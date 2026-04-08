from __future__ import annotations

import json
from typing import Any


# 旧版逐回合 MCP 流程仍然会用到这套 prompt，因此和当前的故事包生成逻辑分开维护。
def _build_json_story_instruction(extra_instruction: str = "") -> str:
    """构造旧版逐回合故事生成的 JSON 约束说明。"""
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


# 当前“单次请求直接生成完整故事包”的核心约束，书城首访播种主要走这里。
def _build_json_story_package_instruction(extra_instruction: str = "") -> str:
    """构造单次整包生成时的 JSON 结构约束。"""
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
        '"effects":{"persona":{"extrovert_introvert":1},"relationship":{"favor":1}}}]}'
        "]}"
        "其中 turn 节点必须正好 3 个 choices，ending 节点的 choices 必须是空数组。"
        "整个故事包固定为 3 个 ending 节点。"
        "整个分支图通常包含 4 到 7 个 turn 节点，但用户实际单条游玩路径应在 2 到 4 个 turn 节点后进入结局。"
        "rootNodeId 必须指向第一个 turn 节点。"
        "每个 turn 节点都必须能通过 choices 走到某个 ending 节点。"
        "每个 choice 的 nextNodeId 必须指向同一故事包中的合法节点，不能留空，不能引用不存在的节点。"
        "每个 choice 都要写出明确的人设或好感影响，effects 里的数值只能用整数。"
        "正文 scene 必须是 2 段中文互动小说文本，风格更像橙光/互动小说，而不是聊天回复。"
        "三个 choices 必须明显不同，不能只是同义改写。"
        "至少 2 个 choices 要有明确对白或人物动作，不要写成抽象标签。"
        "正文 scene 和 choices.text 中禁止使用英文双引号 \"，因为这会破坏 JSON。"
        "如果需要对白，一律使用中文直角引号「」或自然叙述，不要使用英文双引号。"
        "正文和选项里都不要出现 ```、JSON、注释、解释文字。"
        "单个 scene 固定为 2 段，单个 choice 控制在 40 个中文字符以内。"
        "不要输出任何 null，不要省略必填字段。"
        f"{extra}"
    )


# 两阶段生成时，单个节点正文补全所用的 prompt 模板。
def _build_json_story_node_instruction(extra_instruction: str = "") -> str:
    """构造单节点正文补全时的 JSON 约束。"""
    extra = f"\n修正要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在补全互动小说某一个节点的正文内容。"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "JSON 结构必须为："
        '{"stageLabel":"阶段标题","directorNote":"一句局势提示","scene":"2段正文","summary":"一句本节点摘要"}'
        "scene 必须是中文互动小说文本。"
        "禁止使用英文双引号 \"，如果出现对白，只能使用中文直角引号「」。"
        "不要输出 choices，不要输出 nodes，不要解释结构。"
        "summary 和 directorNote 要短，scene 必须固定写成 2 段，并且围绕已给定的分支走向。"
        "正文要更像有戏的互动小说场景，优先使用对白、动作、误会、反应和情绪落点。"
        "不要平铺直叙地总结剧情，不要新增骨架之外的新主线。"
        f"{extra}"
    )


# 两阶段生成时，单个节点选项补全所用的 prompt 模板。
def _build_json_story_choice_instruction(extra_instruction: str = "") -> str:
    """构造单节点选项补全时的 JSON 约束。"""
    extra = f"\n修正要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        "你正在为互动小说的单个节点生成三个可点击选项。"
        "必须返回严格 JSON，不要使用 Markdown，不要使用代码块，不要添加 JSON 之外的任何文字。\n"
        "JSON 结构必须为："
        '{"choices":[{"strategy":"策略ID","text":"选项文案"},{"strategy":"策略ID","text":"选项文案"},{"strategy":"策略ID","text":"选项文案"}]}'
        "必须严格返回 3 个 choices。"
        "每个 text 都必须是生活化、人物化、能直接点选的选项文案。"
        "至少 2 个选项要带对白或明确动作，不要只写抽象标签。"
        "三个选项必须明显不同，要有 drama 或搞笑互动感。"
        "不要生成新的剧情结构，不要改写 nextNodeId，不要解释策略。"
        f"{extra}"
    )


# 旧版 MCP 入口使用：根据 opening 直接生成第一回合。
def _compose_story_prompt(opening: str, role: str, user_name: str, extra_instruction: str = "") -> str:
    """组合旧版 MCP 流程生成第一回合时使用的完整 prompt。"""
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


