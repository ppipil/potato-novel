from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .integration import build_integration_manifest
from .openings import PRESET_OPENINGS, get_opening_summary, get_opening_title
from .security import random_urlsafe, sign_payload, verify_payload

app = FastAPI(title="Potato Novel Backend")
DEFAULT_DATA_DIR = Path("/tmp/potato-novel-data") if os.getenv("VERCEL") else Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()
STORIES_PATH = DATA_DIR / "stories.json"
SESSIONS_PATH = DATA_DIR / "story_sessions.json"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
COOKIE_PATH = "/"
PACKAGE_VERSION = 2

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_env() -> None:
    missing = []
    for name, value in {
        "SECONDME_CLIENT_ID": settings.client_id,
        "SECONDME_CLIENT_SECRET": settings.client_secret,
        "SECONDME_AUTH_URL": settings.auth_url,
        "SECONDME_TOKEN_URL": settings.token_url,
        "SECONDME_USERINFO_URL": settings.userinfo_url,
        "SESSION_SECRET": settings.session_secret,
    }.items():
        if not value or value.startswith("replace-with-"):
            missing.append(name)
    if missing:
        raise HTTPException(status_code=500, detail={"message": "Missing backend configuration", "fields": missing})


def _get_server_session(request: Request) -> dict[str, Any]:
    session = request.cookies.get("session")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_payload(session, settings.session_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid session")
    token = payload.get("token", {})
    user = payload.get("user", {})
    if not token.get("access_token"):
        raise HTTPException(status_code=401, detail="Session expired")
    return {"user": user, "token": token}


def _load_stories() -> list[dict[str, Any]]:
    if not STORIES_PATH.exists():
        return []
    return json.loads(STORIES_PATH.read_text(encoding="utf-8"))


def _save_stories(stories: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_PATH.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_sessions() -> list[dict[str, Any]]:
    if not SESSIONS_PATH.exists():
        return []
    return json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))


def _save_sessions(sessions: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_PATH.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_json_story_instruction(extra_instruction: str = "") -> str:
    extra = f"\n额外要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在担任一个中文互动叙事引擎，需要把故事拆成多轮推进，而不是一次写完整篇小说。"
        "每次只推进一个关键场景，并给玩家可选行动。\n"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "JSON 结构必须为："
        '{"scene":"当前场景描写","summary":"到目前为止的剧情摘要","choices":["动作1","动作2","动作3"],'
        '"status":"ongoing 或 ending 或 complete","stageLabel":"当前阶段标题","directorNote":"一句简短的局势提示"}。'
        "其中 scene 必须自然分成 2 到 4 段剧情；choices 必须正好 3 条。"
        "choices 不要写成抽象指令，比如“直接质问对方”“暗中观察”“继续试探”。"
        "choices 必须写成生活化、人物化、能直接点选的选项文案。"
        "至少 2 个 choice 必须是带说话口吻的具体回应，可以直接写人物会说的话，或者“我抬眼看着他：……”“我笑了一下：……”这样的表达。"
        "最多 1 个 choice 可以是纯行为选项。"
        "三个 choices 必须体现明显不同的人设倾向、语言风格和关系走向，比如嘴硬、温柔、试探、撩拨、装傻、逞强、真诚、心机、克制、挑衅。"
        "每个 choice 都要让人觉得有戏、有情绪张力、符合言情或互动小说的阅读感。"
        f"{extra}"
    )


def _build_json_story_package_instruction(extra_instruction: str = "") -> str:
    extra = f"\n修正要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在担任中文互动小说引擎，需要一次性生成一个可本地游玩的短篇互动故事包，而不是逐回合聊天续写。"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "只允许返回一个 JSON object，不能在前后补充说明、注释、标题或解释。\n"
        "JSON 结构必须为："
        '{"title":"故事标题","rootNodeId":"起始节点ID","nodes":['
        '{"id":"节点ID","kind":"turn 或 ending","turn":1,'
        '"stageLabel":"阶段标题","directorNote":"局势提示","scene":"正文","summary":"本节点摘要",'
        '"choices":[{"id":"选项ID","text":"选项文案","nextNodeId":"下个节点ID","style":"风格","tone":"语气",'
        '"effects":{"persona":{"真诚":1},"relationship":{"好感":1}}}]}'
        "]}"
        "其中 turn 节点必须正好 3 个 choices，ending 节点的 choices 必须是空数组。"
        "整个故事包固定为 3 个 ending 节点。"
        "整个分支图通常包含 4 到 7 个 turn 节点，但用户实际单条游玩路径应在 2 到 4 个 turn 节点后进入结局。"
        "rootNodeId 必须指向第一个 turn 节点。"
        "每个 turn 节点都必须能通过 choices 走到某个 ending 节点。"
        "每个 choice 的 nextNodeId 必须指向同一故事包中的合法节点，不能留空，不能引用不存在的节点。"
        "每个 choice 都要写出明确的人设或好感影响，effects 里的数值只能用整数。"
        "正文 scene 必须是 2 到 4 段中文互动小说文本，风格更像橙光/互动小说，而不是聊天回复。"
        "三个 choices 必须明显不同，不能只是同义改写。"
        "至少 2 个 choices 要有明确对白或人物动作，不要写成抽象标签。"
        "正文 scene 和 choices.text 中禁止使用英文双引号 \"，因为这会破坏 JSON。"
        "如果需要对白，一律使用中文直角引号「」或自然叙述，不要使用英文双引号。"
        "正文和选项里都不要出现 ```、JSON、注释、解释文字。"
        "单个 scene 控制在 3 段以内，单个 choice 控制在 40 个中文字符以内。"
        "不要输出任何 null，不要省略必填字段。"
        f"{extra}"
    )


def _build_json_story_skeleton_instruction(extra_instruction: str = "") -> str:
    extra = f"\n修正要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在担任中文互动小说引擎，现在只需要先生成一个可玩的分支骨架，不要生成长篇正文。"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "只允许返回一个 JSON object。\n"
        "JSON 结构必须为："
        '{"title":"故事标题","rootNodeId":"起始节点ID","nodes":['
        '{"id":"节点ID","kind":"turn 或 ending","turn":1,"stageLabel":"阶段标题",'
        '"directorNote":"一句局势提示","summary":"一句本节点摘要",'
        '"choices":[{"id":"选项ID","text":"选项文案","nextNodeId":"下个节点ID","style":"风格","tone":"语气",'
        '"effects":{"persona":{"真诚":1},"relationship":{"好感":1}}}]}'
        "]}"
        "其中 turn 节点必须正好 3 个 choices，ending 节点的 choices 必须是空数组。"
        "整个骨架固定为 3 个 ending 节点。"
        "整个分支图通常包含 4 到 7 个 turn 节点，但用户实际单条游玩路径应在 3 个 turn 节点后进入结局。"
        "所有 nextNodeId 都必须合法，并且从 rootNodeId 必须能走到 ending。"
        "summary 和 directorNote 必须简短，每项不超过 30 个中文字符。"
        "choices.text 不超过 28 个中文字符。"
        "不要输出 scene 字段，不要写长段正文。"
        "正文中的对白后续再生成，这一阶段只保留骨架。"
        "不要输出 2 个或 4 个 ending 节点。"
        "不要输出 null，不要省略必填字段。"
        f"{extra}"
    )


def _build_json_story_node_instruction(extra_instruction: str = "") -> str:
    extra = f"\n修正要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在补全互动小说某一个节点的正文内容。"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "JSON 结构必须为："
        '{"stageLabel":"阶段标题","directorNote":"一句局势提示","scene":"2到3段正文","summary":"一句本节点摘要"}'
        "scene 必须是中文互动小说文本。"
        "禁止使用英文双引号 \"，如果出现对白，只能使用中文直角引号「」。"
        "不要输出 choices，不要输出 nodes，不要解释结构。"
        "summary 和 directorNote 要短，scene 要围绕已给定的分支走向。"
        f"{extra}"
    )


def _compose_story_prompt(opening: str, role: str, user_name: str, extra_instruction: str = "") -> str:
    return (
        f"{_build_json_story_instruction(extra_instruction)}\n\n"
        f"玩家昵称：{user_name or 'SecondMe 用户'}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        "请生成第 1 回合。"
        "这一回合要完成世界建立、冲突抛出和可行动作设计。"
        "选项之间必须产生真实分支张力，同时要让用户一眼看出这是不同性格主角会说的话或会做的事。"
        "status 默认为 ongoing，除非开头本身已经天然走到结局。"
    )


def _compose_story_package_prompt(
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
    repair_hint: str = "",
) -> str:
    preferred = "、".join(persona_profile.get("preferredStyles", [])) or "真诚、试探、撩拨"
    return (
        f"{_build_json_story_package_instruction(repair_hint)}\n\n"
        f"玩家昵称：{user_name or 'SecondMe 用户'}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        f"用户偏好人设：{persona_profile.get('label', '未知分身')}，偏好风格：{preferred}\n"
        "生成要求："
        "整个故事包要有清晰开端、升温、反转、收束；"
        "不同选项要体现温柔、试探、强势、心机、嘴硬、撩拨等差异；"
        "至少设计 1 个甜系或高好感结局，也可以加入 1 个翻车或遗憾结局；"
        "不要出现开放式输入槽，不要让玩家自己补完动作。"
        "所有对白统一写成「这样」而不是 \"这样\"。"
        "宁可句子短一点，也不要把 JSON 写坏。"
        "请优先保证结构正确，其次再追求文风华丽。"
    )


def _compose_story_skeleton_prompt(
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
    repair_hint: str = "",
) -> str:
    preferred = "、".join(persona_profile.get("preferredStyles", [])) or "真诚、试探、撩拨"
    return (
        f"{_build_json_story_skeleton_instruction(repair_hint)}\n\n"
        f"玩家昵称：{user_name or 'SecondMe 用户'}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        f"用户偏好人设：{persona_profile.get('label', '未知分身')}，偏好风格：{preferred}\n"
        "请先生成结构稳定的互动故事骨架："
        "要有开端、升温、反转、收束；"
        "不同选项要体现温柔、试探、强势、心机、嘴硬、撩拨等差异；"
        "三个结局里至少包含：1 个高好感结局、1 个成长/和解结局、1 个遗憾或开放式结局。"
        "再次强调：固定输出 3 个 ending 节点，且用户单条路径应在 2 到 4 个 turn 节点后进入结局。"
        "这一阶段最重要的是结构合法、分支清晰、选项不重复。"
    )


