"""故事包领域辅助模块，负责 story package 的结构规则、选项属性与 runtime 辅助计算。"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional


def build_story_package_node_map(story_package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """按节点 ID 建立 story package 的节点索引。"""
    return {node.get("id"): node for node in story_package.get("nodes", []) if node.get("id")}


def build_runtime_entries_for_node(node: dict[str, Any], clean_model_text: Callable[[str], str]) -> list[dict[str, Any]]:
    """根据节点内容构造 runtime 初始展示条目。"""
    entries = [
        {"turn": node.get("turn"), "label": node.get("stageLabel"), "text": node.get("scene", "")},
    ]
    director_note = clean_model_text(node.get("directorNote", ""))
    if director_note:
        entries.append({"turn": node.get("turn"), "label": "局势提示", "text": director_note})
    return entries


def choice_style(choice: str) -> str:
    """根据选项文案粗略推断其风格标签。"""
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


def choice_tone(choice: str, style: str) -> str:
    """根据风格映射出更适合展示的语气标签。"""
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


def choice_effects(style: str) -> dict[str, dict[str, int]]:
    """根据选项风格生成默认的人格与关系数值影响。"""
    persona_effect = {
        "extrovert_introvert": 0,
        "scheming_naive": 0,
        "optimistic_pessimistic": 0,
    }
    relationship_effect = {"favor": 0}

    if style in {"soft", "support", "trust"}:
        persona_effect["extrovert_introvert"] += 1
        persona_effect["optimistic_pessimistic"] += 1
        relationship_effect["favor"] += 1
    elif style == "tease":
        persona_effect["extrovert_introvert"] += 1
        relationship_effect["favor"] += 1
    elif style == "confrontation":
        persona_effect["extrovert_introvert"] += 1
        persona_effect["optimistic_pessimistic"] -= 1
        relationship_effect["favor"] -= 1
    elif style in {"strategy", "manipulation"}:
        persona_effect["scheming_naive"] += 1
        relationship_effect["favor"] -= 1
    elif style == "observation":
        persona_effect["extrovert_introvert"] -= 1
        persona_effect["scheming_naive"] += 1
    elif style == "risk":
        persona_effect["extrovert_introvert"] += 1
        persona_effect["optimistic_pessimistic"] -= 1

    return {
        "persona": {key: value for key, value in persona_effect.items() if value},
        "relationship": {key: value for key, value in relationship_effect.items() if value},
    }


def normalize_choice_effect_payload(payload: Any, fallback_style: str, clean_model_text: Callable[[str], str]) -> dict[str, dict[str, int]]:
    """规范化选项 effects，并在缺失时按风格补默认值。"""
    normalized = {"persona": {}, "relationship": {}}
    if isinstance(payload, dict):
        for category in ("persona", "relationship"):
            category_payload = payload.get(category, {})
            if isinstance(category_payload, dict):
                normalized[category] = {
                    clean_model_text(key): int(value)
                    for key, value in category_payload.items()
                    if clean_model_text(key) and isinstance(value, (int, float))
                }
    fallback = choice_effects(fallback_style)
    for category in ("persona", "relationship"):
        if not normalized[category]:
            normalized[category] = fallback.get(category, {})
    return normalized


def fallback_choice_by_index(index: int, scene: str) -> str:
    """按位置返回一个兜底选项文案。"""
    normalized_scene = re.sub(r"\s+", "", str(scene or ""))
    scene_hint = normalized_scene[:10] if normalized_scene else "眼前这局面"
    fallbacks = [
        f"我压低声音看着{scene_hint}：「你先别躲，把话说清楚。」",
        f"我弯起眼睛试探他：「都到{scene_hint}这一步了，你还想让我装没看见？」",
        f"我没有立刻接话，只盯着{scene_hint}往前半步，逼他先把底牌亮出来。",
    ]
    if 0 <= index < len(fallbacks):
        return fallbacks[index]
    return f"我顺着眼前的局势轻声说出第 {index + 1} 种回应，试探他的真实态度。"


def ensure_distinct_choices(choices: list[str], scene: str = "") -> list[str]:
    """尽量保证三个选项在风格上彼此不同。"""
    distinct: list[str] = []
    seen_styles = set()
    fallback_by_style = {
        "confrontation": "我盯着他的眼睛，半点没退：“你要是真想瞒我，就不会露出这种表情。现在，告诉我实话。”",
        "soft": "我放轻声音：“你可以不马上解释清楚，但至少别把我推开。让我陪你一起面对。”",
        "tease": "我偏头笑了一下：“原来你也会紧张？那我是不是该重新认识一下你了？”",
    }
    ordered_styles = ["confrontation", "soft", "tease"]

    for choice in choices:
        style = choice_style(choice)
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
        distinct.append(fallback_choice_by_index(len(distinct), scene))
    return distinct[:3]


def infer_stage_from_turn(turn_count: int, total_turns: int, kind: str) -> str:
    """根据节点回合数推断它在整局中的戏剧阶段。"""
    if kind == "ending":
        return "ending"
    if turn_count <= 1:
        return "opening"
    if turn_count >= max(total_turns - 1, 3):
        return "climax"
    return "conflict"


def build_choice_objects(choice_texts: list[str], persona_profile: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    """把纯文本选项补齐成前端可直接展示的完整对象。"""
    preferred_styles = persona_profile.get("preferredStyles", [])
    choice_objects = []
    recommended_choice_id = None

    for index, text in enumerate(choice_texts, start=1):
        style = choice_style(text)
        choice_id = f"C{index}"
        choice = {
            "id": choice_id,
            "text": text,
            "style": style,
            "tone": choice_tone(text, style),
            "effects": choice_effects(style),
            "isRecommended": False,
            "isAiChoice": False,
        }
        if recommended_choice_id is None and (style in preferred_styles or (style == "soft" and "support" in preferred_styles)):
            recommended_choice_id = choice_id
        choice_objects.append(choice)

    if recommended_choice_id is None and choice_objects:
        recommended_choice_id = choice_objects[0]["id"]

    for choice in choice_objects:
        if choice["id"] == recommended_choice_id:
            choice["isRecommended"] = True
            choice["isAiChoice"] = True
    return choice_objects, recommended_choice_id or "", recommended_choice_id or ""


def finalize_story_package(
    story_package: dict[str, Any],
    persona_profile: dict[str, Any],
    clean_model_text: Callable[[str], str],
    package_version: int,
    template_package_generator: str,
    story_generation_debug_metadata: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """为故事包补齐推荐信息、阶段信息和调试元数据。"""
    story_package["version"] = package_version
    story_package["generatedBy"] = template_package_generator
    story_package["debug"] = story_generation_debug_metadata()
    nodes = story_package.get("nodes", [])
    node_map = {node["id"]: node for node in nodes}
    playable_count = sum(1 for node in nodes if node.get("kind") == "turn")
    for node in nodes:
        if node.get("kind") != "turn":
            continue
        raw_choices = node.get("choices", [])
        if not raw_choices:
            continue
        choice_payloads = [choice.get("text", "") for choice in raw_choices]
        recommendation_basis, _, _ = build_choice_objects(choice_payloads, persona_profile)
        choice_objects = []
        for index, choice in enumerate(raw_choices, start=1):
            style = choice.get("style") or choice_style(choice.get("text", ""))
            tone = choice.get("tone") or choice_tone(choice.get("text", ""), style)
            normalized_choice = {
                "id": choice.get("id") or f"{node['id']}-C{index}",
                "text": clean_model_text(choice.get("text", "")),
                "nextNodeId": clean_model_text(choice.get("nextNodeId", "")),
                "style": style,
                "tone": tone,
                "effects": normalize_choice_effect_payload(choice.get("effects"), style, clean_model_text),
                "isRecommended": False,
                "isAiChoice": False,
            }
            basis = recommendation_basis[index - 1] if index - 1 < len(recommendation_basis) else {}
            normalized_choice["isRecommended"] = bool(basis.get("isRecommended"))
            normalized_choice["isAiChoice"] = bool(basis.get("isAiChoice"))
            choice_objects.append(normalized_choice)
        node["choices"] = choice_objects
        node["turn"] = int(node.get("turn", 1))
        node["stage"] = infer_stage_from_turn(node["turn"], playable_count, "turn")
        for choice in node["choices"]:
            next_node = node_map.get(choice["nextNodeId"])
            if next_node and next_node.get("kind") == "ending":
                choice["effects"]["relationship"] = {
                    **choice["effects"].get("relationship", {}),
                }
    story_package["playableTurnCount"] = playable_count
    story_package["endingNodeIds"] = [node["id"] for node in nodes if node.get("kind") == "ending"]
    return story_package


def story_package_validation_error(story_package: dict[str, Any], clean_model_text: Callable[[str], str]) -> Optional[str]:
    """校验 story package 是否满足当前可玩结构约束。"""
    nodes = story_package.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return "Story package must contain nodes"
    node_map = {node.get("id"): node for node in nodes if node.get("id")}
    root_node_id = story_package.get("rootNodeId")
    if root_node_id not in node_map:
        return "rootNodeId must point to an existing node"
    playable_nodes = [node for node in nodes if node.get("kind") == "turn"]
    ending_nodes = [node for node in nodes if node.get("kind") == "ending"]
    if len(playable_nodes) < 2:
        return "Story package must contain at least 2 playable turn nodes"
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
            if not clean_model_text(choice.get("text", "")):
                return f"Choice text is missing in node {node.get('id', 'unknown')}"
            if clean_model_text(choice.get("nextNodeId", "")) not in node_map:
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


def choice_blueprint(
    choice_id: str,
    strategy: str,
    prompt_label: str,
    fallback_text: str,
    next_node_id: str,
    style: Optional[str] = None,
    tone: Optional[str] = None,
) -> dict[str, Any]:
    """创建模板骨架里一条 choice blueprint。"""
    resolved_style = style or strategy
    return {
        "id": choice_id,
        "strategy": strategy,
        "promptLabel": prompt_label,
        "fallbackText": fallback_text,
        "nextNodeId": next_node_id,
        "style": resolved_style,
        "tone": tone or choice_tone(fallback_text, resolved_style),
        "effects": choice_effects(resolved_style),
    }


def build_template_story_package_skeleton(
    opening: str,
    role: str,
    get_opening_title: Callable[[str], str],
    get_opening_summary: Callable[[str], str],
    package_version: int,
) -> dict[str, Any]:
    """生成后端内置的高戏剧互动故事骨架模板。"""
    title = get_opening_title(opening) or "未命名互动宇宙"
    opening_summary = get_opening_summary(opening) or opening.split("\n")[0].strip() or opening
    nodes = [
        {
            "id": "N1",
            "kind": "turn",
            "turn": 1,
            "stageLabel": "第一幕·直接出事",
            "directorNote": "异常已经摆到台面上了，你得马上接球、试探，或者直接掀桌。",
            "summary": "故事一开场就出现明显异常，主角必须立刻用自己的态度回应局势。",
            "beat": "开场异常",
            "pathSummary": f"开头已经给出核心异常：{opening_summary}",
            "choiceBlueprints": [
                choice_blueprint("N1-C1", "soft", "软接情绪", "我放轻声音：「你先别躲，我想知道这件事里，你最怕我看见的到底是什么。」", "N2-soft", style="soft", tone="温柔"),
                choice_blueprint("N1-C2", "tease", "带笑试探", "我偏头笑了一下：「你把气氛搞得这么暧昧，我要是再装傻，是不是就太不给面子了？」", "N2-tease", style="tease", tone="撩拨"),
                choice_blueprint("N1-C3", "confrontation", "直接掀桌", "我抬眼盯住他：「既然都把我逼到这一步了，那你就别想再含糊过去。」", "N2-hard", style="confrontation", tone="强势"),
            ],
        },
        {
            "id": "N2-soft",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·柔软反扑",
            "directorNote": "你先接住了局面，对方的软肋浮出来了。第二次选择会决定这场关系是落向真心、暧昧，还是清醒抽身。",
            "summary": "温柔路线让对方开始松动，真正的情绪爆点已经来到眼前。",
            "beat": "中段推进",
            "pathSummary": "你在第一步选择先接住情绪，于是局势从对撞转向带伤的靠近。",
            "choiceBlueprints": [
                choice_blueprint("N2-soft-C1", "trust", "认真接住", "我伸手握住他：「那这次换我认真一点，不让你一个人撑着。」", "E-sweet", style="trust", tone="真诚"),
                choice_blueprint("N2-soft-C2", "tease", "留一点余温", "我弯起眼睛：「你都说到这一步了，再嘴硬就太可惜了吧？」", "E-slowburn", style="tease", tone="暧昧"),
                choice_blueprint("N2-soft-C3", "observation", "先把自己稳住", "我深吸一口气：「今天先到这里，我得先把自己理清楚。」", "E-open", style="observation", tone="克制"),
            ],
        },
        {
            "id": "N2-tease",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·暧昧升温",
            "directorNote": "你把场面拧得更暧昧了，对方已经快被你撩到失控。第二次选择会决定这是甜蜜兑现、慢热拉扯，还是临门收手。",
            "summary": "撩拨路线让张力拉满，关系已经走到要落地的前一秒。",
            "beat": "中段推进",
            "pathSummary": "你在第一步选择带笑试探，把场面推成了一场带火花的拉扯。",
            "choiceBlueprints": [
                choice_blueprint("N2-tease-C1", "trust", "把玩笑落地", "我忽然认真起来：「如果你愿意说实话，这次我不会再笑着糊弄过去。」", "E-sweet", style="trust", tone="真诚"),
                choice_blueprint("N2-tease-C2", "tease", "继续续杯", "我抬手替他理了一下衣领：「你都快把心事写脸上了，还要我继续猜吗？」", "E-slowburn", style="tease", tone="撩拨"),
                choice_blueprint("N2-tease-C3", "observation", "停在门口", "我把笑意收了一点：「今天就先到这里，剩下的话改天再说。」", "E-open", style="observation", tone="克制"),
            ],
        },
        {
            "id": "N2-hard",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·正面冲撞",
            "directorNote": "你把话挑明了，对方也被逼到边缘。第二次选择会决定你是强硬拿下、半退半撩，还是先抽身止损。",
            "summary": "强势路线把局势直接推到悬崖边，情绪和真相一起翻上来。",
            "beat": "中段推进",
            "pathSummary": "你在第一步直接掀桌，把关系推进到了最容易出真相也最容易失控的位置。",
            "choiceBlueprints": [
                choice_blueprint("N2-hard-C1", "confrontation", "强硬拿下", "我还是不退：「你可以生气，但你得把理由一字一句说清楚。」", "E-sweet", style="confrontation", tone="强势"),
                choice_blueprint("N2-hard-C2", "tease", "边退边撩", "我忽然放缓一点：「如果我真的伤到你，那你至少要让我知道我错在哪。」", "E-slowburn", style="tease", tone="松动"),
                choice_blueprint("N2-hard-C3", "observation", "先行止损", "我盯着他看了几秒，最后还是后退半步：「今天先到这里，等我们都冷静了再说。」", "E-open", style="observation", tone="冷静"),
            ],
        },
        {
            "id": "E-sweet",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局",
            "directorNote": "高好感分支结局：允许甜、疯、黑色幽默或高压反转，不限制标题风格。",
            "summary": "这是高好感分支的结局位，请由模型根据前文自由命名并完成收束。",
            "beat": "高好感结局位",
            "pathSummary": "高好感路径已成立，结局标题和收束风格由模型自行决定。",
            "endingType": "good",
            "choices": [],
        },
        {
            "id": "E-slowburn",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局",
            "directorNote": "中间态分支结局：允许慢热留白，也允许压抑、反讽或临界失控。",
            "summary": "这是中间态分支的结局位，请由模型自由命名并决定结尾张力。",
            "beat": "中间态结局位",
            "pathSummary": "中间态路径已成立，结局标题与调性不做固定模板限制。",
            "endingType": "bittersweet",
            "choices": [],
        },
        {
            "id": "E-open",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局",
            "directorNote": "低好感/克制分支结局：可开放式，也可强冲突、决裂、冷幽默或自我觉醒。",
            "summary": "这是低好感或克制分支的结局位，请由模型自由命名并完成结尾。",
            "beat": "低好感/克制结局位",
            "pathSummary": "低好感或克制路径已成立，结局标题和尺度由模型自由发挥。",
            "endingType": "open",
            "choices": [],
        },
    ]

    for node in nodes:
        if node.get("kind") != "turn":
            continue
        blueprints = node.get("choiceBlueprints", [])
        node["choices"] = [
            {
                "id": blueprint["id"],
                "text": blueprint["fallbackText"],
                "nextNodeId": blueprint["nextNodeId"],
                "style": blueprint["style"],
                "tone": blueprint["tone"],
                "effects": blueprint["effects"],
            }
            for blueprint in blueprints
        ]

    return {
        "version": package_version,
        "title": title,
        "opening": opening,
        "role": role,
        "rootNodeId": "N1",
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"favor": 0},
            "persona": {"extrovert_introvert": 0, "scheming_naive": 0, "optimistic_pessimistic": 0},
            "turn": 1,
            "endingHint": "",
        },
    }
