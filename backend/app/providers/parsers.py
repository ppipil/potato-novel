"""模型输出解析边界模块，负责统一暴露 JSON 提取与故事结构归一化能力。"""

from __future__ import annotations

import re
from typing import Any, Callable, Type

from ..domain.story_package import choice_style
from ..domain.story_package import choice_tone
from ..domain.story_package import fallback_choice_by_index
from ..domain.story_package import finalize_story_package
from ..domain.story_package import normalize_choice_effect_payload
from ..domain.story_package import story_package_validation_error
from ..story_text import _extract_json_object, _normalize_ending_analysis, _split_scene_into_paragraphs


def extract_json_object(raw_text: str) -> dict:
    """从模型输出中提取 JSON 对象。"""
    return _extract_json_object(raw_text)


def split_scene_into_paragraphs(scene: str) -> list[str]:
    """把正文文本拆成前端可展示的段落数组。"""
    return _split_scene_into_paragraphs(scene)


def normalize_ending_analysis(raw_text: str) -> dict:
    """把模型返回的结局分析归一化为前端可用结构。"""
    return _normalize_ending_analysis(raw_text)


def normalize_story_package(
    raw_text: str,
    opening: str,
    role: str,
    persona_profile: dict[str, Any],
    clean_model_text: Callable[[str], str],
    get_opening_title: Callable[[str], str],
    package_version: int,
    template_package_generator: str,
    story_generation_debug_metadata: Callable[[], dict[str, Any]],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """把整包故事 JSON 解析成内部统一的 story package 结构。"""
    try:
        payload = extract_json_object(raw_text)
    except Exception as exc:
        if not isinstance(exc, http_exception_cls):
            raise
        raise http_exception_cls(
            status_code=400,
            detail={
                "message": "Story package JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_nodes = payload.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise http_exception_cls(status_code=400, detail={"message": "Story package nodes must be an array", "body": raw_text})

    nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = clean_model_text(raw_node.get("id", f"N{index}")) or f"N{index}"
        kind = clean_model_text(raw_node.get("kind", "turn")).lower()
        if kind not in {"turn", "ending"}:
            kind = "turn"
        turn = raw_node.get("turn", index)
        if not isinstance(turn, int):
            turn = index
        scene = clean_model_text(raw_node.get("scene", ""))
        if not scene:
            continue
        summary = clean_model_text(raw_node.get("summary", "")) or scene
        stage_label = clean_model_text(raw_node.get("stageLabel", "剧情推进")) or "剧情推进"
        director_note = clean_model_text(raw_node.get("directorNote", ""))
        raw_choices = raw_node.get("choices", [])
        if not isinstance(raw_choices, list):
            raw_choices = []
        choices = []
        if kind == "turn":
            for choice_index, raw_choice in enumerate(raw_choices[:3], start=1):
                if not isinstance(raw_choice, dict):
                    continue
                text = clean_model_text(raw_choice.get("text", ""))
                next_node_id = clean_model_text(raw_choice.get("nextNodeId", ""))
                if not text or not next_node_id:
                    continue
                style = clean_model_text(raw_choice.get("style", "")) or choice_style(text)
                tone = clean_model_text(raw_choice.get("tone", "")) or choice_tone(text, style)
                choices.append(
                    {
                        "id": clean_model_text(raw_choice.get("id", f"{node_id}-C{choice_index}")) or f"{node_id}-C{choice_index}",
                        "text": text,
                        "nextNodeId": next_node_id,
                        "style": style,
                        "tone": tone,
                        "effects": normalize_choice_effect_payload(raw_choice.get("effects"), style, clean_model_text),
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
                "paragraphs": split_scene_into_paragraphs(scene),
                "summary": summary,
                "choices": choices if kind == "turn" else [],
            }
        )

    story_package = {
        "version": package_version,
        "title": clean_model_text(payload.get("title", "")) or get_opening_title(opening) or "未命名互动宇宙",
        "opening": opening,
        "role": role,
        "rootNodeId": clean_model_text(payload.get("rootNodeId", "N1")) or "N1",
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
    validation_error = story_package_validation_error(story_package, clean_model_text)
    if validation_error:
        raise http_exception_cls(status_code=400, detail={"message": validation_error, "body": raw_text})
    return finalize_story_package(
        story_package,
        persona_profile,
        clean_model_text,
        package_version,
        template_package_generator,
        story_generation_debug_metadata,
    )


def normalize_story_node_content(
    raw_text: str,
    clean_model_text: Callable[[str], str],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """把单节点正文 JSON 解析成内部统一结构。"""
    try:
        payload = extract_json_object(raw_text)
    except Exception as exc:
        if not isinstance(exc, http_exception_cls):
            raise
        payload = _fallback_story_node_content_payload(raw_text, clean_model_text)
        if payload is None:
            raise http_exception_cls(
                status_code=400,
                detail={
                    "message": "Story node JSON parse failed",
                    "body": raw_text,
                    "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
                },
            ) from exc
    scene = clean_model_text(payload.get("scene", ""))
    if not scene:
        raise http_exception_cls(status_code=400, detail={"message": "Story node scene is missing", "body": raw_text})
    stage_label = clean_model_text(payload.get("stageLabel", "剧情推进")) or "剧情推进"
    director_note = clean_model_text(payload.get("directorNote", ""))
    summary = clean_model_text(payload.get("summary", "")) or scene
    return {
        "stageLabel": stage_label,
        "directorNote": director_note,
        "scene": scene,
        "paragraphs": split_scene_into_paragraphs(scene),
        "summary": summary,
    }


def _fallback_story_node_content_payload(
    raw_text: str,
    clean_model_text: Callable[[str], str],
) -> dict[str, str] | None:
    """当节点正文没返回合法 JSON 时，尽量从半结构化文本里抢救出可用正文。"""
    cleaned = str(raw_text or "").strip()
    if not cleaned:
        return None

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()

    stage_label = ""
    director_note = ""
    summary = ""
    scene_lines: list[str] = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = line.replace("：", ":")
        lower = normalized.lower()
        if lower.startswith("stagelabel:"):
            stage_label = clean_model_text(normalized.split(":", 1)[1])
            continue
        if lower.startswith("directornote:"):
            director_note = clean_model_text(normalized.split(":", 1)[1])
            continue
        if lower.startswith("summary:"):
            summary = clean_model_text(normalized.split(":", 1)[1])
            continue
        if lower.startswith("scene:"):
            scene_lines.append(clean_model_text(normalized.split(":", 1)[1]))
            continue
        if re.match(r"^(阶段标题|局势提示|摘要|正文)\s*:", normalized):
            label, value = normalized.split(":", 1)
            value = clean_model_text(value)
            if "阶段标题" in label:
                stage_label = value
            elif "局势提示" in label:
                director_note = value
            elif "摘要" in label:
                summary = value
            elif "正文" in label:
                scene_lines.append(value)
            continue
        scene_lines.append(line)

    scene = clean_model_text("\n".join(scene_lines))
    if not scene:
        flat = clean_model_text(cleaned)
        if len(flat) < 20:
            return None
        scene = flat

    return {
        "stageLabel": stage_label or "剧情推进",
        "directorNote": director_note,
        "summary": summary or scene,
        "scene": scene,
    }


def normalize_story_node_choices(
    raw_text: str,
    node: dict[str, Any],
    clean_model_text: Callable[[str], str],
    http_exception_cls: Type[Exception],
) -> list[dict[str, Any]]:
    """把单节点选项 JSON 解析成内部统一结构。"""
    blueprints = node.get("choiceBlueprints", [])
    if not isinstance(blueprints, list) or len(blueprints) != 3:
        raise http_exception_cls(status_code=400, detail={"message": "Story node is missing choice blueprints", "node": node.get("id")})

    try:
        payload = extract_json_object(raw_text)
    except Exception as exc:
        if not isinstance(exc, http_exception_cls):
            raise
        raise http_exception_cls(
            status_code=400,
            detail={
                "message": "Story choice JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_choices = payload.get("choices", [])
    if not isinstance(raw_choices, list):
        raw_choices = []

    provided_texts: list[str] = []
    for raw_choice in raw_choices[:3]:
        if isinstance(raw_choice, dict):
            provided_texts.append(clean_model_text(raw_choice.get("text", "")))
        else:
            provided_texts.append(clean_model_text(raw_choice))

    distinct_texts: list[str] = []
    seen: set[str] = set()
    for index, blueprint in enumerate(blueprints):
        candidate = provided_texts[index] if index < len(provided_texts) else ""
        if not candidate or candidate in seen:
            candidate = clean_model_text(blueprint.get("fallbackText", ""))
        if candidate in seen:
            candidate = fallback_choice_by_index(index, node.get("summary", ""))
        distinct_texts.append(candidate)
        seen.add(candidate)

    choices: list[dict[str, Any]] = []
    for blueprint, text in zip(blueprints, distinct_texts):
        style = clean_model_text(blueprint.get("style", "")) or choice_style(text)
        choices.append(
            {
                "id": clean_model_text(blueprint.get("id", "")) or f"{node.get('id')}-{len(choices) + 1}",
                "text": text,
                "nextNodeId": clean_model_text(blueprint.get("nextNodeId", "")),
                "style": style,
                "tone": clean_model_text(blueprint.get("tone", "")) or choice_tone(text, style),
                "effects": normalize_choice_effect_payload(blueprint.get("effects"), style, clean_model_text),
            }
        )
    return choices