def _compose_story_node_prompt(
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    repair_hint: str = "",
) -> str:
    node_lines = []
    for item in skeleton_nodes:
        choices_text = "；".join(
            f"{choice.get('id')}->{choice.get('nextNodeId')}:{choice.get('text')}"
            for choice in item.get("choices", [])
        ) or "无选项"
        node_lines.append(
            f"- {item.get('id')} | {item.get('kind')} | turn={item.get('turn')} | {item.get('stageLabel')} | {item.get('summary')} | {choices_text}"
        )
    skeleton_digest = "\n".join(node_lines)
    choice_digest = "\n".join(
        f"- {choice.get('id')}：{choice.get('text')} -> {choice.get('nextNodeId')}"
        for choice in node.get("choices", [])
    ) or "- 本节点为 ending，无 choices"
    ending_instruction = (
        "这是结局节点。scene 不要只写一句收尾摘要，而要写成一个真正的结局场景。"
        "请写 3 到 4 段，优先使用人物对白、动作和情绪反应来完成收束。"
        "至少包含：最后一次对峙或确认、情绪落点、结局余波。"
        "读感要像橙光结局页前的正式收尾，不要像系统结算文案。"
    ) if node.get("kind") == "ending" else (
        "这是普通回合节点。scene 写 2 到 3 段，重点放在当前冲突推进和情绪张力上。"
    )
    return (
        f"{_build_json_story_node_instruction(repair_hint)}\n\n"
        f"故事标题：{title}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        f"当前节点：{node.get('id')} ({node.get('kind')})\n"
        f"当前节点阶段：{node.get('stageLabel')}\n"
        f"当前节点摘要：{node.get('summary')}\n"
        f"当前节点选项：\n{choice_digest}\n"
        f"完整骨架：\n{skeleton_digest}\n"
        "请只补全当前节点的正文，使它和骨架走向一致。"
        "scene 要有文学阅读感，但不要过长，不要引入骨架之外的新主线。"
        f"{ending_instruction}"
    )


def _compose_story_turn_prompt(session: dict[str, Any], user_name: str, action: str) -> str:
    transcript = session.get("transcript", [])
    recent_events = transcript[-6:]
    timeline = "\n".join(
        f"- {item.get('label', '事件')}：{item.get('text', '').strip()}" for item in recent_events if item.get("text")
    )
    target_status = "complete" if session.get("turnCount", 1) >= 5 or "收尾" in action or "结局" in action else "ending" if session.get("turnCount", 1) >= 4 else "ongoing"
    return (
        f"{_build_json_story_instruction()}\n\n"
        f"玩家昵称：{user_name or 'SecondMe 用户'}\n"
        f"玩家身份：{session['meta'].get('role', '')}\n"
        f"故事开头：{session['meta'].get('opening', '')}\n"
        f"当前回合数：{session.get('turnCount', 1)}\n"
        f"当前剧情摘要：{session.get('summary', '')}\n"
        f"当前状态：{json.dumps(session.get('state', {}), ensure_ascii=False)}\n"
        f"最近事件：\n{timeline or '- 暂无'}\n"
        f"玩家本轮行动：{action}\n"
        f"本轮目标状态：{target_status}\n"
        "请基于玩家行动推进下一回合。"
        "如果之前埋下了信任、误解、操控、伪装等伏笔，请在本轮继续兑现这些影响。"
        "新一轮 choices 要延续人物关系变化，给出更生活化、更像橙光互动小说的选项，不要退回抽象动作标签。"
        "如果故事已经接近收束，请让局势明显走向结局；如果本轮就是结局，请把 status 设为 complete。"
    )


def _compose_ending_analysis_prompt(opening: str, summary: str, transcript: list[dict[str, Any]], state: dict[str, Any]) -> str:
    action_lines = "\n".join(
        f"- 第{item.get('turn', '')}回合 {item.get('text', '').strip()}"
        for item in transcript
        if "玩家行动" in str(item.get("label", "")) and item.get("text")
    )
    return (
        "你是一名擅长中文互动小说、恋爱测试和角色洞察的分析型写手。"
        "请根据用户在一局故事里的具体选择，输出一段有趣、轻巧、像互动游戏结算页一样的分析。"
        "不要讲大道理，不要空泛总结，要结合具体选择风格来判断。\n"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "JSON 结构必须为："
        '{"title":"土豆人格标题","personaTags":["标签1","标签2"],"romance":"感情向分析","life":"生活向分析","nextUniverseHook":"一句推荐下一个宇宙的钩子"}。\n\n'
        f"故事开头：{opening}\n"
        f"剧情结局摘要：{summary}\n"
        f"玩家实际选择：\n{action_lines or '- 暂无'}\n"
        f"故事状态：{json.dumps(state or {}, ensure_ascii=False)}\n\n"
        "要求："
        "title 要像测试结果名，简短有记忆点；"
        "personaTags 返回 2 到 4 个简短中文标签；"
        "romance 要分析这个人谈感情时是什么风格；"
        "life 要分析这个人放到现实生活里像什么性格；"
        "nextUniverseHook 要像一句有趣的推荐语。"
    )


async def _call_secondme_chat(access_token: str, prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            chat_response = await client.post(
                "https://api.mindverse.com/gate/lab/api/secondme/chat/stream",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"message": prompt},
            )
            if chat_response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "SecondMe chat request failed", "body": chat_response.text},
                )
            story_text = _extract_story_from_sse(chat_response.text)
            if not story_text.strip():
                raise HTTPException(status_code=400, detail="SecondMe chat returned empty content")
            return story_text
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe chat API", "error": str(exc)},
        ) from exc


async def _call_secondme_act(access_token: str, message: str, action_control: str, max_tokens: int = 2000) -> str:
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            act_response = await client.post(
                "https://api.mindverse.com/gate/lab/api/secondme/act/stream",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "message": message,
                    "actionControl": action_control,
                    "maxTokens": max_tokens,
                },
            )
            if act_response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "SecondMe act request failed", "body": act_response.text},
                )
            action_text = _extract_story_from_sse(act_response.text)
            if not action_text.strip():
                raise HTTPException(status_code=400, detail="SecondMe act returned empty content")
            return action_text
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe act API", "error": str(exc)},
        ) from exc


def _normalize_story_turn(raw_text: str) -> dict[str, Any]:
    payload = _extract_json_object(raw_text)
    scene = _clean_model_text(payload.get("scene", ""))
    summary = _clean_model_text(payload.get("summary", ""))
    stage_label = _clean_model_text(payload.get("stageLabel", "剧情推进")) or "剧情推进"
    director_note = _clean_model_text(payload.get("directorNote", ""))
    status = str(payload.get("status", "ongoing")).strip().lower()
    raw_choices = payload.get("choices", [])
    if not isinstance(raw_choices, list):
        raw_choices = []
    choices = [_clean_model_text(item) for item in raw_choices if _clean_model_text(item)]
    if len(choices) < 3:
        fallback = [
            "我抬眼看着他，故作镇定地问：“所以，你现在打算把真相告诉我，还是继续让我猜？”",
            "我先软下语气：“你别急，我不是来拆穿你的。我只是想知道，我该站在哪一边。”",
            "我没有立刻开口，只是安静地观察他的表情，想先确认他真正害怕的到底是什么。"] 
        for item in fallback:
            if len(choices) >= 3:
                break
            choices.append(item)
    choices = _ensure_distinct_choices(choices[:3], scene)
    if status not in {"ongoing", "ending", "complete"}:
        status = "ongoing"
    if not scene:
        raise HTTPException(status_code=400, detail={"message": "Interactive story response missing scene", "body": raw_text})
    if not summary:
        summary = scene
    return {
        "scene": scene,
        "paragraphs": _split_scene_into_paragraphs(scene),
        "summary": summary,
        "choices": choices,
        "status": status,
        "stageLabel": stage_label,
        "directorNote": director_note,
    }


def _normalize_choice_effect_payload(payload: Any, fallback_style: str) -> dict[str, dict[str, int]]:
    normalized = {"persona": {}, "relationship": {}}
    if isinstance(payload, dict):
        for category in ("persona", "relationship"):
            category_payload = payload.get(category, {})
            if isinstance(category_payload, dict):
                normalized[category] = {
                    _clean_model_text(key): int(value)
                    for key, value in category_payload.items()
                    if _clean_model_text(key) and isinstance(value, (int, float))
                }
    fallback = _choice_effects(fallback_style)
    for category in ("persona", "relationship"):
        if not normalized[category]:
            normalized[category] = fallback.get(category, {})
    return normalized


def _normalize_story_package(raw_text: str, opening: str, role: str, persona_profile: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story package JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_nodes = payload.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise HTTPException(status_code=400, detail={"message": "Story package nodes must be an array", "body": raw_text})

    nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = _clean_model_text(raw_node.get("id", f"N{index}")) or f"N{index}"
        kind = _clean_model_text(raw_node.get("kind", "turn")).lower()
        if kind not in {"turn", "ending"}:
            kind = "turn"
        turn = raw_node.get("turn", index)
        if not isinstance(turn, int):
            turn = index
        scene = _clean_model_text(raw_node.get("scene", ""))
        if not scene:
            continue
        summary = _clean_model_text(raw_node.get("summary", "")) or scene
        stage_label = _clean_model_text(raw_node.get("stageLabel", "剧情推进")) or "剧情推进"
        director_note = _clean_model_text(raw_node.get("directorNote", ""))
        raw_choices = raw_node.get("choices", [])
        if not isinstance(raw_choices, list):
            raw_choices = []
        choices = []
        if kind == "turn":
            for choice_index, raw_choice in enumerate(raw_choices[:3], start=1):
                if not isinstance(raw_choice, dict):
                    continue
                text = _clean_model_text(raw_choice.get("text", ""))
                next_node_id = _clean_model_text(raw_choice.get("nextNodeId", ""))
                if not text or not next_node_id:
                    continue
                style = _clean_model_text(raw_choice.get("style", "")) or _choice_style(text)
                tone = _clean_model_text(raw_choice.get("tone", "")) or _choice_tone(text, style)
                choices.append(
                    {
                        "id": _clean_model_text(raw_choice.get("id", f"{node_id}-C{choice_index}")) or f"{node_id}-C{choice_index}",
                        "text": text,
                        "nextNodeId": next_node_id,
                        "style": style,
                        "tone": tone,
                        "effects": _normalize_choice_effect_payload(raw_choice.get("effects"), style),
                    }
                )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "turn": turn,
                "stageLabel": stage_label,
                "directorNote": director_note,
                "scene": scene,
                "paragraphs": _split_scene_into_paragraphs(scene),
                "summary": summary,
                "choices": choices if kind == "turn" else [],
            }
        )

    story_package = {
        "version": PACKAGE_VERSION,
        "title": _clean_model_text(payload.get("title", "")) or get_opening_title(opening) or "未命名互动宇宙",
        "opening": opening,
        "role": role,
        "rootNodeId": _clean_model_text(payload.get("rootNodeId", "N1")) or "N1",
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"好感": 0, "信任": 0, "警惕": 0},
            "persona": {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0},
            "turn": 1,
            "endingHint": "",
        },
    }
    validation_error = _story_package_validation_error(story_package)
    if validation_error:
        raise HTTPException(status_code=400, detail={"message": validation_error, "body": raw_text})
    return _finalize_story_package(story_package, persona_profile)


