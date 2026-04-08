"""会话领域模型辅助模块，负责来源类型规范化和会话响应序列化。"""

from __future__ import annotations

from typing import Any, Callable


def normalize_source_type(value: Any) -> str:
    """规范化故事来源类型，只保留 `library` 或 `custom`。"""
    normalized = str(value or "").strip().lower()
    if normalized in {"library", "custom"}:
        return normalized
    return "custom"


def serialize_session(session: dict[str, Any], clean_model_text: Callable[[str], str]) -> dict[str, Any]:
    """把内部会话结构裁剪成前端可消费的响应格式。"""
    if session.get("kind") == "story_package":
        source_type = normalize_source_type(session.get("sourceType") or session.get("meta", {}).get("sourceType"))
        meta = {**session.get("meta", {})}
        meta.pop("runtime", None)
        meta["sourceType"] = source_type
        return {
            "id": session["id"],
            "kind": "story_package",
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"],
            "status": session.get("status", "ready"),
            "packageStatus": session.get("packageStatus", "ready"),
            "sourceType": source_type,
            "meta": meta,
            "package": session.get("package", {}),
            "completedRun": session.get("completedRun"),
            "runtime": session.get("runtime"),
        }
    return {
        "id": session["id"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "status": session["status"],
        "turnCount": session["turnCount"],
        "meta": session["meta"],
        "summary": clean_model_text(session.get("summary", "")),
        "currentScene": clean_model_text(session.get("currentScene", "")),
        "paragraphs": [clean_model_text(item) for item in session.get("paragraphs", []) if clean_model_text(item)],
        "choices": session.get("choices", []),
        "stageLabel": clean_model_text(session.get("stageLabel", "剧情推进")) or "剧情推进",
        "directorNote": clean_model_text(session.get("directorNote", "")),
        "state": session.get("state", {}),
        "personaProfile": session.get("personaProfile", {}),
        "recommendedChoiceId": session.get("recommendedChoiceId"),
        "aiChoiceId": session.get("aiChoiceId"),
        "transcript": [
            {
                **item,
                "label": clean_model_text(item.get("label", "")),
                "text": clean_model_text(item.get("text", "")),
            }
            for item in session.get("transcript", [])
        ],
    }
