"""Prompt 边界模块，负责统一暴露故事生成与分析所需的 prompt 构造函数。"""

from __future__ import annotations

from ..story_prompts import (
    _compose_ending_analysis_prompt,
    _compose_story_choice_prompt,
    _compose_story_node_prompt,
    _compose_story_package_prompt,
    _compose_story_prompt,
)


def compose_story_prompt(opening: str, role: str, user_name: str, extra_instruction: str = "") -> str:
    """组合旧版 MCP 流程的首回合生成 prompt。"""
    return _compose_story_prompt(opening=opening, role=role, user_name=user_name, extra_instruction=extra_instruction)


def compose_story_package_prompt(
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict,
    repair_hint: str = "",
) -> str:
    """组合整包故事生成所需的 prompt。"""
    return _compose_story_package_prompt(
        opening=opening,
        role=role,
        user_name=user_name,
        persona_profile=persona_profile,
        repair_hint=repair_hint,
    )


def compose_story_choice_prompt(
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict],
    node: dict,
    repair_hint: str = "",
) -> str:
    """组合单节点选项生成所需的 prompt。"""
    return _compose_story_choice_prompt(
        opening=opening,
        role=role,
        title=title,
        skeleton_nodes=skeleton_nodes,
        node=node,
        repair_hint=repair_hint,
    )


def compose_story_node_prompt(
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict],
    node: dict,
    repair_hint: str = "",
) -> str:
    """组合单节点正文生成所需的 prompt。"""
    return _compose_story_node_prompt(
        opening=opening,
        role=role,
        title=title,
        skeleton_nodes=skeleton_nodes,
        node=node,
        repair_hint=repair_hint,
    )


def compose_ending_analysis_prompt(opening: str, summary: str, transcript: list[dict], state: dict) -> str:
    """组合结局签语分析所需的 prompt。"""
    return _compose_ending_analysis_prompt(opening=opening, summary=summary, transcript=transcript, state=state)