def _normalize_story_skeleton(raw_text: str, opening: str, role: str) -> dict[str, Any]:
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story skeleton JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_nodes = payload.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise HTTPException(status_code=400, detail={"message": "Story skeleton nodes must be an array", "body": raw_text})

    nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = _clean_model_text(raw_node.get("id", f"N{index}")) or f"N{index}"
        kind = _clean_model_text(raw_node.get("kind", "turn")).lower()
        if kind not in {"turn", "ending"}:
            kind = "turn"
        turn = raw_node.get("turn", index)
        if not isinstance(turn, int):
            turn = index
        stage_label = _clean_model_text(raw_node.get("stageLabel", "剧情推进")) or "剧情推进"
        director_note = _clean_model_text(raw_node.get("directorNote", ""))
        summary = _clean_model_text(raw_node.get("summary", "")) or stage_label
        raw_choices = raw_node.get("choices", [])
        if not isinstance(raw_choices, list):
            raw_choices = []
        choices = []
        if kind == "turn":
            for choice_index, raw_choice in enumerate(raw_choices[:3], start=1):
                if not isinstance(raw_choice, dict):
                    continue
                text = _clean_model_text(raw_choice.get("text", ""))
                next_node_id = _clean_model_text(raw_choice.get("nextNodeId", ""))
                if not text or not next_node_id:
                    continue
                style = _clean_model_text(raw_choice.get("style", "")) or _choice_style(text)
                tone = _clean_model_text(raw_choice.get("tone", "")) or _choice_tone(text, style)
                choices.append(
                    {
                        "id": _clean_model_text(raw_choice.get("id", f"{node_id}-C{choice_index}")) or f"{node_id}-C{choice_index}",
                        "text": text,
                        "nextNodeId": next_node_id,
                        "style": style,
                        "tone": tone,
                        "effects": _normalize_choice_effect_payload(raw_choice.get("effects"), style),
                    }
                )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "turn": turn,
                "stageLabel": stage_label,
                "directorNote": director_note,
                "summary": summary,
                "choices": choices if kind == "turn" else [],
            }
        )

    skeleton = {
        "version": PACKAGE_VERSION,
        "title": _clean_model_text(payload.get("title", "")) or get_opening_title(opening) or "未命名互动宇宙",
        "opening": opening,
        "role": role,
        "rootNodeId": _clean_model_text(payload.get("rootNodeId", "")),
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"好感": 0, "信任": 0, "警惕": 0},
            "persona": {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0},
            "turn": 1,
            "endingHint": "",
        },
    }
    validation_error = _story_package_validation_error(skeleton)
    if validation_error:
        raise HTTPException(status_code=400, detail={"message": validation_error, "body": raw_text})
    return skeleton


def _normalize_story_node_content(raw_text: str) -> dict[str, Any]:
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story node JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc
    scene = _clean_model_text(payload.get("scene", ""))
    if not scene:
        raise HTTPException(status_code=400, detail={"message": "Story node scene is missing", "body": raw_text})
    stage_label = _clean_model_text(payload.get("stageLabel", "剧情推进")) or "剧情推进"
    director_note = _clean_model_text(payload.get("directorNote", ""))
    summary = _clean_model_text(payload.get("summary", "")) or scene
    return {
        "stageLabel": stage_label,
        "directorNote": director_note,
        "scene": scene,
        "paragraphs": _split_scene_into_paragraphs(scene),
        "summary": summary,
    }


def _normalize_ending_analysis(raw_text: str) -> dict[str, str]:
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException:
        payload = _extract_ending_analysis_payload_fallback(raw_text) or {}
    return {
        "title": _clean_model_text(payload.get("title", "")) or "你的土豆人格正在生成中",
        "personaTags": [
            _clean_model_text(item)
            for item in payload.get("personaTags", [])
            if _clean_model_text(item)
        ] if isinstance(payload.get("personaTags"), list) else [],
        "romance": _clean_model_text(payload.get("romance", "")) or "这局里的你，显然不是随便点点选项的人。",
        "life": _clean_model_text(payload.get("life", "")) or "放到现实生活里，你大概也是那种会把故事过成连续剧的人。",
        "nextUniverseHook": _clean_model_text(payload.get("nextUniverseHook", "")) or "下一本宇宙，也许更适合你的那一面。"
    }


def _extract_ending_analysis_payload_fallback(raw_text: str) -> dict[str, Any] | None:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    keys = ["title", "personaTags", "romance", "life", "nextUniverseHook"]
    extracted: dict[str, Any] = {}

    for index, key in enumerate(keys):
        marker = f'"{key}":'
        start_index = candidate.find(marker)
        if start_index == -1:
            continue
        value_start = start_index + len(marker)
        next_start = len(candidate)
        for next_key in keys[index + 1 :]:
            next_marker = f',\n  "{next_key}":'
            found = candidate.find(next_marker, value_start)
            if found != -1:
                next_start = found
                break
        raw_value = candidate[value_start:next_start].strip().rstrip(",").strip()
        if key == "personaTags":
            extracted[key] = _parse_loose_choices(raw_value)
        else:
            extracted[key] = _parse_loose_string_value(raw_value)

    if not extracted:
        return None
    return extracted


def _ensure_distinct_choices(choices: list[str], scene: str = "") -> list[str]:
    distinct = []
    seen_styles = set()
    fallback_by_style = {
        "confrontation": "我盯着他的眼睛，半点没退：“你要是真想瞒我，就不会露出这种表情。现在，告诉我实话。”",
        "soft": "我放轻声音：“你可以不马上解释清楚，但至少别把我推开。让我陪你一起面对。”",
        "tease": "我偏头笑了一下：“原来你也会紧张？那我是不是该重新认识一下你了？”",
    }
    ordered_styles = ["confrontation", "soft", "tease"]

    for choice in choices:
        style = _choice_style(choice)
        if style in seen_styles:
            continue
        distinct.append(choice)
        seen_styles.add(style)

    for style in ordered_styles:
        if len(distinct) >= 3:
            break
        if style in seen_styles:
            continue
        distinct.append(fallback_by_style[style])
        seen_styles.add(style)

    while len(distinct) < 3:
        distinct.append(_fallback_choice_by_index(len(distinct), scene))
    return distinct[:3]


def _fallback_choice_by_index(index: int, scene: str) -> str:
    fallbacks = [
        "我低声开口：“你先别躲，我想听你亲口说。”",
        "我故意弯起眼睛笑了笑：“如果你想试探我，那我也不介意陪你玩到底。”",
        "我没有马上接话，只是顺着他的动作慢慢逼近一步，想看他会不会先失态。"] 
    if 0 <= index < len(fallbacks):
        return fallbacks[index]
    return f"我顺着眼前的局势轻声说出第 {index + 1} 种回应，试探他的真实态度。"


def _split_scene_into_paragraphs(scene: str) -> list[str]:
    normalized = scene.replace("\r\n", "\n").strip()
    paragraphs = [part.strip() for part in normalized.split("\n") if part.strip()]
    if len(paragraphs) >= 2:
        return paragraphs[:4]
    chunks = [part.strip() for part in normalized.replace("。", "。\n").split("\n") if part.strip()]
    return chunks[:4] if chunks else [scene]


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise HTTPException(status_code=400, detail={"message": "Interactive story response was not valid JSON", "body": raw_text})
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        fallback_payload = _extract_story_payload_fallback(candidate)
        if fallback_payload is not None:
            return fallback_payload
        raise HTTPException(
            status_code=400,
            detail={"message": "Interactive story JSON parse failed", "body": raw_text, "error": str(exc)},
        ) from exc


def _extract_story_payload_fallback(candidate: str) -> dict[str, Any] | None:
    keys = ["scene", "summary", "choices", "status", "stageLabel", "directorNote"]
    extracted: dict[str, Any] = {}

    for index, key in enumerate(keys):
        marker = f'"{key}":'
        start = candidate.find(marker)
        if start == -1:
            return None
        value_start = start + len(marker)
        next_start = len(candidate)
        for next_key in keys[index + 1 :]:
            next_marker = f',\n  "{next_key}":'
            found = candidate.find(next_marker, value_start)
            if found != -1:
                next_start = found
                break
        raw_value = candidate[value_start:next_start].strip().rstrip(",").strip()
        if key == "choices":
            extracted[key] = _parse_loose_choices(raw_value)
        else:
            extracted[key] = _parse_loose_string_value(raw_value)

    if not extracted.get("scene") or not extracted.get("choices"):
        return None
    return extracted


def _parse_loose_string_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return _clean_model_text(
        value.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
        .strip()
    )


def _clean_model_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()

    # Some model responses leak the closing JSON brace into the final string field.
    text = text.removesuffix("\n}").removesuffix("}")
    text = text.strip()

    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
      text = text[1:-1].strip()

    return text


