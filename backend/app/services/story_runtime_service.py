"""故事运行时服务模块，负责 runtime 初始化、会话复用判断和完成态故事编译。"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Type

from ..domain.session_models import normalize_source_type
from ..domain.story_package import build_runtime_entries_for_node, build_story_package_node_map


def initial_runtime_from_package(
    story_package: dict[str, Any],
    clean_model_text: Callable[[str], str],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """根据故事包根节点构造初始阅读 runtime。"""
    root_node_id = story_package.get("rootNodeId")
    node_map = build_story_package_node_map(story_package)
    root_node = node_map.get(root_node_id)
    if not root_node:
        raise http_exception_cls(status_code=400, detail="Story package root node is missing")
    return {
        "currentNodeId": root_node_id,
        "entries": build_runtime_entries_for_node(root_node, clean_model_text),
        "path": [],
        "state": story_package.get("initialState", {}),
        "status": "complete" if root_node.get("kind") == "ending" else "ongoing",
        "endingNodeId": root_node_id if root_node.get("kind") == "ending" else "",
        "summary": clean_model_text(root_node.get("summary", "")) if root_node.get("kind") == "ending" else "",
    }


def ensure_story_package_runtime(
    session: dict[str, Any],
    clean_model_text: Callable[[str], str],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """确保故事包会话上始终带有可用的 runtime。"""
    runtime = session.get("runtime")
    package = session.get("package", {})
    node_map = build_story_package_node_map(package)
    if isinstance(runtime, dict) and runtime.get("currentNodeId") in node_map:
        return runtime
    runtime = initial_runtime_from_package(package, clean_model_text, http_exception_cls)
    session["runtime"] = runtime
    return runtime


def package_matches(session: dict[str, Any], user_id: str, opening: str, role: str) -> bool:
    """判断一个故事包会话是否命中指定开头和角色。"""
    return (
        session.get("userId") == user_id
        and session.get("meta", {}).get("opening", "").strip() == opening.strip()
        and session.get("meta", {}).get("role", "").strip() == role.strip()
    )


def find_reusable_package(
    sessions: list[dict[str, Any]],
    user_id: str,
    opening: str,
    role: str,
    package_version: int,
    clean_model_text: Callable[[str], str],
    legacy_package_generator: str,
    template_package_generator: str,
    source_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """查找当前用户可直接复用的未完成故事包。"""
    for item in sessions:
        if not package_matches(item, user_id, opening, role):
            continue
        if item.get("kind") != "story_package":
            continue
        if source_type and normalize_source_type(item.get("sourceType") or item.get("meta", {}).get("sourceType")) != source_type:
            continue
        if source_type == "library" and not clean_model_text(item.get("meta", {}).get("openingId", "")):
            continue
        if item.get("completedRun"):
            continue
        if str(item.get("status", "")).strip().lower() == "complete":
            continue
        runtime = item.get("runtime")
        if isinstance(runtime, dict) and str(runtime.get("status", "")).strip().lower() == "complete":
            continue
        if item.get("packageStatus") not in {"ready", "hydrating"}:
            continue
        package = item.get("package", {})
        if package.get("version") != package_version:
            continue
        if package.get("generatedBy") not in {legacy_package_generator, template_package_generator}:
            continue
        return item
    return None


def build_story_from_completed_run(
    session: dict[str, Any],
    completed_run: dict[str, Any],
    clean_model_text: Callable[[str], str],
    get_opening_title: Callable[[str], str],
) -> str:
    """把 story package 的 completed run 编译成完整故事文本。"""
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
        lines.append(clean_model_text(item.get("text", "")))
        lines.append("")
    summary = clean_model_text(completed_run.get("summary", ""))
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


def build_story_from_session(
    session: dict[str, Any],
    clean_model_text: Callable[[str], str],
    get_opening_title: Callable[[str], str],
    http_exception_cls: Type[Exception],
) -> str:
    """把会话内容编译成可保存的完整故事文本。"""
    if session.get("kind") == "story_package":
        completed_run = session.get("completedRun")
        if not completed_run:
            raise http_exception_cls(status_code=400, detail="Story package has not been completed")
        return build_story_from_completed_run(session, completed_run, clean_model_text, get_opening_title)

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
