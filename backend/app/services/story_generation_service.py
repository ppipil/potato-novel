"""故事生成服务模块，负责故事包生成主编排与节点物化流程。"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Optional, Type


def _emit_generation_log(tag: str, payload: dict[str, Any]) -> None:
    """输出始终开启的故事生成进度日志，便于排查长时间卡住的问题。"""
    print(tag, payload, flush=True)


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
    total_nodes = len(phase_nodes)
    for index, node in enumerate(skeleton_nodes, start=1):
        base_node = {**node}
        node_id = str(base_node.get("id") or f"N{index}")
        node_started_at = time.perf_counter()
        _emit_generation_log(
            "[story-package-progress]",
            {
                "step": "node-prose-start",
                "nodeId": node_id,
                "nodeKind": base_node.get("kind"),
                "nodeIndex": index,
                "nodeTotal": total_nodes,
                "stageLabel": base_node.get("stageLabel", ""),
            },
        )
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
        _emit_generation_log(
            "[story-package-progress]",
            {
                "step": "node-prose-done",
                "nodeId": node_id,
                "nodeIndex": index,
                "nodeTotal": total_nodes,
                "elapsedMs": int((time.perf_counter() - node_started_at) * 1000),
            },
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
            choice_started_at = time.perf_counter()
            _emit_generation_log(
                "[story-package-progress]",
                {
                    "step": "node-choices-start",
                    "nodeId": node_id,
                    "nodeIndex": index,
                    "nodeTotal": total_nodes,
                },
            )
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
            _emit_generation_log(
                "[story-package-progress]",
                {
                    "step": "node-choices-done",
                    "nodeId": node_id,
                    "nodeIndex": index,
                    "nodeTotal": total_nodes,
                    "elapsedMs": int((time.perf_counter() - choice_started_at) * 1000),
                },
            )
        completed_nodes.append(hydrated_node)
        _emit_generation_log(
            "[story-package-progress]",
            {
                "step": "node-complete",
                "nodeId": node_id,
                "nodeIndex": index,
                "nodeTotal": total_nodes,
                "totalElapsedMs": int((time.perf_counter() - node_started_at) * 1000),
            },
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
    """按“正文先行，再生选项”的节点迭代方式生成完整故事包。"""
    started_at = time.perf_counter()
    _emit_generation_log(
        "[story-package-progress]",
        {
            "step": "package-build-start",
            "openingPreview": str(opening or "")[:80],
            "role": role,
            "choiceProvider": choice_provider,
            "proseProvider": prose_provider,
        },
    )
    skeleton = build_story_package_skeleton(opening=opening, role=role)
    skeleton_nodes = skeleton.get("nodes", [])
    _emit_generation_log(
        "[story-package-progress]",
        {
            "step": "skeleton-ready",
            "title": skeleton.get("title", ""),
            "nodeCount": len(skeleton_nodes),
            "turnNodeCount": len([node for node in skeleton_nodes if node.get("kind") == "turn"]),
            "endingNodeCount": len([node for node in skeleton_nodes if node.get("kind") == "ending"]),
            "elapsedMs": int((time.perf_counter() - started_at) * 1000),
        },
    )
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
        _emit_generation_log(
            "[story-package-progress]",
            {
                "step": "package-build-failed",
                "reason": validation_error,
                "elapsedMs": int((time.perf_counter() - started_at) * 1000),
            },
        )
        raise http_exception_cls(status_code=400, detail={"message": validation_error})
    finalized = finalize_story_package(package, persona_profile)
    _emit_generation_log(
        "[story-package-progress]",
        {
            "step": "package-build-complete",
            "title": finalized.get("title", ""),
            "nodeCount": len(finalized.get("nodes", []) or []),
            "elapsedMs": int((time.perf_counter() - started_at) * 1000),
        },
    )
    return finalized
