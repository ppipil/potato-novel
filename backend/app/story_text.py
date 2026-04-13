from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import HTTPException


def _clean_model_text(value: Any) -> str:
    """清洗模型返回的文本，统一去掉多余包裹和尾部噪声。"""
    text = str(value or "").replace("\r\n", "\n").strip()
    text = text.removesuffix("\n}").removesuffix("}")
    text = text.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    # 常见脏前缀：模型把数组/坏 JSON 片段的一部分混进正文开头。
    while True:
        updated = text
        for prefix in ('", "', '","', "', '", ",'", "',", '["', "['", '",', "',"):
            if updated.startswith(prefix):
                updated = updated[len(prefix):].lstrip()
        if updated.startswith("[") and len(updated) > 1 and updated[1] in {'"', "'"}:
            updated = updated[2:].lstrip()
        if updated == text:
            break
        text = updated
    text = text.strip(" \n\r\t'\",")
    return text


def _parse_loose_string_value(raw_value: str) -> str:
    """尽量从宽松的 JSON 片段里提取一个字符串值。"""
    value = raw_value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return _clean_model_text(
        value.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
        .strip()
    )


def _parse_loose_choices(raw_value: str) -> list[str]:
    """从宽松数组文本里尽量恢复选项列表。"""
    value = raw_value.strip()
    if value.startswith("["):
        value = value[1:]
    if value.endswith("]"):
        value = value[:-1]

    choices: list[str] = []
    current = []
    in_string = False
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            if in_string:
                choices.append("".join(current).strip())
                current = []
                in_string = False
            else:
                in_string = True
            continue
        if in_string:
            current.append(char)

    cleaned_choices = [_clean_model_text(item) for item in choices if _clean_model_text(item)]
    if cleaned_choices:
        return cleaned_choices

    fallback = []
    for part in value.split(","):
        normalized = _clean_model_text(part.strip().strip('"'))
        if normalized:
            fallback.append(normalized)
    return fallback


def _extract_story_payload_fallback(candidate: str) -> Optional[dict[str, Any]]:
    """当标准 JSON 解析失败时，按固定字段顺序兜底抽取故事结构。"""
    keys = ["scene", "summary", "choices", "status", "stageLabel", "directorNote"]
    extracted: dict[str, Any] = {}

    for index, key in enumerate(keys):
        marker = f'"{key}":'
        start = candidate.find(marker)
        if start == -1:
            return None
        value_start = start + len(marker)
        next_start = len(candidate)
        for next_key in keys[index + 1 :]:
            next_marker = f',\n  "{next_key}":'
            found = candidate.find(next_marker, value_start)
            if found != -1:
                next_start = found
                break
        raw_value = candidate[value_start:next_start].strip().rstrip(",").strip()
        if key == "choices":
            extracted[key] = _parse_loose_choices(raw_value)
        else:
            extracted[key] = _parse_loose_string_value(raw_value)

    if not extracted.get("scene") or not extracted.get("choices"):
        return None
    return extracted


def _extract_ending_analysis_payload_fallback(raw_text: str) -> Optional[dict[str, Any]]:
    """当结局分析 JSON 不规范时，兜底提取关键字段。"""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    keys = ["title", "personaTags", "romance", "life", "nextUniverseHook"]
    extracted: dict[str, Any] = {}

    for index, key in enumerate(keys):
        marker = f'"{key}":'
        start_index = candidate.find(marker)
        if start_index == -1:
            continue
        value_start = start_index + len(marker)
        next_start = len(candidate)
        for next_key in keys[index + 1 :]:
            next_marker = f',\n  "{next_key}":'
            found = candidate.find(next_marker, value_start)
            if found != -1:
                next_start = found
                break
        raw_value = candidate[value_start:next_start].strip().rstrip(",").strip()
        if key == "personaTags":
            extracted[key] = _parse_loose_choices(raw_value)
        else:
            extracted[key] = _parse_loose_string_value(raw_value)

    if not extracted:
        return None
    return extracted


def _escape_control_chars_in_json_strings(value: str) -> str:
    """仅在 JSON 字符串内部转义控制字符，减少解析失败。"""
    chars: list[str] = []
    in_string = False
    escaped = False

    for char in value:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\":
            chars.append(char)
            escaped = True
            continue
        if char == '"':
            chars.append(char)
            in_string = not in_string
            continue
        if in_string:
            if char == "\n":
                chars.append("\\n")
                continue
            if char == "\r":
                chars.append("\\r")
                continue
            if char == "\t":
                chars.append("\\t")
                continue
        chars.append(char)

    return "".join(chars)


def _repair_common_json_issues(candidate: str) -> str:
    """修补模型常见的 JSON 格式问题，如中文冒号和重复引号。"""
    repaired = candidate
    repaired = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*：', r'"\1":', repaired)
    repaired = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*,\s*"\1"\s*:', r'"\1":', repaired)
    repaired = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*[“"]+', r'"\1":"', repaired)
    repaired = _escape_control_chars_in_json_strings(repaired)
    return repaired


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """从模型原始文本中截取并解析一个 JSON 对象。"""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise HTTPException(status_code=400, detail={"message": "Interactive story response was not valid JSON", "body": raw_text})
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        repaired_candidate = _repair_common_json_issues(candidate)
        if repaired_candidate != candidate:
            try:
                return json.loads(repaired_candidate)
            except json.JSONDecodeError:
                pass
        fallback_payload = _extract_story_payload_fallback(candidate)
        if fallback_payload is not None:
            return fallback_payload
        raise HTTPException(
            status_code=400,
            detail={"message": "Interactive story JSON parse failed", "body": raw_text, "error": str(exc)},
        ) from exc


def _split_scene_into_paragraphs(scene: str) -> list[str]:
    """把场景正文拆成前端逐段展示用的段落数组。"""
    normalized = scene.replace("\r\n", "\n").strip()
    paragraphs = [part.strip() for part in normalized.split("\n") if part.strip()]
    if len(paragraphs) >= 2:
        return paragraphs[:5]
    chunks = [part.strip() for part in normalized.replace("。", "。\n").split("\n") if part.strip()]
    return chunks[:5] if chunks else [scene]


def _normalize_ending_analysis(raw_text: str) -> dict[str, Any]:
    """把模型返回的结局分析整理成稳定字段。"""
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException:
        payload = _extract_ending_analysis_payload_fallback(raw_text) or {}
    return {
        "title": _clean_model_text(payload.get("title", "")) or "你的土豆人格正在生成中",
        "personaTags": [
            _clean_model_text(item)
            for item in payload.get("personaTags", [])
            if _clean_model_text(item)
        ] if isinstance(payload.get("personaTags"), list) else [],
        "romance": _clean_model_text(payload.get("romance", "")) or "这局里的你，显然不是随便点点选项的人。",
        "life": _clean_model_text(payload.get("life", "")) or "放到现实生活里，你大概也是那种会把故事过成连续剧的人。",
        "nextUniverseHook": _clean_model_text(payload.get("nextUniverseHook", "")) or "下一本宇宙，也许更适合你的那一面。",
    }


def _extract_story_from_sse(raw_text: str) -> str:
    """从 SSE 响应中拼接出完整文本内容。"""
    chunks: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except Exception:
            continue
        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                chunks.append(str(content))
    return "".join(chunks)
