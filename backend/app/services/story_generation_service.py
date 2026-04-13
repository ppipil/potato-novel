"""故事生成服务模块，负责故事包生成主编排与节点物化流程。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Type


async def hydrate_story_nodes_interleaved(
    access_token: Optional[str],
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    choice_provider: str,
    prose_provider: str,
    generate_story_node_choices: Callable[..., Awaitable[list[dict[str, Any]]]],
    generate_story_node_content: Callable[..., Awaitable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """按阅读顺序逐节点物化：先正文，再选项。"""
    phase_nodes = [node.get("id") for node in skeleton_nodes if node.get("id")]
    completed_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        base_node = {**node}
        content = await generate_story_node_content(
            access_token=access_token,
            opening=opening,
            role=role,
            title=title,
            skeleton_nodes=skeleton_nodes,
            node=base_node,
            provider=prose_provider,
            phase_nodes=phase_nodes,
        )
        hydrated_node = {
            **base_node,
            "stageLabel": content.get("stageLabel") or base_node.get("stageLabel", "剧情推进"),
            "directorNote": content.get("directorNote") or base_node.get("directorNote", ""),
            "scene": content["scene"],
            "paragraphs": content["paragraphs"],
            "summary": content.get("summary") or base_node.get("summary", ""),
            "loaded": True,
        }
        if hydrated_node.get("kind") == "turn":
            hydrated_node["choices"] = await generate_story_node_choices(
                access_token=access_token,
                opening=opening,
                role=role,
                title=title,
                skeleton_nodes=skeleton_nodes,
                node=hydrated_node,
                provider=choice_provider,
                phase_nodes=phase_nodes,
            )
        completed_nodes.append(hydrated_node)
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
    """按“正文先行，再生选项”的节点迭代方式生成完整故事包。"""
    skeleton = build_story_package_skeleton(opening=opening, role=role)
    skeleton_nodes = skeleton.get("nodes", [])
    completed_nodes = await hydrate_story_nodes_interleaved(
        access_token=access_token,
        opening=opening,
        role=role,
        title=skeleton.get("title", ""),
        skeleton_nodes=skeleton_nodes,
        choice_provider=choice_provider,
        prose_provider=prose_provider,
        generate_story_node_choices=generate_story_node_choices,
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
