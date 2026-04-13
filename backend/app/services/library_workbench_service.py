"""隐藏工作台服务：负责节点包规范化、blueprint 兜底与 AI 解析/补写。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Type

MIN_WORKBENCH_CHOICES = 2
MAX_WORKBENCH_CHOICES = 4


def _build_default_workbench_initial_state() -> dict[str, Any]:
    """构造工作台默认初始状态，覆盖常用隐藏变量。"""
    return {
        "stage": "opening",
        "flags": [],
        "relationship": {
            "favor": 0,
            "taiziFavor": 30,
            "chuxiangFavor": 20,
            "peijiFavor": 20,
            "generalFavor": 20,
            "revealRisk": 15,
            "peijiControl": 10,
            "powerBias": 0,
            "darkness": 0,
        },
        "persona": {
            "extrovert_introvert": 0,
            "scheming_naive": 0,
            "optimistic_pessimistic": 0,
        },
        "turn": 1,
        "endingHint": "",
    }


def _compose_workbench_outline_prompt(
    outline: str,
    title_hint: str,
    opening_hint: str,
    role_hint: str,
    repair_hint: str = "",
) -> str:
    """把用户大纲转换为工作流节点所需的模型提示词。"""
    repair_line = f"\n修正要求：{repair_hint.strip()}" if repair_hint.strip() else ""
    return (
        "你是“互动小说工作流解析器”。"
        "任务：把用户提供的大纲，解析成可直接用于可视化工作台编辑的节点图 JSON。"
        "必须返回严格 JSON object，不要 Markdown，不要代码块，不要任何解释。"
        "只允许输出一个 JSON 对象。"
        "JSON 结构："
        '{"title":"书名","opening":"开头","role":"玩家身份","rootNodeId":"N1","nodes":['
        '{"id":"节点ID","kind":"turn 或 ending","turn":1,'
        '"stageLabel":"章节标题","directorNote":"一句局势提示，可写触发条件",'
        '"summary":"节点摘要","scene":"节点正文或简短场景","choiceCount":3,'
        '"choices":[{"id":"选项ID","text":"选项文案","nextNodeId":"目标节点ID","style":"风格","tone":"语气",'
        '"effects":{"persona":{"extrovert_introvert":0},"relationship":{"favor":1}}}]},'
        '{"id":"E-1","kind":"ending","turn":7,"stageLabel":"结局","directorNote":"","summary":"结局摘要","scene":"结局场景","choiceCount":0,"choices":[]}'
        "]}"
        "约束："
        "1) turn 节点的 choiceCount 必须在 2 到 4，choices 数量必须与 choiceCount 一致；"
        "2) ending 节点 choiceCount 必须为 0，choices 必须为空数组；"
        "3) nextNodeId 必须全部指向已存在节点；"
        "4) 至少 3 个 ending 节点；"
        "5) rootNodeId 必须指向第一个 turn 节点；"
        "6) 若大纲有隐藏线/触发条件（例如好感阈值），请写入相关节点的 directorNote；"
        "7) scene 可以先写简版（1-2段），便于后续人工或 AI 细化。"
        f"{repair_line}\n\n"
        f"标题参考：{title_hint or '未命名互动宇宙'}\n"
        f"开头参考：{opening_hint or '请根据大纲生成一个开局场景'}\n"
        f"玩家身份参考：{role_hint or '主人公'}\n"
        f"用户原始大纲：\n{outline}\n"
    )


def _clean_http_error_message(exc: Exception, http_exception_cls: Type[Exception]) -> str:
    """抽取异常里的可读错误信息，便于回填给下一次修复提示。"""
    if isinstance(exc, http_exception_cls):
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("detail") or detail)
        if detail:
            return str(detail)
    return str(exc) or "unknown error"


def _next_available_node_id(existing_ids: set[str], prefix: str) -> str:
    """按前缀生成不重复节点 ID。"""
    index = 1
    while f"{prefix}{index}" in existing_ids:
        index += 1
    return f"{prefix}{index}"


def _ensure_workbench_minimum_structure(
    nodes: list[dict[str, Any]],
    outline: str,
    clean_model_text: Callable[[Any], str],
) -> None:
    """兜底补齐至少一个 turn 与三个 ending，防止解析结果过于残缺。"""
    existing_ids = {clean_model_text(item.get("id", "")) for item in nodes if clean_model_text(item.get("id", ""))}
    turn_nodes = [item for item in nodes if item.get("kind") == "turn"]
    ending_nodes = [item for item in nodes if item.get("kind") == "ending"]

    if not turn_nodes:
        seed_text = clean_model_text(outline).splitlines()[0] if clean_model_text(outline) else "主角被迫在冲突中做出第一步选择。"
        root_id = "N1"
        if root_id in existing_ids:
            root_id = _next_available_node_id(existing_ids, "N")
        nodes.insert(
            0,
            {
                "id": root_id,
                "kind": "turn",
                "turn": 1,
                "stageLabel": "开局",
                "directorNote": "AI 兜底节点：请按真实大纲补写。",
                "summary": seed_text or "开局冲突",
                "scene": seed_text or "主角意识到局势正在失控。",
                "choiceCount": 3,
                "choices": [],
            },
        )
        existing_ids.add(root_id)
        turn_nodes = [nodes[0]]

    max_turn = 1
    for item in nodes:
        try:
            max_turn = max(max_turn, int(item.get("turn", 1)))
        except (TypeError, ValueError):
            continue

    while len(ending_nodes) < 3:
        ending_id = _next_available_node_id(existing_ids, "E-auto-")
        existing_ids.add(ending_id)
        max_turn += 1
        ending = {
            "id": ending_id,
            "kind": "ending",
            "turn": max_turn,
            "stageLabel": "结局",
            "directorNote": "AI 自动补齐结局节点",
            "summary": "可在工作台中继续细化该结局。",
            "scene": "故事在这里进入收束分支。",
            "choiceCount": 0,
            "choices": [],
        }
        nodes.append(ending)
        ending_nodes.append(ending)


def _workbench_choice_prompt_label(style: str) -> str:
    """为工作台补齐 choice blueprint 的提示标签。"""
    mapping = {
        "soft": "软接情绪",
        "support": "安抚支持",
        "trust": "认真接住",
        "tease": "带笑试探",
        "confrontation": "直接掀桌",
        "observation": "先稳住局势",
        "strategy": "试探布局",
        "manipulation": "强控节奏",
        "risk": "冒险推进",
    }
    return mapping.get(style, "推进剧情")


def _clamp_workbench_choice_count(raw_value: Any, fallback: int = 3) -> int:
    """把工作台节点 choice 数量限制在允许范围内。"""
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = fallback
    if parsed < MIN_WORKBENCH_CHOICES:
        return MIN_WORKBENCH_CHOICES
    if parsed > MAX_WORKBENCH_CHOICES:
        return MAX_WORKBENCH_CHOICES
    return parsed


def _normalize_workbench_nodes(
    story_package: dict[str, Any],
    clean_model_text: Callable[[Any], str],
    choice_style: Callable[[str], str],
    choice_tone: Callable[[str, str], str],
    normalize_choice_effect_payload: Callable[[Any, str, Callable[[Any], str]], dict[str, dict[str, int]]],
    http_exception_cls: Type[Exception],
) -> list[dict[str, Any]]:
    """规范化工作台传入的节点数组，保证后续 AI 补写链路可用。"""
    raw_nodes = story_package.get("nodes", [])
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise http_exception_cls(status_code=400, detail="Workbench package must contain nodes")

    normalized_nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = clean_model_text(raw_node.get("id", f"N{index}")) or f"N{index}"
        kind = clean_model_text(raw_node.get("kind", "turn")).lower()
        if kind not in {"turn", "ending"}:
            kind = "turn"

        turn_raw = raw_node.get("turn", index)
        try:
            turn = int(turn_raw)
        except (TypeError, ValueError):
            turn = index

        stage_label = clean_model_text(raw_node.get("stageLabel", "")) or ("结局" if kind == "ending" else "剧情推进")
        summary = clean_model_text(raw_node.get("summary", ""))
        scene = clean_model_text(raw_node.get("scene", ""))
        director_note = clean_model_text(raw_node.get("directorNote", ""))
        beat = clean_model_text(raw_node.get("beat", ""))
        path_summary = clean_model_text(raw_node.get("pathSummary", ""))
        ending_type = clean_model_text(raw_node.get("endingType", ""))

        choices_raw = raw_node.get("choices", [])
        if not isinstance(choices_raw, list):
            choices_raw = []

        desired_choice_count = _clamp_workbench_choice_count(
            raw_node.get("choiceCount"),
            len(choices_raw) if choices_raw else 3,
        )

        choices: list[dict[str, Any]] = []
        if kind == "turn":
            for choice_index, raw_choice in enumerate(choices_raw[:desired_choice_count], start=1):
                source_choice = raw_choice if isinstance(raw_choice, dict) else {}
                text = clean_model_text(source_choice.get("text", ""))
                next_node_id = clean_model_text(source_choice.get("nextNodeId", ""))
                style = clean_model_text(source_choice.get("style", ""))
                if not style:
                    style = choice_style(text) if text else "dialogue"
                tone = clean_model_text(source_choice.get("tone", "")) or choice_tone(text or "我先顺着局势回应。", style)
                choices.append(
                    {
                        "id": clean_model_text(source_choice.get("id", f"{node_id}-C{choice_index}")) or f"{node_id}-C{choice_index}",
                        "text": text,
                        "nextNodeId": next_node_id,
                        "style": style,
                        "tone": tone,
                        "effects": normalize_choice_effect_payload(source_choice.get("effects"), style, clean_model_text),
                    }
                )

        normalized_node = {
            "id": node_id,
            "kind": kind,
            "turn": turn,
            "stageLabel": stage_label,
            "summary": summary,
            "scene": scene,
            "directorNote": director_note,
            "choiceCount": desired_choice_count if kind == "turn" else 0,
            "choices": choices if kind == "turn" else [],
        }
        if beat:
            normalized_node["beat"] = beat
        if path_summary:
            normalized_node["pathSummary"] = path_summary
        if ending_type:
            normalized_node["endingType"] = ending_type
        choice_blueprints = raw_node.get("choiceBlueprints")
        if isinstance(choice_blueprints, list):
            normalized_node["choiceBlueprints"] = [item for item in choice_blueprints if isinstance(item, dict)]

        normalized_nodes.append(normalized_node)

    if not normalized_nodes:
        raise http_exception_cls(status_code=400, detail="Workbench package must contain valid node objects")

    story_package["nodes"] = normalized_nodes
    return normalized_nodes


def _build_workbench_choice_blueprints(
    node: dict[str, Any],
    all_node_ids: list[str],
    desired_choice_count: int,
    clean_model_text: Callable[[Any], str],
    choice_style: Callable[[str], str],
    choice_tone: Callable[[str, str], str],
    choice_effects: Callable[[str], dict[str, dict[str, int]]],
    fallback_choice_by_index: Callable[[int, str], str],
) -> list[dict[str, Any]]:
    """为手工节点构造可被生成器消费的 choice blueprints。"""
    node_id = clean_model_text(node.get("id", "")) or "N1"
    existing_choices = node.get("choices", [])
    if not isinstance(existing_choices, list):
        existing_choices = []

    fallback_targets = [candidate for candidate in all_node_ids if candidate and candidate != node_id]
    if not fallback_targets:
        fallback_targets = [node_id]

    blueprints: list[dict[str, Any]] = []
    for index in range(desired_choice_count):
        source_choice = existing_choices[index] if index < len(existing_choices) and isinstance(existing_choices[index], dict) else {}
        text = clean_model_text(source_choice.get("text", "")) or fallback_choice_by_index(index, node.get("summary") or node.get("scene", ""))
        style = clean_model_text(source_choice.get("style", "")) or choice_style(text)
        tone = clean_model_text(source_choice.get("tone", "")) or choice_tone(text, style)
        next_node_id = clean_model_text(source_choice.get("nextNodeId", ""))
        if next_node_id not in all_node_ids:
            next_node_id = fallback_targets[index % len(fallback_targets)]
        blueprints.append(
            {
                "id": clean_model_text(source_choice.get("id", f"{node_id}-C{index + 1}")) or f"{node_id}-C{index + 1}",
                "strategy": style,
                "promptLabel": _workbench_choice_prompt_label(style),
                "fallbackText": text,
                "nextNodeId": next_node_id,
                "style": style,
                "tone": tone,
                "effects": choice_effects(style),
            }
        )
    return blueprints


def _ensure_workbench_turn_choices(
    node: dict[str, Any],
    all_node_ids: list[str],
    clean_model_text: Callable[[Any], str],
    choice_style: Callable[[str], str],
    choice_tone: Callable[[str, str], str],
    normalize_choice_effect_payload: Callable[[Any, str, Callable[[Any], str]], dict[str, dict[str, int]]],
    choice_effects: Callable[[str], dict[str, dict[str, int]]],
    fallback_choice_by_index: Callable[[int, str], str],
) -> None:
    """保证工作台 turn 节点始终有可用 choices 与 blueprints。"""
    if node.get("kind") != "turn":
        node["choices"] = []
        return

    desired_choice_count = _clamp_workbench_choice_count(
        node.get("choiceCount"),
        len(node.get("choices", [])) if isinstance(node.get("choices"), list) else 3,
    )
    blueprints = node.get("choiceBlueprints")
    if not isinstance(blueprints, list) or len(blueprints) != desired_choice_count:
        blueprints = _build_workbench_choice_blueprints(
            node=node,
            all_node_ids=all_node_ids,
            desired_choice_count=desired_choice_count,
            clean_model_text=clean_model_text,
            choice_style=choice_style,
            choice_tone=choice_tone,
            choice_effects=choice_effects,
            fallback_choice_by_index=fallback_choice_by_index,
        )
    else:
        repaired_blueprints: list[dict[str, Any]] = []
        for index, blueprint in enumerate(blueprints[:desired_choice_count], start=1):
            candidate = blueprint if isinstance(blueprint, dict) else {}
            next_node_id = clean_model_text(candidate.get("nextNodeId", ""))
            if next_node_id not in all_node_ids:
                fallback_targets = [item for item in all_node_ids if item and item != node.get("id")]
                if not fallback_targets:
                    fallback_targets = [node.get("id")]
                next_node_id = fallback_targets[(index - 1) % len(fallback_targets)]
            fallback_text = clean_model_text(candidate.get("fallbackText", "")) or fallback_choice_by_index(index - 1, node.get("summary") or node.get("scene", ""))
            style = clean_model_text(candidate.get("style", "")) or choice_style(fallback_text)
            repaired_blueprints.append(
                {
                    "id": clean_model_text(candidate.get("id", f"{node.get('id')}-C{index}")) or f"{node.get('id')}-C{index}",
                    "strategy": clean_model_text(candidate.get("strategy", "")) or style,
                    "promptLabel": clean_model_text(candidate.get("promptLabel", "")) or _workbench_choice_prompt_label(style),
                    "fallbackText": fallback_text,
                    "nextNodeId": next_node_id,
                    "style": style,
                    "tone": clean_model_text(candidate.get("tone", "")) or choice_tone(fallback_text, style),
                    "effects": normalize_choice_effect_payload(candidate.get("effects"), style, clean_model_text),
                }
            )
        blueprints = repaired_blueprints

    node["choiceCount"] = desired_choice_count
    node["choiceBlueprints"] = blueprints

    existing_choices = node.get("choices", [])
    if not isinstance(existing_choices, list):
        existing_choices = []

    normalized_choices: list[dict[str, Any]] = []
    for index, blueprint in enumerate(blueprints[:desired_choice_count], start=1):
        source_choice = existing_choices[index - 1] if index - 1 < len(existing_choices) and isinstance(existing_choices[index - 1], dict) else {}
        text = clean_model_text(source_choice.get("text", "")) or clean_model_text(blueprint.get("fallbackText", "")) or fallback_choice_by_index(index - 1, node.get("summary") or node.get("scene", ""))
        next_node_id = clean_model_text(source_choice.get("nextNodeId", "")) or clean_model_text(blueprint.get("nextNodeId", ""))
        if next_node_id not in all_node_ids:
            fallback_targets = [item for item in all_node_ids if item and item != node.get("id")]
            if not fallback_targets:
                fallback_targets = [node.get("id")]
            next_node_id = fallback_targets[(index - 1) % len(fallback_targets)]
        style = clean_model_text(source_choice.get("style", "")) or clean_model_text(blueprint.get("style", "")) or choice_style(text)
        tone = clean_model_text(source_choice.get("tone", "")) or clean_model_text(blueprint.get("tone", "")) or choice_tone(text, style)
        normalized_choices.append(
            {
                "id": clean_model_text(source_choice.get("id", "")) or clean_model_text(blueprint.get("id", "")) or f"{node.get('id')}-C{index}",
                "text": text,
                "nextNodeId": next_node_id,
                "style": style,
                "tone": tone,
                "effects": normalize_choice_effect_payload(source_choice.get("effects") or blueprint.get("effects"), style, clean_model_text),
            }
        )
    node["choices"] = normalized_choices


async def ai_parse_workbench_outline(
    server_session: dict[str, Any],
    body: dict[str, Any],
    clean_model_text: Callable[[Any], str],
    has_volcengine_prose_provider: Callable[[], bool],
    call_volcengine_prose: Callable[..., Any],
    call_secondme_act: Callable[..., Any],
    extract_json_object: Callable[[str], dict[str, Any]],
    choice_style: Callable[[str], str],
    choice_tone: Callable[[str, str], str],
    choice_effects: Callable[[str], dict[str, dict[str, int]]],
    fallback_choice_by_index: Callable[[int, str], str],
    normalize_choice_effect_payload: Callable[[Any, str, Callable[[Any], str]], dict[str, dict[str, int]]],
    package_version: int,
    template_package_generator: str,
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """把自由文本剧情大纲解析为可编辑的工作台 story package。"""
    outline = clean_model_text(body.get("outline", ""))
    if not outline:
        raise http_exception_cls(status_code=400, detail="Missing outline text")

    raw_package = body.get("package")
    base_package = deepcopy(raw_package) if isinstance(raw_package, dict) else {}

    requested_provider = clean_model_text(body.get("provider", "volcengine")).lower()
    provider = "secondme" if requested_provider == "secondme" else "volcengine"
    access_token = server_session.get("token", {}).get("access_token")
    if provider == "volcengine" and not has_volcengine_prose_provider():
        provider = "secondme"
    if provider == "secondme" and not access_token:
        if has_volcengine_prose_provider():
            provider = "volcengine"
        else:
            raise http_exception_cls(status_code=500, detail="SecondMe access token is required for outline parsing")

    title_hint = clean_model_text(body.get("title", "")) or clean_model_text(base_package.get("title", "")) or "未命名互动宇宙"
    opening_hint = clean_model_text(body.get("opening", "")) or clean_model_text(base_package.get("opening", "")) or title_hint
    role_hint = clean_model_text(body.get("role", "")) or clean_model_text(base_package.get("role", "")) or "主人公"

    last_error: Exception | None = None
    parsed_payload: dict[str, Any] | None = None
    for attempt in range(3):
        repair_hint = ""
        if last_error is not None:
            repair_hint = (
                f"上一次输出无法解析或结构非法，原因：{_clean_http_error_message(last_error, http_exception_cls)}。"
                "这次请严格返回合法 JSON，并确保 nodes/choices/nextNodeId 全部有效。"
            )
        prompt = _compose_workbench_outline_prompt(
            outline=outline,
            title_hint=title_hint,
            opening_hint=opening_hint,
            role_hint=role_hint,
            repair_hint=repair_hint,
        )
        try:
            if provider == "volcengine":
                raw_text = await call_volcengine_prose(prompt=prompt, max_tokens=2800)
            else:
                raw_text = await call_secondme_act(
                    access_token=access_token,
                    message="请把剧情大纲解析成互动小说工作流 JSON",
                    action_control=prompt,
                    max_tokens=3200,
                )
            candidate = extract_json_object(raw_text)
            if not isinstance(candidate, dict):
                raise http_exception_cls(status_code=400, detail="Outline parser result must be JSON object")
            parsed_payload = candidate.get("package") if isinstance(candidate.get("package"), dict) else candidate
            if not isinstance(parsed_payload, dict):
                raise http_exception_cls(status_code=400, detail="Outline parser payload is invalid")
            if not isinstance(parsed_payload.get("nodes"), list):
                raise http_exception_cls(status_code=400, detail="Outline parser payload missing nodes")
            break
        except Exception as exc:  # noqa: BLE001 - 这里需要统一重试所有解析失败
            last_error = exc
            parsed_payload = None

    if not isinstance(parsed_payload, dict):
        reason = _clean_http_error_message(last_error or Exception("parse failed"), http_exception_cls)
        raise http_exception_cls(
            status_code=502,
            detail={
                "message": "AI outline parsing failed after 3 attempts",
                "reason": reason,
            },
        )

    story_package = deepcopy(base_package)
    story_package["title"] = clean_model_text(body.get("title", "")) or clean_model_text(parsed_payload.get("title", "")) or title_hint
    story_package["opening"] = clean_model_text(body.get("opening", "")) or clean_model_text(parsed_payload.get("opening", "")) or opening_hint
    story_package["role"] = clean_model_text(body.get("role", "")) or clean_model_text(parsed_payload.get("role", "")) or role_hint
    story_package["version"] = int(story_package.get("version") or package_version)
    story_package["generatedBy"] = "library_workbench_outline_parser_v1"
    story_package["nodes"] = parsed_payload.get("nodes", [])

    parsed_initial_state = parsed_payload.get("initialState")
    base_initial_state = base_package.get("initialState")
    default_initial_state = _build_default_workbench_initial_state()
    if isinstance(base_initial_state, dict):
        default_initial_state.update(base_initial_state)
    if isinstance(parsed_initial_state, dict):
        merged_relationship = dict(default_initial_state.get("relationship", {}))
        merged_relationship.update(parsed_initial_state.get("relationship", {}) if isinstance(parsed_initial_state.get("relationship"), dict) else {})
        merged_persona = dict(default_initial_state.get("persona", {}))
        merged_persona.update(parsed_initial_state.get("persona", {}) if isinstance(parsed_initial_state.get("persona"), dict) else {})
        default_initial_state.update(parsed_initial_state)
        default_initial_state["relationship"] = merged_relationship
        default_initial_state["persona"] = merged_persona
    story_package["initialState"] = default_initial_state

    nodes = _normalize_workbench_nodes(
        story_package=story_package,
        clean_model_text=clean_model_text,
        choice_style=choice_style,
        choice_tone=choice_tone,
        normalize_choice_effect_payload=normalize_choice_effect_payload,
        http_exception_cls=http_exception_cls,
    )
    _ensure_workbench_minimum_structure(nodes, outline=outline, clean_model_text=clean_model_text)

    all_node_ids = [item.get("id") for item in nodes if item.get("id")]
    if not all_node_ids:
        raise http_exception_cls(status_code=400, detail="Workbench package has no valid node IDs")

    turn_nodes = [item for item in nodes if item.get("kind") == "turn"]
    for candidate in turn_nodes:
        _ensure_workbench_turn_choices(
            node=candidate,
            all_node_ids=all_node_ids,
            clean_model_text=clean_model_text,
            choice_style=choice_style,
            choice_tone=choice_tone,
            normalize_choice_effect_payload=normalize_choice_effect_payload,
            choice_effects=choice_effects,
            fallback_choice_by_index=fallback_choice_by_index,
        )

    sorted_turns = sorted(
        turn_nodes,
        key=lambda item: (int(item.get("turn", 1)) if isinstance(item.get("turn"), int) or str(item.get("turn", "")).isdigit() else 1, str(item.get("id", ""))),
    )
    root_candidate = clean_model_text(parsed_payload.get("rootNodeId", ""))
    if root_candidate in {item.get("id") for item in turn_nodes}:
        story_package["rootNodeId"] = root_candidate
    elif sorted_turns:
        story_package["rootNodeId"] = sorted_turns[0].get("id") or all_node_ids[0]
    else:
        story_package["rootNodeId"] = all_node_ids[0]

    turn_count = len(turn_nodes)
    ending_count = len([item for item in nodes if item.get("kind") == "ending"])
    return {
        "package": story_package,
        "provider": provider,
        "generated": {
            "turnNodes": turn_count,
            "endingNodes": ending_count,
            "totalNodes": len(nodes),
        },
    }


async def ai_complete_workbench_node(
    server_session: dict[str, Any],
    body: dict[str, Any],
    clean_model_text: Callable[[Any], str],
    has_volcengine_prose_provider: Callable[[], bool],
    generate_story_node_choices: Callable[..., Any],
    generate_story_node_content: Callable[..., Any],
    choice_style: Callable[[str], str],
    choice_tone: Callable[[str, str], str],
    choice_effects: Callable[[str], dict[str, dict[str, int]]],
    fallback_choice_by_index: Callable[[int, str], str],
    normalize_choice_effect_payload: Callable[[Any, str, Callable[[Any], str]], dict[str, dict[str, int]]],
    package_version: int,
    template_package_generator: str,
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """为隐藏工作台补写单节点（正文/选项/全部）。"""
    raw_package = body.get("package")
    if not isinstance(raw_package, dict):
        raise http_exception_cls(status_code=400, detail="Missing workbench package")

    node_id = clean_model_text(body.get("nodeId", ""))
    if not node_id:
        raise http_exception_cls(status_code=400, detail="Missing nodeId")

    mode = clean_model_text(body.get("mode", "both")).lower()
    if mode not in {"scene", "choices", "both"}:
        mode = "both"

    requested_provider = clean_model_text(body.get("provider", "volcengine")).lower()
    provider = "secondme" if requested_provider == "secondme" else "volcengine"
    if provider == "volcengine" and not has_volcengine_prose_provider():
        provider = "secondme"

    story_package = deepcopy(raw_package)
    story_package["title"] = clean_model_text(body.get("title", "")) or clean_model_text(story_package.get("title", "")) or "未命名互动宇宙"
    story_package["opening"] = clean_model_text(body.get("opening", "")) or clean_model_text(story_package.get("opening", "")) or story_package["title"]
    story_package["role"] = clean_model_text(body.get("role", "")) or clean_model_text(story_package.get("role", "")) or "主人公"
    story_package["version"] = int(story_package.get("version") or package_version)
    story_package["generatedBy"] = clean_model_text(story_package.get("generatedBy", "")) or template_package_generator

    nodes = _normalize_workbench_nodes(
        story_package=story_package,
        clean_model_text=clean_model_text,
        choice_style=choice_style,
        choice_tone=choice_tone,
        normalize_choice_effect_payload=normalize_choice_effect_payload,
        http_exception_cls=http_exception_cls,
    )

    all_node_ids = [item.get("id") for item in nodes if item.get("id")]
    if not all_node_ids:
        raise http_exception_cls(status_code=400, detail="Workbench package has no valid node IDs")

    if clean_model_text(story_package.get("rootNodeId", "")) not in all_node_ids:
        story_package["rootNodeId"] = all_node_ids[0]

    node_map = {item.get("id"): item for item in nodes if item.get("id")}
    node = node_map.get(node_id)
    if not node:
        raise http_exception_cls(status_code=404, detail=f"Node not found: {node_id}")

    for candidate in nodes:
        if candidate.get("kind") == "turn":
            _ensure_workbench_turn_choices(
                node=candidate,
                all_node_ids=all_node_ids,
                clean_model_text=clean_model_text,
                choice_style=choice_style,
                choice_tone=choice_tone,
                normalize_choice_effect_payload=normalize_choice_effect_payload,
                choice_effects=choice_effects,
                fallback_choice_by_index=fallback_choice_by_index,
            )

    if mode in {"choices", "both"}:
        if node.get("kind") != "turn":
            raise http_exception_cls(status_code=400, detail="Ending node has no choices to generate")
        if int(node.get("choiceCount") or 3) != 3:
            raise http_exception_cls(
                status_code=400,
                detail="AI choice completion currently supports nodes with exactly 3 choices",
            )
        generated_choices = await generate_story_node_choices(
            access_token=server_session.get("token", {}).get("access_token"),
            opening=story_package["opening"],
            role=story_package["role"],
            title=story_package["title"],
            skeleton_nodes=nodes,
            node=node,
            provider=provider,
            phase_nodes=[node_id],
        )
        node["choices"] = generated_choices
        _ensure_workbench_turn_choices(
            node=node,
            all_node_ids=all_node_ids,
            clean_model_text=clean_model_text,
            choice_style=choice_style,
            choice_tone=choice_tone,
            normalize_choice_effect_payload=normalize_choice_effect_payload,
            choice_effects=choice_effects,
            fallback_choice_by_index=fallback_choice_by_index,
        )

    if mode in {"scene", "both"}:
        generated_content = await generate_story_node_content(
            access_token=server_session.get("token", {}).get("access_token"),
            opening=story_package["opening"],
            role=story_package["role"],
            title=story_package["title"],
            skeleton_nodes=nodes,
            node=node,
            provider=provider,
            phase_nodes=[node_id],
        )
        node.update(generated_content)

    return {
        "package": story_package,
        "nodeId": node_id,
        "node": node,
        "mode": mode,
        "provider": provider,
        "generated": {
            "scene": mode in {"scene", "both"},
            "choices": mode in {"choices", "both"} and node.get("kind") == "turn",
        },
    }
