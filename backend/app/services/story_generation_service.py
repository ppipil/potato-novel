"""故事生成服务模块，负责两阶段故事包生成的主编排与节点物化流程。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Type


async def hydrate_story_choice_nodes(
    access_token: Optional[str],
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    choice_provider: str,
    generate_story_node_choices: Callable[..., Awaitable[list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """按顺序为所有 turn 节点补全选项。"""
    choice_phase_nodes = [node.get("id") for node in skeleton_nodes if node.get("kind") == "turn" and node.get("id")]
    prepared_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        if node.get("kind") != "turn":
            prepared_nodes.append(node)
            continue
        prepared_nodes.append(
            {
                **node,
                "choices": await generate_story_node_choices(
                    access_token=access_token,
                    opening=opening,
                    role=role,
                    title=title,
                    skeleton_nodes=skeleton_nodes,
                    node=node,
                    provider=choice_provider,
                    phase_nodes=choice_phase_nodes,
                ),
            }
        )
    return prepared_nodes


async def hydrate_story_content_nodes(
    access_token: Optional[str],
    opening: str,
    role: str,
    title: str,
    prepared_nodes: list[dict[str, Any]],
    prose_provider: str,
    generate_story_node_content: Callable[..., Awaitable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """按顺序为全部节点补全正文内容。"""
    prose_phase_nodes = [node.get("id") for node in prepared_nodes if node.get("id")]
    completed_nodes: list[dict[str, Any]] = []
    for node in prepared_nodes:
        content = await generate_story_node_content(
            access_token=access_token,
            opening=opening,
            role=role,
            title=title,
            skeleton_nodes=prepared_nodes,
            node=node,
            provider=prose_provider,
            phase_nodes=prose_phase_nodes,
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
    return completed_nodes


async def build_story_package_two_stage(
    access_token: Optional[str],
    opening: str,
    role: str,
    persona_profile: dict[str, Any],
    build_story_package_skeleton: Callable[..., dict[str, Any]],
    generate_story_node_choices: Callable[..., Awaitable[list[dict[str, Any]]]],
    generate_story_node_content: Callable[..., Awaitable[dict[str, Any]]],
    finalize_story_package: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    story_package_validation_error: Callable[[dict[str, Any]], Optional[str]],
    http_exception_cls: Type[Exception],
    choice_provider: str = "secondme",
    prose_provider: str = "volcengine",
) -> dict[str, Any]:
    """按“先选项、后正文”的两阶段方式生成完整故事包。"""
    skeleton = build_story_package_skeleton(opening=opening, role=role)
    skeleton_nodes = skeleton.get("nodes", [])
    prepared_nodes = await hydrate_story_choice_nodes(
        access_token=access_token,
        opening=opening,
        role=role,
        title=skeleton.get("title", ""),
        skeleton_nodes=skeleton_nodes,
        choice_provider=choice_provider,
        generate_story_node_choices=generate_story_node_choices,
    )
    completed_nodes = await hydrate_story_content_nodes(
        access_token=access_token,
        opening=opening,
        role=role,
        title=skeleton.get("title", ""),
        prepared_nodes=prepared_nodes,
        prose_provider=prose_provider,
        generate_story_node_content=generate_story_node_content,
    )
    package = {
        **skeleton,
        "nodes": completed_nodes,
        "hydratedNodeIds": sorted(node.get("id") for node in completed_nodes if node.get("id")),
    }
    validation_error = story_package_validation_error(package)
    if validation_error:
        raise http_exception_cls(status_code=400, detail={"message": validation_error})
    return finalize_story_package(package, persona_profile)
