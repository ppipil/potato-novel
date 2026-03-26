from __future__ import annotations

import json
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
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORIES_PATH = DATA_DIR / "stories.json"
SESSIONS_PATH = DATA_DIR / "story_sessions.json"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
COOKIE_PATH = "/"

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
        '{"title":"土豆人格标题","romance":"感情向分析","life":"生活向分析","nextUniverseHook":"一句推荐下一个宇宙的钩子"}。\n\n'
        f"故事开头：{opening}\n"
        f"剧情结局摘要：{summary}\n"
        f"玩家实际选择：\n{action_lines or '- 暂无'}\n"
        f"故事状态：{json.dumps(state or {}, ensure_ascii=False)}\n\n"
        "要求："
        "title 要像测试结果名，简短有记忆点；"
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


def _normalize_ending_analysis(raw_text: str) -> dict[str, str]:
    payload = _extract_json_object(raw_text)
    return {
        "title": _clean_model_text(payload.get("title", "")) or "你的土豆人格正在生成中",
        "romance": _clean_model_text(payload.get("romance", "")) or "这局里的你，显然不是随便点点选项的人。",
        "life": _clean_model_text(payload.get("life", "")) or "放到现实生活里，你大概也是那种会把故事过成连续剧的人。",
        "nextUniverseHook": _clean_model_text(payload.get("nextUniverseHook", "")) or "下一本宇宙，也许更适合你的那一面。"
    }


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


def _serialize_session(session: dict[str, Any]) -> dict[str, Any]:
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
    opening = body.get("opening", "").strip()
    role = body.get("role", "").strip()
    if not opening or not role:
        raise HTTPException(status_code=400, detail="Missing opening or role")

    user = server_session["user"]
    access_token = server_session["token"]["access_token"]
    persona_profile = _derive_persona_profile(user)
    prompt = _compose_story_prompt(opening=opening, role=role, user_name=user.get("name") or "SecondMe 用户")
    turn = _normalize_story_turn(await _call_secondme_chat(access_token=access_token, prompt=prompt))
    choice_objects, recommended_choice_id, ai_choice_id = _build_choice_objects(turn["choices"], persona_profile)
    now = int(time.time())
    state = _update_story_state({}, "", turn["choices"], 1, turn["status"])
    session_record = {
        "id": random_urlsafe(10),
        "createdAt": now,
        "updatedAt": now,
        "userId": user.get("userId"),
        "status": turn["status"],
        "turnCount": 1,
        "meta": {
            "opening": opening,
            "role": role,
            "author": user.get("name") or "SecondMe 用户",
        },
        "summary": turn["summary"],
        "currentScene": turn["scene"],
        "paragraphs": turn["paragraphs"],
        "choices": choice_objects,
        "stageLabel": turn["stageLabel"],
        "directorNote": turn["directorNote"],
        "state": state,
        "personaProfile": persona_profile,
        "recommendedChoiceId": recommended_choice_id,
        "aiChoiceId": ai_choice_id,
        "transcript": [
            {"turn": 1, "label": turn["stageLabel"], "text": turn["scene"]},
            *([{"turn": 1, "label": "局势提示", "text": turn["directorNote"]}] if turn["directorNote"] else []),
        ],
    }
    sessions = _load_sessions()
    sessions.insert(0, session_record)
    _save_sessions(sessions)

    return JSONResponse(
        {
            "ok": True,
            "session": _serialize_session(session_record),
        }
    )


@app.post("/api/story/continue")
async def continue_story(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_id = body.get("sessionId", "").strip()
    action = body.get("action", "").strip()
    if not session_id or not action:
        raise HTTPException(status_code=400, detail="Missing sessionId or action")

    sessions, story_session, index = _find_session(session_id, server_session["user"].get("userId"))
    if story_session.get("status") == "complete":
        raise HTTPException(status_code=400, detail="Story session already completed")

    choice_map = {item.get("id"): item.get("text", "") for item in story_session.get("choices", [])}
    action_text = choice_map.get(action, action)
    prompt = _compose_story_turn_prompt(story_session, server_session["user"].get("name") or "SecondMe 用户", action_text)
    turn = _normalize_story_turn(await _call_secondme_chat(server_session["token"]["access_token"], prompt))
    next_turn = int(story_session.get("turnCount", 1)) + 1
    choice_objects, recommended_choice_id, ai_choice_id = _build_choice_objects(turn["choices"], story_session.get("personaProfile", {}))
    story_session["turnCount"] = next_turn
    story_session["updatedAt"] = int(time.time())
    story_session["status"] = turn["status"]
    story_session["summary"] = turn["summary"]
    story_session["currentScene"] = turn["scene"]
    story_session["paragraphs"] = turn["paragraphs"]
    story_session["choices"] = choice_objects
    story_session["stageLabel"] = turn["stageLabel"]
    story_session["directorNote"] = turn["directorNote"]
    story_session["recommendedChoiceId"] = recommended_choice_id
    story_session["aiChoiceId"] = ai_choice_id
    story_session["state"] = _update_story_state(
        story_session.get("state", {}),
        action_text,
        turn["choices"],
        next_turn,
        turn["status"],
    )
    transcript = story_session.setdefault("transcript", [])
    transcript.extend([
        {"turn": next_turn - 1, "label": "玩家行动", "text": action_text},
        {"turn": next_turn, "label": turn["stageLabel"], "text": turn["scene"]},
        *([{"turn": next_turn, "label": "局势提示", "text": turn["directorNote"]}] if turn["directorNote"] else []),
    ])
    story_session["transcript"] = _recent_transcript_window(transcript, limit=18)
    sessions[index] = story_session
    _save_sessions(sessions)
    return JSONResponse({"ok": True, "session": _serialize_session(story_session)})


@app.get("/api/story/sessions/{session_id}")
async def get_story_session(session_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    _, story_session, _ = _find_session(session_id, server_session["user"].get("userId"))
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
    if story_session.get("status") != "complete":
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
    return JSONResponse(
        {
            "ok": True,
            "story": compiled_story,
            "meta": {
                **story_session.get("meta", {}),
                "sessionId": story_session["id"],
                "turnCount": story_session.get("turnCount", 0),
                "status": story_session.get("status", "complete"),
                "state": story_session.get("state", {}),
            },
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