def _parse_loose_choices(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if value.startswith("["):
        value = value[1:]
    if value.endswith("]"):
        value = value[:-1]

    choices: list[str] = []
    current = []
    in_string = False
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            if in_string:
                choices.append("".join(current).strip())
                current = []
                in_string = False
            else:
                in_string = True
            continue
        if in_string:
            current.append(char)

    cleaned = [
        item.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\").strip()
        for item in choices
        if item.strip()
    ]
    return cleaned


def _find_session(session_id: str, user_id: str) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    sessions = _load_sessions()
    for index, item in enumerate(sessions):
        if item.get("id") == session_id and item.get("userId") == user_id:
            return sessions, item, index
    raise HTTPException(status_code=404, detail="Story session not found")


def _package_matches(session: dict[str, Any], user_id: str, opening: str, role: str) -> bool:
    return (
        session.get("userId") == user_id
        and session.get("meta", {}).get("opening", "").strip() == opening.strip()
        and session.get("meta", {}).get("role", "").strip() == role.strip()
    )


def _find_reusable_package(sessions: list[dict[str, Any]], user_id: str, opening: str, role: str) -> dict[str, Any] | None:
    for item in sessions:
        if not _package_matches(item, user_id, opening, role):
            continue
        if item.get("kind") != "story_package":
            continue
        if item.get("packageStatus") not in {"ready", "hydrating"}:
            continue
        package = item.get("package", {})
        if package.get("version") != PACKAGE_VERSION:
            continue
        if package.get("generatedBy") != "secondme_act_two_stage":
            continue
        return item
    return None


def _serialize_session(session: dict[str, Any]) -> dict[str, Any]:
    if session.get("kind") == "story_package":
        return {
            "id": session["id"],
            "kind": "story_package",
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"],
            "status": session.get("status", "ready"),
            "packageStatus": session.get("packageStatus", "ready"),
            "meta": session.get("meta", {}),
            "package": session.get("package", {}),
            "completedRun": session.get("completedRun"),
        }
    return {
        "id": session["id"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "status": session["status"],
        "turnCount": session["turnCount"],
        "meta": session["meta"],
        "summary": _clean_model_text(session.get("summary", "")),
        "currentScene": _clean_model_text(session.get("currentScene", "")),
        "paragraphs": [_clean_model_text(item) for item in session.get("paragraphs", []) if _clean_model_text(item)],
        "choices": session.get("choices", []),
        "stageLabel": _clean_model_text(session.get("stageLabel", "剧情推进")) or "剧情推进",
        "directorNote": _clean_model_text(session.get("directorNote", "")),
        "state": session.get("state", {}),
        "personaProfile": session.get("personaProfile", {}),
        "recommendedChoiceId": session.get("recommendedChoiceId"),
        "aiChoiceId": session.get("aiChoiceId"),
        "transcript": [
            {
                **item,
                "label": _clean_model_text(item.get("label", "")),
                "text": _clean_model_text(item.get("text", "")),
            }
            for item in session.get("transcript", [])
        ],
    }


def _build_story_from_session(session: dict[str, Any]) -> str:
    if session.get("kind") == "story_package":
        completed_run = session.get("completedRun")
        if not completed_run:
            raise HTTPException(status_code=400, detail="Story package has not been completed")
        return _build_story_from_completed_run(session, completed_run)

    title = get_opening_title(session["meta"].get("opening", "")) or "未命名故事"
    lines = [
        f"《{title}：互动版》",
        f"玩家身份：{session['meta'].get('role', '')}",
        f"创作者：{session['meta'].get('author', '')}",
        "",
        "【故事开端】",
        session["meta"].get("opening", ""),
        "",
    ]
    for item in session.get("transcript", []):
        label = item.get("label", "事件")
        turn = item.get("turn")
        prefix = f"第 {turn} 回合" if turn else "故事片段"
        lines.append(f"【{prefix}·{label}】")
        lines.append(item.get("text", ""))
        lines.append("")
    if session.get("summary"):
        lines.extend(["【结局摘要】", session["summary"], ""])
    state = session.get("state", {})
    if state:
        lines.extend(
            [
                "【结局状态】",
                f"阶段：{state.get('stage', '')}",
                f"旗标：{', '.join(state.get('flags', [])) or '无'}",
                f"关系：{json.dumps(state.get('relationship', {}), ensure_ascii=False)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _build_story_from_completed_run(session: dict[str, Any], completed_run: dict[str, Any]) -> str:
    title = session.get("package", {}).get("title") or get_opening_title(session["meta"].get("opening", "")) or "未命名故事"
    lines = [
        f"《{title}：互动版》",
        f"玩家身份：{session['meta'].get('role', '')}",
        f"创作者：{session['meta'].get('author', '')}",
        "",
        "【故事开端】",
        session["meta"].get("opening", ""),
        "",
    ]
    for item in completed_run.get("transcript", []):
        label = item.get("label", "事件")
        turn = item.get("turn")
        prefix = f"第 {turn} 回合" if turn else "故事片段"
        lines.append(f"【{prefix}·{label}】")
        lines.append(_clean_model_text(item.get("text", "")))
        lines.append("")
    summary = _clean_model_text(completed_run.get("summary", ""))
    if summary:
        lines.extend(["【结局摘要】", summary, ""])
    state = completed_run.get("state", {})
    if state:
        lines.extend(
            [
                "【结局状态】",
                f"阶段：{state.get('stage', '')}",
                f"旗标：{', '.join(state.get('flags', [])) or '无'}",
                f"关系：{json.dumps(state.get('relationship', {}), ensure_ascii=False)}",
                f"人格：{json.dumps(state.get('persona', {}), ensure_ascii=False)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _derive_persona_profile(user: dict[str, Any]) -> dict[str, Any]:
    seed = f"{user.get('route', '')}|{user.get('name', '')}|{user.get('userId', '')}"
    styles = [
        {
            "key": "strategist",
            "label": "策略型分身",
            "preferredStyles": ["strategy", "manipulation", "observation"],
            "description": "更偏向试探、布局和控制风险。",
        },
        {
            "key": "empath",
            "label": "共情型分身",
            "preferredStyles": ["trust", "support", "observation"],
            "description": "更偏向理解他人、建立关系和稳住局势。",
        },
        {
            "key": "rebel",
            "label": "冲锋型分身",
            "preferredStyles": ["confrontation", "risk", "sacrifice"],
            "description": "更偏向正面碰撞、冒险推进和主动改变局面。",
        },
    ]
    total = sum(ord(char) for char in seed) if seed else 0
    profile = styles[total % len(styles)]
    return {
        **profile,
        "source": "secondme-user-heuristic",
    }


def _choice_style(choice: str) -> str:
    mapping = [
        ("“", "dialogue"),
        ("”", "dialogue"),
        ("我笑", "tease"),
        ("笑了一下", "tease"),
        ("偏头", "tease"),
        ("靠近", "tease"),
        ("质问", "confrontation"),
        ("揭穿", "confrontation"),
        ("逼", "confrontation"),
        ("你到底", "confrontation"),
        ("为什么", "confrontation"),
        ("试探", "strategy"),
        ("假装", "strategy"),
        ("套话", "strategy"),
        ("离开", "observation"),
        ("观察", "observation"),
        ("躲", "observation"),
        ("相信", "trust"),
        ("陪你", "soft"),
        ("别怕", "soft"),
        ("没关系", "soft"),
        ("我会", "soft"),
        ("保护", "support"),
        ("安抚", "support"),
        ("利用", "manipulation"),
        ("诱导", "manipulation"),
        ("交易", "manipulation"),
        ("冒险", "risk"),
        ("闯", "risk"),
        ("牺牲", "sacrifice"),
    ]
    for keyword, style in mapping:
        if keyword in choice:
            return style
    return "dialogue"


def _choice_tone(choice: str, style: str) -> str:
    if style == "tease":
        return "撩拨"
    if style in {"soft", "support", "trust"}:
        return "温柔"
    if style == "confrontation":
        return "强势"
    if style in {"strategy", "manipulation"}:
        return "试探"
    if style == "observation":
        return "克制"
    if style == "risk":
        return "冒险"
    return "生活化"


def _choice_effects(style: str) -> dict[str, dict[str, int]]:
    persona_effect = {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0}
    relationship_effect = {"好感": 0, "信任": 0, "警惕": 0}

    if style in {"soft", "support", "trust"}:
        persona_effect["真诚"] += 1
        relationship_effect["好感"] += 1
        relationship_effect["信任"] += 1
    elif style == "tease":
        persona_effect["胆量"] += 1
        relationship_effect["好感"] += 1
    elif style == "confrontation":
        persona_effect["嘴硬"] += 1
        persona_effect["胆量"] += 1
        relationship_effect["警惕"] += 1
    elif style in {"strategy", "manipulation"}:
        persona_effect["心机"] += 1
        relationship_effect["警惕"] += 1
    elif style == "observation":
        persona_effect["心机"] += 1
    elif style == "risk":
        persona_effect["胆量"] += 1
        relationship_effect["警惕"] += 1

    return {
        "persona": {key: value for key, value in persona_effect.items() if value},
        "relationship": {key: value for key, value in relationship_effect.items() if value},
    }


def _merge_state_delta(state: dict[str, Any], effects: dict[str, dict[str, int]], next_turn: int, stage: str, ending_hint: str = "") -> dict[str, Any]:
    next_state = {
        "stage": stage,
        "flags": list(state.get("flags", [])),
        "relationship": dict(state.get("relationship", {})),
        "persona": dict(state.get("persona", {})),
        "turn": next_turn,
        "endingHint": ending_hint,
    }
    for category in ("persona", "relationship"):
        for key, value in effects.get(category, {}).items():
            next_state[category][key] = next_state[category].get(key, 0) + int(value)
    return next_state


def _infer_stage_from_turn(turn_count: int, total_turns: int, kind: str) -> str:
    if kind == "ending":
        return "ending"
    if turn_count <= 1:
        return "opening"
    if turn_count >= max(total_turns - 1, 3):
        return "climax"
    return "conflict"


def _build_choice_objects(choice_texts: list[str], persona_profile: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    preferred_styles = persona_profile.get("preferredStyles", [])
    choice_objects = []
    recommended_choice_id = None
    ai_choice_id = None

    for index, text in enumerate(choice_texts, start=1):
        style = _choice_style(text)
        choice_id = f"C{index}"
        effects = _choice_effects(style)
        choice = {
            "id": choice_id,
            "text": text,
            "style": style,
            "tone": _choice_tone(text, style),
            "effects": effects,
            "isRecommended": False,
            "isAiChoice": False,
        }
        if recommended_choice_id is None and (style in preferred_styles or (style == "soft" and "support" in preferred_styles)):
            recommended_choice_id = choice_id
        choice_objects.append(choice)

    if recommended_choice_id is None and choice_objects:
        recommended_choice_id = choice_objects[0]["id"]
    ai_choice_id = recommended_choice_id

    for choice in choice_objects:
        if choice["id"] == recommended_choice_id:
            choice["isRecommended"] = True
        if choice["id"] == ai_choice_id:
            choice["isAiChoice"] = True
    return choice_objects, recommended_choice_id, ai_choice_id


def _finalize_story_package(story_package: dict[str, Any], persona_profile: dict[str, Any]) -> dict[str, Any]:
    story_package["version"] = PACKAGE_VERSION
    story_package["generatedBy"] = "secondme_act_two_stage"
    nodes = story_package.get("nodes", [])
    node_map = {node["id"]: node for node in nodes}
    playable_count = sum(1 for node in nodes if node.get("kind") == "turn")
    for node in nodes:
        if node.get("kind") != "turn":
            continue
        choice_objects = []
        raw_choices = node.get("choices", [])
        if not raw_choices:
            continue
        choice_payloads = [choice.get("text", "") for choice in raw_choices]
        recommendation_basis, _, _ = _build_choice_objects(choice_payloads, persona_profile)
        for index, choice in enumerate(raw_choices, start=1):
            style = choice.get("style") or _choice_style(choice.get("text", ""))
            tone = choice.get("tone") or _choice_tone(choice.get("text", ""), style)
            normalized_choice = {
                "id": choice.get("id") or f"{node['id']}-C{index}",
                "text": _clean_model_text(choice.get("text", "")),
                "nextNodeId": _clean_model_text(choice.get("nextNodeId", "")),
                "style": style,
                "tone": tone,
                "effects": _normalize_choice_effect_payload(choice.get("effects"), style),
                "isRecommended": False,
                "isAiChoice": False,
            }
            basis = recommendation_basis[index - 1] if index - 1 < len(recommendation_basis) else {}
            normalized_choice["isRecommended"] = bool(basis.get("isRecommended"))
            normalized_choice["isAiChoice"] = bool(basis.get("isAiChoice"))
            choice_objects.append(normalized_choice)
        node["choices"] = choice_objects
        node["turn"] = int(node.get("turn", 1))
        node["stage"] = _infer_stage_from_turn(node["turn"], playable_count, "turn")
        for choice in node["choices"]:
            next_node = node_map.get(choice["nextNodeId"])
            if next_node and next_node.get("kind") == "ending":
                choice["effects"]["relationship"] = {
                    **choice["effects"].get("relationship", {}),
                }
    story_package["playableTurnCount"] = playable_count
    story_package["endingNodeIds"] = [node["id"] for node in nodes if node.get("kind") == "ending"]
    return story_package


def _validate_story_package(story_package: dict[str, Any]) -> bool:
    return _story_package_validation_error(story_package) is None


def _story_package_validation_error(story_package: dict[str, Any]) -> str | None:
    nodes = story_package.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return "Story package must contain nodes"
    node_map = {node.get("id"): node for node in nodes if node.get("id")}
    root_node_id = story_package.get("rootNodeId")
    if root_node_id not in node_map:
        return "rootNodeId must point to an existing node"
    playable_nodes = [node for node in nodes if node.get("kind") == "turn"]
    ending_nodes = [node for node in nodes if node.get("kind") == "ending"]
    if not (4 <= len(playable_nodes) <= 7):
        return "Story package must contain 4 to 7 playable turn nodes"
    if len(ending_nodes) != 3:
        return "Story package must contain exactly 3 ending nodes"
    path_depths: list[int] = []
    stack: list[tuple[str, int]] = [(root_node_id, 1)]
    visited_depth: set[tuple[str, int]] = set()
    while stack:
        node_id, depth = stack.pop()
        if (node_id, depth) in visited_depth:
            continue
        visited_depth.add((node_id, depth))
        node = node_map.get(node_id)
        if not node:
            continue
        if node.get("kind") == "ending":
            path_depths.append(depth)
            continue
        for choice in node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            next_node = node_map.get(next_node_id)
            if not next_node_id or not next_node:
                continue
            next_depth = depth if next_node.get("kind") == "ending" else depth + 1
            stack.append((next_node_id, next_depth))
    if not path_depths:
        return "No ending path depth found from rootNodeId"
    if min(path_depths) < 2 or max(path_depths) > 4:
        return "Each playable path must reach an ending after 2 to 4 turn nodes"
    for node in playable_nodes:
        choices = node.get("choices", [])
        if len(choices) != 3:
            return f"Turn node {node.get('id', 'unknown')} must contain exactly 3 choices"
        for choice in choices:
            if not _clean_model_text(choice.get("text", "")):
                return f"Choice text is missing in node {node.get('id', 'unknown')}"
            if _clean_model_text(choice.get("nextNodeId", "")) not in node_map:
                return f"Choice nextNodeId is invalid in node {node.get('id', 'unknown')}"

    visited = set()
    stack = [root_node_id]
    reached_ending = False
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = node_map.get(node_id)
        if not node:
            return f"Node {node_id} is missing from node map"
        if node.get("kind") == "ending":
            reached_ending = True
            continue
        for choice in node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            if next_node_id and next_node_id not in visited:
                stack.append(next_node_id)
    if not reached_ending:
        return "No reachable ending node found from rootNodeId"
    return None


def _initial_hydrate_node_ids(skeleton: dict[str, Any]) -> set[str]:
    node_map = {node.get("id"): node for node in skeleton.get("nodes", [])}
    root_node_id = skeleton.get("rootNodeId")
    hydrate_ids: set[str] = set()
    if root_node_id and root_node_id in node_map:
        hydrate_ids.add(root_node_id)
        root_node = node_map[root_node_id]
        for choice in root_node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            if next_node_id in node_map:
                hydrate_ids.add(next_node_id)
    return hydrate_ids


async def _hydrate_story_package_nodes(
    session_record: dict[str, Any],
    access_token: str,
    opening: str,
    role: str,
) -> dict[str, Any]:
    package = session_record.get("package", {})
    skeleton_nodes = package.get("nodes", [])
    pending_nodes = [node for node in skeleton_nodes if not node.get("loaded")]
    if not pending_nodes:
        package["hydratedNodeIds"] = sorted({node.get("id") for node in skeleton_nodes if node.get("id")})
        return package

    hydrated_ids = set(package.get("hydratedNodeIds", []))
    for node in skeleton_nodes:
        if node.get("loaded") and node.get("id"):
            hydrated_ids.add(node["id"])

    updated_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        if node.get("loaded"):
            updated_nodes.append(node)
            continue
        content = await _generate_story_node_content(
            access_token=access_token,
            opening=opening,
            role=role,
            title=package.get("title", ""),
            skeleton_nodes=skeleton_nodes,
            node=node,
        )
        hydrated_ids.add(node.get("id"))
        updated_nodes.append(
            {
                **node,
                "stageLabel": content.get("stageLabel") or node.get("stageLabel", "剧情推进"),
                "directorNote": content.get("directorNote") or node.get("directorNote", ""),
                "scene": content["scene"],
                "paragraphs": content["paragraphs"],
                "summary": content.get("summary") or node.get("summary", ""),
                "loaded": True,
            }
        )

    package["nodes"] = updated_nodes
    package["hydratedNodeIds"] = sorted(hydrated_ids)
    return _finalize_story_package(package, session_record.get("personaProfile", {}))


async def _generate_story_skeleton(
    access_token: str,
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
) -> dict[str, Any]:
    last_error: HTTPException | None = None
    for attempt in range(3):
        repair_hint = ""
        if last_error is not None:
            detail = last_error.detail if isinstance(last_error.detail, dict) else {"message": str(last_error.detail)}
            reason = detail.get("message", "unknown error")
            count_fix = ""
            if "4 to 7 playable turn nodes" in reason:
                count_fix = "你上一次的 turn 节点数量不对。这次请把整个分支图控制在 4 到 7 个 turn 节点内。"
            elif "exactly 3 ending nodes" in reason:
                count_fix = "你上一次的 ending 节点数量不对。这次必须固定输出 3 个 ending 节点，不要多也不要少。"
            elif "2 to 4 turn nodes" in reason:
                count_fix = "你上一次的单条游玩路径太短或太长了。这次必须让用户在 2 到 4 个 turn 节点后进入结局。"
            repair_hint = f"上一次骨架输出失败，失败原因：{reason}。{count_fix}这次必须修正。"
        prompt = _compose_story_skeleton_prompt(
            opening=opening,
            role=role,
            user_name=user_name,
            persona_profile=persona_profile,
            repair_hint=repair_hint,
        )
        raw_text = await _call_secondme_act(
            access_token=access_token,
            message=f"请为这个故事生成互动骨架：{opening}",
            action_control=prompt,
            max_tokens=4000,
        )
        try:
            return _normalize_story_skeleton(raw_text, opening=opening, role=role)
        except HTTPException as exc:
            print(
                "[story-skeleton-debug]",
                json.dumps(
                    {
                        "attempt": attempt + 1,
                        "opening": opening[:80],
                        "role": role,
                        "error": exc.detail,
                        "raw": raw_text,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_error = exc
    detail = last_error.detail if last_error is not None and isinstance(last_error.detail, dict) else {"message": "Story skeleton generation failed"}
    raise HTTPException(
        status_code=502,
        detail={
            "message": "SecondMe returned an invalid story skeleton after 3 attempts",
            "reason": detail.get("message"),
        },
    )


async def _generate_story_node_content(
    access_token: str,
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
) -> dict[str, Any]:
    last_error: HTTPException | None = None
    for attempt in range(3):
        repair_hint = ""
        if last_error is not None:
            detail = last_error.detail if isinstance(last_error.detail, dict) else {"message": str(last_error.detail)}
            repair_hint = f"上一次节点正文输出失败，失败原因：{detail.get('message', 'unknown error')}。这次必须修正。"
        prompt = _compose_story_node_prompt(
            opening=opening,
            role=role,
            title=title,
            skeleton_nodes=skeleton_nodes,
            node=node,
            repair_hint=repair_hint,
        )
        raw_text = await _call_secondme_act(
            access_token=access_token,
            message=f"请补全节点 {node.get('id')} 的正文",
            action_control=prompt,
            max_tokens=2500,
        )
        try:
            return _normalize_story_node_content(raw_text)
        except HTTPException as exc:
            print(
                "[story-node-debug]",
                json.dumps(
                    {
                        "attempt": attempt + 1,
                        "nodeId": node.get("id"),
                        "role": role,
                        "error": exc.detail,
                        "raw": raw_text,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_error = exc
    detail = last_error.detail if last_error is not None and isinstance(last_error.detail, dict) else {"message": "Story node generation failed"}
    raise HTTPException(
        status_code=502,
        detail={
            "message": f"SecondMe returned invalid node content for {node.get('id')} after 3 attempts",
            "reason": detail.get("message"),
        },
    )


async def _build_story_package_two_stage(
    access_token: str,
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
    hydrate_node_ids: set[str] | None = None,
) -> dict[str, Any]:
    skeleton = await _generate_story_skeleton(
        access_token=access_token,
        opening=opening,
        role=role,
        user_name=user_name,
        persona_profile=persona_profile,
    )
    skeleton_nodes = skeleton.get("nodes", [])
    if hydrate_node_ids is None:
        hydrate_node_ids = {node.get("id") for node in skeleton_nodes if node.get("id")}
    elif not hydrate_node_ids:
        hydrate_node_ids = _initial_hydrate_node_ids(skeleton)
    completed_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        if node.get("id") in hydrate_node_ids:
            content = await _generate_story_node_content(
                access_token=access_token,
                opening=opening,
                role=role,
                title=skeleton.get("title", ""),
                skeleton_nodes=skeleton_nodes,
                node=node,
            )
            completed_nodes.append(
                {
                    **node,
                    "stageLabel": content.get("stageLabel") or node.get("stageLabel", "剧情推进"),
                    "directorNote": content.get("directorNote") or node.get("directorNote", ""),
                    "scene": content["scene"],
                    "paragraphs": content["paragraphs"],
                    "summary": content.get("summary") or node.get("summary", ""),
                    "loaded": True,
                }
            )
        else:
            completed_nodes.append(
                {
                    **node,
                    "scene": "",
                    "paragraphs": [],
                    "loaded": False,
                }
            )
    package = {
        **skeleton,
        "nodes": completed_nodes,
        "hydratedNodeIds": sorted(hydrate_node_ids),
    }
    validation_error = _story_package_validation_error(package)
    if validation_error:
        raise HTTPException(status_code=400, detail={"message": validation_error})
    return _finalize_story_package(package, persona_profile)


def _create_fallback_story_package(opening: str, role: str, persona_profile: dict[str, Any]) -> dict[str, Any]:
    title = get_opening_title(opening) or "未命名互动宇宙"
    opening_summary = get_opening_summary(opening) or opening.split("\n")[0].strip() or opening
    soft_text = "我放轻声音：“你先别躲，我想知道这件事里，你最怕我看见的到底是什么。”"
    tease_text = "我偏头笑了一下：“你把气氛搞得这么暧昧，我要是再装傻，是不是就太不给面子了？”"
    hard_text = "我抬眼盯住他：“既然都把我逼到这一步了，那你就别想再含糊过去。”"

    nodes = [
        {
            "id": "N1",
            "kind": "turn",
            "turn": 1,
            "stageLabel": "第一幕·风暴前夜",
            "directorNote": "局势刚被掀开，你需要决定自己是软接、试探还是硬顶。",
            "scene": (
                f"故事刚从这句开头掀开帘子：{opening_summary}。"
                f"以“{role}”身份站在这场风暴中央的我，已经隐约意识到眼前这段关系并没有表面上那么简单。\n\n"
                "对面的人显然也在等我表态，他没有催促，却把沉默拉得很长，像是在逼我先交底。\n\n"
                "空气里有一点危险，也有一点过分暧昧的预兆。只要我说错一句话，接下来的每一步都会彻底改写走向。"
            ),
            "summary": "故事开场，主角第一次正面碰上真正的关系裂口，必须选定自己的回应方式。",
            "choices": [
                {"id": "N1-C1", "text": soft_text, "nextNodeId": "N2-soft", "style": "soft", "tone": "温柔", "effects": _choice_effects("soft")},
                {"id": "N1-C2", "text": tease_text, "nextNodeId": "N2-tease", "style": "tease", "tone": "撩拨", "effects": _choice_effects("tease")},
                {"id": "N1-C3", "text": hard_text, "nextNodeId": "N2-hard", "style": "confrontation", "tone": "强势", "effects": _choice_effects("confrontation")},
            ],
        },
        {
            "id": "N2-soft",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·软着陆",
            "directorNote": "你让对方稍微放下戒心，但更深的真相也跟着浮上来。",
            "scene": "我先把锋芒收了回来，对方明显愣了一下，像是没料到我会这样温柔。那一瞬间，他眼底压着的委屈竟然比怒气更先冒出来。\n\n他沉默了很久，像是在判断我这次是不是又只是一时兴起。可越是这样，我越能感觉到，这段关系真正危险的地方从来不是争吵，而是那些一直没人说破的真心。\n\n他终于低声开口，说出口的却不是解释，而是一句带着旧伤的反问：如果我现在把真相全告诉你，你还会站在我这边吗？",
            "summary": "温柔路线让对方先露出脆弱，但也逼出了站队问题。",
            "choices": [
                {"id": "N2-soft-C1", "text": "我靠近半步：“你把话说完，我可以先不替自己辩解。”", "nextNodeId": "N3-confession", "style": "support", "tone": "安抚", "effects": _choice_effects("support")},
                {"id": "N2-soft-C2", "text": "我垂下眼睫，故意轻声追问：“所以你一直没走，是舍不得，还是不甘心？”", "nextNodeId": "N3-confession", "style": "tease", "tone": "试探", "effects": _choice_effects("tease")},
                {"id": "N2-soft-C3", "text": "我没有立刻回答，只是先记下他每一次神色变化，想判断他有没有藏更深的事。", "nextNodeId": "N3-secret", "style": "observation", "tone": "克制", "effects": _choice_effects("observation")},
            ],
        },
        {
            "id": "N2-tease",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·暧昧试探",
            "directorNote": "你把局面拉到了更靠近心动的边缘，但也可能让对方以为你仍在玩笑。",
            "scene": "我把语气放得轻快了一点，像是在刀尖上故意转了个圈。对面的人果然被我晃得怔住，呼吸都乱了一瞬。\n\n可这种撩拨式的退让并不完全安全，因为只要我再多装作若无其事一点，他就会重新怀疑我是不是根本不认真。\n\n他看着我，像是在等我接下来到底会继续逗他，还是终于给出一句能落地的话。",
            "summary": "暧昧路线把张力推高，但认真与不认真之间只差一步。",
            "choices": [
                {"id": "N2-tease-C1", "text": "我抬手替他理了一下衣领：“你都快把心事写脸上了，还要我继续猜吗？”", "nextNodeId": "N3-confession", "style": "tease", "tone": "撩拨", "effects": _choice_effects("tease")},
                {"id": "N2-tease-C2", "text": "我忽然认真起来：“如果你愿意说实话，这次我不会再笑着糊弄过去。”", "nextNodeId": "N3-confession", "style": "trust", "tone": "真诚", "effects": _choice_effects("trust")},
                {"id": "N2-tease-C3", "text": "我顺势把话题拐开，想先套出他背后还有没有别人参与。", "nextNodeId": "N3-secret", "style": "strategy", "tone": "心机", "effects": _choice_effects("strategy")},
            ],
        },
        {
            "id": "N2-hard",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·正面冲撞",
            "directorNote": "强势能逼出真相，也可能把关系直接推向悬崖边。",
            "scene": "我没有给他退路，连语气都像是把最后一层遮羞布一起掀开。对面的人被我逼得下颌绷紧，眼神里那点克制终于开始裂开。\n\n他显然也有情绪，只是以前一直在忍。现在被我这样顶着逼问，他反而像是终于找到了失控的理由。\n\n可就在气氛快要彻底炸开的那一刻，我看见他眼底闪过一丝很轻的难过，那不像厌烦，反而像被我伤过太久。", 
            "summary": "强碰强之后，真正暴露出来的可能不是敌意，而是被压久了的感情伤口。",
            "choices": [
                {"id": "N2-hard-C1", "text": "我还是不退：“你可以生气，但你得把理由一字一句说清楚。”", "nextNodeId": "N3-secret", "style": "confrontation", "tone": "强势", "effects": _choice_effects("confrontation")},
                {"id": "N2-hard-C2", "text": "我忽然放缓一点：“如果我真的伤到你，那你至少要让我知道我错在哪。”", "nextNodeId": "N3-confession", "style": "soft", "tone": "松动", "effects": _choice_effects("soft")},
                {"id": "N2-hard-C3", "text": "我盯着他的反应，决定先逼他暴露更多，再决定要不要退。", "nextNodeId": "N3-secret", "style": "manipulation", "tone": "压迫", "effects": _choice_effects("manipulation")},
            ],
        },
        {
            "id": "N3-confession",
            "kind": "turn",
            "turn": 3,
            "stageLabel": "第三幕·真心外露",
            "directorNote": "对方已经快说到心口，接下来要决定你是接住，还是继续追问。",
            "scene": "终于，他像是被我逼到再也装不下去，低声承认自己不是没感觉，而是一直不敢相信我会认真。那些被我忽略过的细节，此刻都突然有了另外一种解释。\n\n他越说越乱，像是把忍了很久的话一次全倒出来。原来这段关系真正卡住的，从来不是谁更会演，而是谁更害怕先承认自己动心。\n\n我听着他呼吸发紧，忽然明白只要再往前半步，故事就会从拉扯转成真正的选择题。", 
            "summary": "对方半告白，感情被端上台面，主角迎来真正的回应节点。",
            "choices": [
                {"id": "N3-confession-C1", "text": "我伸手握住他：“那这次换我认真一点，不让你一个人撑着。”", "nextNodeId": "N4-climax", "style": "trust", "tone": "真诚", "effects": _choice_effects("trust")},
                {"id": "N3-confession-C2", "text": "我弯起眼睛：“你都说到这一步了，再嘴硬就太可惜了吧？”", "nextNodeId": "N4-climax", "style": "tease", "tone": "撩拨", "effects": _choice_effects("tease")},
                {"id": "N3-confession-C3", "text": "我没有立刻接住告白，反而追问他是不是还瞒了我别的真相。", "nextNodeId": "N4-climax", "style": "strategy", "tone": "追查", "effects": _choice_effects("strategy")},
            ],
        },
        {
            "id": "N3-secret",
            "kind": "turn",
            "turn": 3,
            "stageLabel": "第三幕·暗线浮出",
            "directorNote": "局势开始转向反转兑现，你的一念之间会决定这是修罗场还是表白局。",
            "scene": "我没有急着接情绪，而是继续顺着裂缝往下挖。果然，更多没说出口的暗线一点点浮了上来，有误会，也有他刻意替我挡下的麻烦。\n\n越听下去，我越难分清自己现在是生气多一点，还是心软多一点。因为那些被我当成理所当然的纵容，原来全都不是白给。\n\n他见我沉默，像是误会了我的反应，眼神又重新冷下来，仿佛已经做好最坏打算。", 
            "summary": "暗线被翻出，误会与保护并存，故事进入临门一脚的反转前夜。",
            "choices": [
                {"id": "N3-secret-C1", "text": "我忽然上前一步：“你替我挡了这么多事，凭什么现在还想装没发生过？”", "nextNodeId": "N4-climax", "style": "confrontation", "tone": "强压", "effects": _choice_effects("confrontation")},
                {"id": "N3-secret-C2", "text": "我轻声问他：“你做这些，是因为责任，还是因为舍不得我受一点委屈？”", "nextNodeId": "N4-climax", "style": "soft", "tone": "轻问", "effects": _choice_effects("soft")},
                {"id": "N3-secret-C3", "text": "我决定暂时不拆穿全部情绪，先把最后一层关键真相也逼出来。", "nextNodeId": "N4-climax", "style": "manipulation", "tone": "控场", "effects": _choice_effects("manipulation")},
            ],
        },
        {
            "id": "N4-climax",
            "kind": "turn",
            "turn": 4,
            "stageLabel": "第四幕·结局前一秒",
            "directorNote": "你已经走到结局门口，最后一句话会决定这是告白、和解还是擦肩。",
            "scene": "所有误会、暧昧和没说完的话都被推到了最后一秒。眼前的人不再回避，像是把最后的选择权真正交到了我手里。\n\n他看着我，神情里带着一点压不住的紧张，也带着一种“只要你点头我就不退了”的决绝。到这一步，连沉默都像答案。\n\n我知道，只要现在开口，这个宇宙就会被我亲手按向某种结局。", 
            "summary": "结局门打开，最后一句回应决定这段关系会落到哪一种宇宙。",
            "choices": [
                {"id": "N4-C1", "text": "我抱住他，认真承认：“这次轮到我追着你走了。”", "nextNodeId": "E-sweet", "style": "trust", "tone": "告白", "effects": _choice_effects("trust")},
                {"id": "N4-C2", "text": "我抵着他的肩笑：“你先别得意，我们可以从重新认识开始。”", "nextNodeId": "E-slowburn", "style": "tease", "tone": "暧昧", "effects": _choice_effects("tease")},
                {"id": "N4-C3", "text": "我后退半步：“我得先把自己理清楚，今天先到这里。”", "nextNodeId": "E-open", "style": "observation", "tone": "克制", "effects": _choice_effects("observation")},
            ],
        },
        {
            "id": "E-sweet",
            "kind": "ending",
            "turn": 5,
            "stageLabel": "结局·糖分超标",
            "directorNote": "高好感路线达成。",
            "scene": "我抱上去的那一秒，他明显怔住了，随即像是松开了整整一个宇宙的戒备。那些原本会继续拉扯很久的误会，终于在这一刻被真正接住。\n\n他低声笑了一下，像终于等到这句承认太久，连眼底都亮起来。故事没有轰轰烈烈地收尾，却像有人替这段关系轻轻盖了章：从今天开始，我们不再只靠试探相爱。",
            "summary": "你选择直球接住感情，这个宇宙以高好感的双向奔赴收束。",
            "choices": [],
        },
        {
            "id": "E-slowburn",
            "kind": "ending",
            "turn": 5,
            "stageLabel": "结局·暧昧续杯",
            "directorNote": "慢热但极有后劲的结局。",
            "scene": "我没有把话说满，却把退路也留给了彼此。对面的人先是一怔，随后像终于明白我不是拒绝，只是想把这段关系重新写一遍。\n\n他看着我笑，眼底那点紧绷终于慢慢散开。这个宇宙没有立刻官宣式落幕，却像一杯刚刚续上的热饮，知道后劲会越来越长。",
            "summary": "你没有一口气跳进结局，而是选择把关系留在最有余温的慢热区。",
            "choices": [],
        },
        {
            "id": "E-open",
            "kind": "ending",
            "turn": 5,
            "stageLabel": "结局·先把自己找回来",
            "directorNote": "克制路线达成开放式结局。",
            "scene": "我还是给自己留了一步距离。那不是彻底退场，而是终于愿意承认，真正的靠近不能只靠一时上头。\n\n他没有强留，只是看着我点了点头，像在说这一次他愿意把选择权交还给我。于是这个宇宙停在了不算圆满、却足够诚实的位置：如果以后再见，我们会以更清醒的样子重新开始。",
            "summary": "你把关系按在开放式收束上，没有强行圆满，却保住了自己的节奏。",
            "choices": [],
        },
    ]
    story_package = {
        "version": PACKAGE_VERSION,
        "title": title,
        "opening": opening,
        "role": role,
        "rootNodeId": "N1",
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"好感": 0, "信任": 0, "警惕": 0},
            "persona": {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0},
            "turn": 1,
            "endingHint": "",
        },
    }
    return _finalize_story_package(story_package, persona_profile)


def _infer_stage(turn_count: int, status: str) -> str:
    if status == "complete":
        return "ending"
    if turn_count <= 1:
        return "opening"
    if turn_count <= 3:
        return "conflict"
    if turn_count <= 5:
        return "climax" if status != "ending" else "ending"
    return "ending"


def _update_story_state(previous_state: dict[str, Any], action: str, choice_texts: list[str], turn_count: int, status: str) -> dict[str, Any]:
    flags = list(previous_state.get("flags", []))
    relationship = dict(previous_state.get("relationship", {"hero": 0, "villain": 0}))
    persona = dict(previous_state.get("persona", {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0}))
    action_style = _choice_style(action)
    effects = _choice_effects(action_style)

    for key, value in effects.get("persona", {}).items():
        persona[key] = persona.get(key, 0) + value

    if action_style in {"trust", "support"}:
        relationship["hero"] = relationship.get("hero", 0) + 1
        if "trust_path" not in flags:
            flags.append("trust_path")
    if action_style in {"soft", "tease"}:
        relationship["hero"] = relationship.get("hero", 0) + 1
    if action_style in {"confrontation", "risk"}:
        relationship["hero"] = relationship.get("hero", 0) - 1
        relationship["villain"] = relationship.get("villain", 0) - 1
        if "conflict_spike" not in flags:
            flags.append("conflict_spike")
    if action_style in {"strategy", "manipulation", "observation"}:
        if "foreshadowing_seed" not in flags:
            flags.append("foreshadowing_seed")
    if action_style == "manipulation" and "hidden_motive" not in flags:
        flags.append("hidden_motive")
    if any("相信" in choice or "利用" in choice or "揭穿" in choice for choice in choice_texts) and "reversal_ready" not in flags and turn_count >= 3:
        flags.append("reversal_ready")

    stage = _infer_stage(turn_count, status)
    ending_hint = ""
    if stage == "ending" and "trust_path" in flags and "reversal_ready" in flags:
        ending_hint = "曾经建立的信任正在逼近一次反转兑现。"
    elif stage == "ending" and "hidden_motive" in flags:
        ending_hint = "你埋下的隐藏动机正在改变结局走向。"

    return {
        "stage": stage,
        "flags": flags,
        "relationship": relationship,
        "persona": persona,
        "turn": turn_count,
        "endingHint": ending_hint,
    }


def _recent_transcript_window(transcript: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return transcript[-limit:]


def _build_completed_run_from_payload(payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    completed_run = payload.get("completedRun", payload)
    if not isinstance(completed_run, dict):
        raise HTTPException(status_code=400, detail="Missing completedRun payload")
    transcript = completed_run.get("transcript", [])
    if not isinstance(transcript, list):
        transcript = []
    state = completed_run.get("state", {})
    if not isinstance(state, dict):
        state = {}
    ending_node_id = _clean_model_text(completed_run.get("endingNodeId", ""))
    package = session.get("package", {})
    node_map = {node.get("id"): node for node in package.get("nodes", [])}
    ending_node = node_map.get(ending_node_id)
    if not ending_node or ending_node.get("kind") != "ending":
        raise HTTPException(status_code=400, detail="Completed run must point to an ending node")
    return {
        "currentNodeId": ending_node_id,
        "endingNodeId": ending_node_id,
        "summary": _clean_model_text(completed_run.get("summary", "")) or _clean_model_text(ending_node.get("summary", "")),
        "transcript": [
            {
                "turn": item.get("turn"),
                "label": _clean_model_text(item.get("label", "")),
                "text": _clean_model_text(item.get("text", "")),
            }
            for item in transcript
            if isinstance(item, dict) and _clean_model_text(item.get("text", ""))
        ],
        "state": state,
        "path": completed_run.get("path", []),
        "completedAt": int(time.time()),
    }


async def _create_or_reuse_story_package(body: dict[str, Any], server_session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    opening = body.get("opening", "").strip()
    role = body.get("role", "").strip()
    force_regenerate = bool(body.get("forceRegenerate"))
    if not opening or not role:
        raise HTTPException(status_code=400, detail="Missing opening or role")

    user = server_session["user"]
    sessions = _load_sessions()
    if not force_regenerate:
        reusable = _find_reusable_package(sessions, user.get("userId"), opening, role)
        if reusable:
            return reusable, True

    access_token = server_session["token"]["access_token"]
    persona_profile = _derive_persona_profile(user)
    story_package = await _build_story_package_two_stage(
        access_token=access_token,
        opening=opening,
        role=role,
        user_name=user.get("name") or "SecondMe 用户",
        persona_profile=persona_profile,
        hydrate_node_ids=set(),
    )
    all_node_ids = {node.get("id") for node in story_package.get("nodes", []) if node.get("id")}
    hydrated_node_ids = set(story_package.get("hydratedNodeIds", []))

    now = int(time.time())
    session_record = {
        "id": random_urlsafe(10),
        "kind": "story_package",
        "createdAt": now,
        "updatedAt": now,
        "userId": user.get("userId"),
        "status": "ready",
        "packageStatus": "hydrating" if hydrated_node_ids != all_node_ids else "ready",
        "meta": {
            "opening": opening,
            "role": role,
            "author": user.get("name") or "SecondMe 用户",
        },
        "personaProfile": persona_profile,
        "package": story_package,
        "completedRun": None,
    }
    sessions.insert(0, session_record)
    _save_sessions(sessions)
    return session_record, False


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/debug-config")
async def debug_config() -> JSONResponse:
    return JSONResponse(
        {
            "redirect_uri": settings.redirect_uri,
            "frontend_origin": settings.frontend_origin,
            "public_base_url": settings.public_base_url,
            "app_id": settings.secondme_app_id,
        }
    )


@app.get("/integration/manifest.json")
async def integration_manifest(request: Request) -> JSONResponse:
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    manifest = build_integration_manifest(base_url=base_url, app_id=settings.secondme_app_id)
    return JSONResponse(manifest)


@app.get("/api/auth/login")
async def auth_login() -> RedirectResponse:
    _require_env()
    state = random_urlsafe(24)
    params = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": settings.scope,
        "state": state,
    }
    response = RedirectResponse(url=f"{settings.auth_url}?{urlencode(params)}", status_code=302)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600, path=COOKIE_PATH)
    return response


@app.post("/api/auth/exchange")
async def auth_exchange(request: Request) -> JSONResponse:
    _require_env()
    body = await request.json()
    code = body.get("code")
    state = body.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    expected_state = request.cookies.get("oauth_state")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "code": code,
        "redirect_uri": settings.redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            token_response = await client.post(settings.token_url, data=token_payload)
            if token_response.status_code >= 400:
                raise HTTPException(status_code=400, detail={"message": "Token exchange failed", "body": token_response.text})
            token_result = token_response.json()
            token_data = token_result.get("data", token_result)
            access_token = token_data.get("accessToken") or token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail={"message": "Token response missing access token", "body": token_result})

            userinfo_response = await client.get(
                settings.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code >= 400:
                raise HTTPException(status_code=400, detail={"message": "Failed to fetch user info", "body": userinfo_response.text})
            userinfo_result = userinfo_response.json()
            userinfo = userinfo_result.get("data", userinfo_result)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe OAuth API", "error": str(exc)},
        ) from exc

    # Keep the cookie payload small enough for browsers to reliably store it.
    session_user = {
        "userId": userinfo.get("userId"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "avatar": userinfo.get("avatar"),
        "route": userinfo.get("route"),
    }
    session_payload = {
        "iat": int(time.time()),
        "user": session_user,
        "token": {
            "access_token": access_token,
            "refresh_token": token_data.get("refreshToken") or token_data.get("refresh_token"),
            "expires_in": token_data.get("expiresIn") or token_data.get("expires_in"),
            "scope": token_data.get("scope", settings.scope),
        },
    }
    session_token = sign_payload(session_payload, settings.session_secret)

    response = JSONResponse({"ok": True, "user": session_user})
    response.set_cookie("session", session_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7, path=COOKIE_PATH)
    response.delete_cookie("oauth_state", path=COOKIE_PATH)
    return response


@app.get("/api/me")
async def current_user(request: Request) -> JSONResponse:
    _require_env()
    try:
        server_session = _get_server_session(request)
    except HTTPException:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": server_session.get("user", {})})


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie("session", path=COOKIE_PATH)
    response.delete_cookie("oauth_state", path=COOKIE_PATH)
    return response


@app.post("/api/story/start")
async def start_story(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_record, reused = await _create_or_reuse_story_package(body, server_session)

    return JSONResponse(
        {
            "ok": True,
            "session": _serialize_session(session_record),
            "reused": reused,
        }
    )


@app.post("/api/story/preload")
async def preload_story_package(request: Request) -> JSONResponse:
    return await start_story(request)


@app.post("/api/story/regenerate")
async def regenerate_story_package(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_record, _ = await _create_or_reuse_story_package({**body, "forceRegenerate": True}, server_session)
    return JSONResponse({"ok": True, "session": _serialize_session(session_record), "reused": False})


@app.post("/api/story/continue")
async def continue_story(request: Request) -> JSONResponse:
    raise HTTPException(status_code=410, detail="Story continuation has moved to local package playback")


@app.get("/api/story/sessions/{session_id}")
async def get_story_session(session_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    _, story_session, _ = _find_session(session_id, server_session["user"].get("userId"))
    return JSONResponse({"ok": True, "session": _serialize_session(story_session)})


@app.post("/api/story/sessions/{session_id}/hydrate")
async def hydrate_story_session(session_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    sessions, story_session, index = _find_session(session_id, server_session["user"].get("userId"))
    if story_session.get("kind") != "story_package":
        raise HTTPException(status_code=400, detail="Story session does not support hydration")

    package = story_session.get("package", {})
    pending_nodes = [node for node in package.get("nodes", []) if not node.get("loaded")]
    if pending_nodes:
        story_session["package"] = await _hydrate_story_package_nodes(
            session_record=story_session,
            access_token=server_session["token"]["access_token"],
            opening=story_session.get("meta", {}).get("opening", ""),
            role=story_session.get("meta", {}).get("role", ""),
        )
        story_session["updatedAt"] = int(time.time())

    all_node_ids = {node.get("id") for node in story_session.get("package", {}).get("nodes", []) if node.get("id")}
    hydrated_node_ids = set(story_session.get("package", {}).get("hydratedNodeIds", []))
    story_session["packageStatus"] = "ready" if hydrated_node_ids == all_node_ids else "hydrating"
    sessions[index] = story_session
    _save_sessions(sessions)
    return JSONResponse({"ok": True, "session": _serialize_session(story_session)})


@app.post("/api/story/finalize")
async def finalize_story(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_id = body.get("sessionId", "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing sessionId")
    sessions, story_session, index = _find_session(session_id, server_session["user"].get("userId"))
    if story_session.get("kind") == "story_package":
        if body.get("completedRun"):
            story_session["completedRun"] = _build_completed_run_from_payload(body, story_session)
            story_session["status"] = "complete"
            story_session["updatedAt"] = int(time.time())
            sessions[index] = story_session
            _save_sessions(sessions)
        elif not story_session.get("completedRun"):
            raise HTTPException(status_code=400, detail="Missing completed run payload")
    elif story_session.get("status") != "complete":
        story_session["status"] = "complete"
        story_session["updatedAt"] = int(time.time())
        story_session["state"] = _update_story_state(
            story_session.get("state", {}),
            "主动收束剧情",
            [item.get("text", "") for item in story_session.get("choices", [])],
            story_session.get("turnCount", 0),
            "complete",
        )
        sessions[index] = story_session
        _save_sessions(sessions)
    compiled_story = _build_story_from_session(story_session)
    meta = {
        **story_session.get("meta", {}),
        "sessionId": story_session["id"],
        "status": story_session.get("status", "complete"),
    }
    if story_session.get("kind") == "story_package":
        completed_run = story_session.get("completedRun", {})
        meta.update(
            {
                "turnCount": story_session.get("package", {}).get("playableTurnCount", 0),
                "state": completed_run.get("state", {}),
                "summary": completed_run.get("summary", ""),
                "transcript": completed_run.get("transcript", []),
                "endingNodeId": completed_run.get("endingNodeId", ""),
                "packageTitle": story_session.get("package", {}).get("title", ""),
            }
        )
    else:
        meta.update(
            {
                "turnCount": story_session.get("turnCount", 0),
                "state": story_session.get("state", {}),
            }
        )
    return JSONResponse(
        {
            "ok": True,
            "story": compiled_story,
            "meta": meta,
        }
    )


@app.post("/api/story/analyze-ending")
async def analyze_story_ending(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()

    session_id = body.get("sessionId", "").strip()
    story = body.get("story", "")
    meta = body.get("meta", {}) or {}

    if session_id:
        _, story_session, _ = _find_session(session_id, server_session["user"].get("userId"))
        if story_session.get("kind") == "story_package":
            completed_run = story_session.get("completedRun")
            if not completed_run:
                raise HTTPException(status_code=400, detail="Story package is not finished yet")
            opening = story_session.get("meta", {}).get("opening", "")
            summary = completed_run.get("summary", "")
            transcript = completed_run.get("transcript", [])
            state = completed_run.get("state", {})
        else:
            opening = story_session.get("meta", {}).get("opening", "")
            summary = story_session.get("summary", "")
            transcript = story_session.get("transcript", [])
            state = story_session.get("state", {})
    else:
        opening = meta.get("opening", "")
        summary = meta.get("summary", "") or story
        transcript = meta.get("transcript", []) or []
        state = meta.get("state", {}) or {}

    prompt = _compose_ending_analysis_prompt(
        opening=opening,
        summary=summary,
        transcript=transcript,
        state=state,
    )
    analysis = _normalize_ending_analysis(
        await _call_secondme_chat(server_session["token"]["access_token"], prompt)
    )
    return JSONResponse({"ok": True, "analysis": analysis})


@app.post("/api/story/generate")
async def generate_story(request: Request) -> JSONResponse:
    return await start_story(request)


@app.post("/api/story/save")
async def save_story(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    story = body.get("story", "").strip()
    meta = body.get("meta", {})
    if not story:
        raise HTTPException(status_code=400, detail="Missing story")

    stories = _load_stories()
    story_id = random_urlsafe(10)
    record = {
        "id": story_id,
        "createdAt": int(time.time()),
        "userId": server_session["user"].get("userId"),
        "meta": {
            **meta,
            "opening": meta.get("opening", ""),
            "role": meta.get("role", ""),
            "author": meta.get("author") or server_session["user"].get("name") or "SecondMe 用户",
            "sessionId": meta.get("sessionId", ""),
            "turnCount": meta.get("turnCount", 0),
            "status": meta.get("status", ""),
            "state": meta.get("state", {}),
        },
        "story": story,
    }
    stories.insert(0, record)
    _save_stories(stories)
    return JSONResponse({"ok": True, "story": record})


@app.get("/api/stories")
async def list_stories(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    stories = [item for item in _load_stories() if item.get("userId") == user_id]
    return JSONResponse({"ok": True, "stories": stories})


@app.get("/api/stories/{story_id}")
async def get_story(story_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    for item in _load_stories():
        if item.get("id") == story_id and item.get("userId") == user_id:
            return JSONResponse({"ok": True, "story": item})
    raise HTTPException(status_code=404, detail="Story not found")


@app.post("/api/stories/{story_id}/ending-analysis")
async def cache_story_ending_analysis(story_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    analysis = body.get("analysis")
    if not isinstance(analysis, dict):
        raise HTTPException(status_code=400, detail="Missing ending analysis")

    stories = _load_stories()
    user_id = server_session["user"].get("userId")
    for index, item in enumerate(stories):
        if item.get("id") == story_id and item.get("userId") == user_id:
            meta = item.setdefault("meta", {})
            meta["endingAnalysis"] = analysis
            stories[index] = item
            _save_stories(stories)
            return JSONResponse({"ok": True, "story": item})
    raise HTTPException(status_code=404, detail="Story not found")


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    method = body.get("method")
    request_id = body.get("id")

    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "potato-novel-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        )

    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "list_openings",
                            "description": "列出当前推荐的小说开头。",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "generate_story",
                            "description": "根据开头和角色生成短篇小说。需要请求头带 Authorization: Bearer <SecondMe access token>。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "opening": {"type": "string"},
                                    "role": {"type": "string"},
                                    "extra_instruction": {"type": "string"},
                                },
                                "required": ["opening", "role"],
                            },
                        },
                        {
                            "name": "list_saved_stories",
                            "description": "列出当前服务端已保存的小说记录摘要。",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            }
        )

    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "list_openings":
            openings = [
                {
                    "title": get_opening_title(opening),
                    "summary": get_opening_summary(opening),
                    "opening": opening,
                }
                for opening in PRESET_OPENINGS
            ]
            return JSONResponse(_mcp_result(request_id, openings))

        if name == "list_saved_stories":
            stories = [
                {
                    "id": item["id"],
                    "createdAt": item["createdAt"],
                    "title": item["meta"].get("opening", "")[:40],
                    "role": item["meta"].get("role", ""),
                    "author": item["meta"].get("author", ""),
                }
                for item in _load_stories()[:20]
            ]
            return JSONResponse(_mcp_result(request_id, stories))

        if name == "generate_story":
            opening = (arguments.get("opening") or "").strip()
            role = (arguments.get("role") or "").strip()
            extra_instruction = (arguments.get("extra_instruction") or "").strip()
            auth_header = request.headers.get("Authorization", "")
            if not opening or not role:
                return JSONResponse(_mcp_error(request_id, -32602, "Missing opening or role"))
            if not auth_header.startswith("Bearer "):
                return JSONResponse(_mcp_error(request_id, -32001, "Missing Authorization bearer token"))
            access_token = auth_header.replace("Bearer ", "", 1).strip()
            prompt = _compose_story_prompt(opening=opening, role=role, user_name="SecondMe 用户", extra_instruction=extra_instruction)
            story = await _call_secondme_chat(access_token=access_token, prompt=prompt)
            return JSONResponse(_mcp_result(request_id, {"story": story, "opening": opening, "role": role}))

        return JSONResponse(_mcp_error(request_id, -32601, f"Unknown tool: {name}"))

    return JSONResponse(_mcp_error(request_id, -32601, f"Unknown method: {method}"))


def _mcp_result(request_id: Any, payload: Any) -> dict[str, Any]:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": content,
                }
            ]
        },
    }


def _mcp_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        requested = FRONTEND_DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


def _extract_story_from_sse(raw_text: str) -> str:
    chunks: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = httpx.Response(200, content=data).json()
        except Exception:
            continue
        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                chunks.append(content)
    return "".join(chunks)