# 这是当前首访书城故事时，发送给豆包的一次性整包生成 prompt 形态。
def _compose_story_package_prompt(
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
    repair_hint: str = "",
) -> str:
    """组合单次整包生成故事包的完整 prompt。"""
    preferred = "、".join(persona_profile.get("preferredStyles", [])) or "真诚、试探、撩拨"
    return (
        f"{_build_json_story_package_instruction(repair_hint)}\n\n"
        f"故事开头：{opening}\n"
        f"用户偏好人设：{persona_profile.get('label', '未知分身')}，偏好风格：{preferred}\n"
        "生成要求："
        "整个故事包要有清晰开端、升温、反转、收束；"
        "不同选项要体现温柔、试探、强势、心机、嘴硬、撩拨等差异；"
        "至少设计 1 个甜系或高好感结局，也可以加入 1 个翻车或遗憾结局；"
        "请优先保证结构正确，其次再追求文风华丽。"
    )


# 仅两阶段流程使用：为单个节点生成 3 个可点击选项。
def _compose_story_choice_prompt(
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    repair_hint: str = "",
) -> str:
    """组合两阶段流程里单节点选项生成的完整 prompt。"""
    node_lines = []
    for item in skeleton_nodes:
        next_ids = "；".join(
            f"{choice.get('id')}->{choice.get('nextNodeId')}"
            for choice in item.get("choices", [])
        ) or "无选项"
        node_lines.append(
            f"- {item.get('id')} | {item.get('kind')} | turn={item.get('turn')} | {item.get('stageLabel')} | {item.get('summary')} | {next_ids}"
        )
    skeleton_digest = "\n".join(node_lines)
    strategy_lines = []
    for blueprint in node.get("choiceBlueprints", []):
        strategy_lines.append(
            f"- {blueprint.get('strategy')} | 目标语气={blueprint.get('tone')} | 戏剧功能={blueprint.get('promptLabel')} | nextNodeId={blueprint.get('nextNodeId')}"
        )
    strategy_digest = "\n".join(strategy_lines) or "- 本节点没有选项"
    return (
        f"{_build_json_story_choice_instruction(repair_hint)}\n\n"
        f"故事标题：{title}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        f"当前节点：{node.get('id')} ({node.get('kind')})\n"
        f"当前节点阶段：{node.get('stageLabel')}\n"
        f"当前节点剧情功能：{node.get('beat', node.get('summary', ''))}\n"
        f"当前节点局势提示：{node.get('directorNote', '')}\n"
        f"当前节点摘要：{node.get('summary', '')}\n"
        f"本节点必须输出的三类策略：\n{strategy_digest}\n"
        f"完整骨架：\n{skeleton_digest}\n"
        "请只生成当前节点的 3 个选项文案，并按给定策略顺序返回。"
        "每个选项都要像一句真正会说出口的话或一个真正会做的动作。"
        "不要把三个选项写成同义改写。"
    )


# 仅两阶段流程使用：为单个已存在节点生成正文块。
def _compose_story_node_prompt(
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    repair_hint: str = "",
) -> str:
    """组合两阶段流程里单节点正文生成的完整 prompt。"""
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
        "请固定写 2 段，优先使用人物对白、动作和情绪反应来完成收束。"
        "至少包含：最后一次对峙或确认、情绪落点、结局余波。"
        "读感要像橙光结局页前的正式收尾，不要像系统结算文案。"
    ) if node.get("kind") == "ending" else (
        "这是普通回合节点。scene 固定写 2 段，重点放在当前冲突推进和情绪张力上。"
    )
    return (
        f"{_build_json_story_node_instruction(repair_hint)}\n\n"
        f"故事标题：{title}\n"
        f"玩家身份：{role}\n"
        f"故事开头：{opening}\n"
        f"当前节点：{node.get('id')} ({node.get('kind')})\n"
        f"当前节点阶段：{node.get('stageLabel')}\n"
        f"当前节点戏剧功能：{node.get('beat', node.get('summary', ''))}\n"
        f"当前节点路径摘要：{node.get('pathSummary', '')}\n"
        f"当前节点摘要：{node.get('summary')}\n"
        f"当前节点选项：\n{choice_digest}\n"
        f"完整骨架：\n{skeleton_digest}\n"
        "请只补全当前节点的正文，使它和骨架走向一致。"
        "scene 要有文学阅读感，但不要过长，不要引入骨架之外的新主线。"
        f"{ending_instruction}"
    )


def _compose_ending_analysis_prompt(opening: str, summary: str, transcript: list[dict[str, Any]], state: dict[str, Any]) -> str:
    """组合结局签语分析用的 prompt。"""
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
        "title 要像互动游戏结算称号；"
        "personaTags 返回 2 到 4 个短标签；"
        "romance 必须结合 relationship.favor 的高低来分析感情走向；"
        "life 必须结合 persona 三条轴（extrovert_introvert、scheming_naive、optimistic_pessimistic）做人格分析；"
        "nextUniverseHook 像下一本推荐语。"
    )
