from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Optional

import httpx
from fastapi import HTTPException

from .config import settings
from .story_text import _extract_story_from_sse


DebugLogger = Optional[Callable[[str, dict[str, Any]], None]]
MODEL_PROVIDER_TIMEOUT_SECONDS = 180


# This module isolates model-provider specific HTTP calls and response parsing
# so story orchestration in main.py can stay focused on story state.
def _volcengine_chat_url() -> str:
    """拼出 Volcengine 兼容 chat completions 的完整地址。"""
    base_url = settings.volcengine_base_url.strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/chat/completions"):
        return base_url
    chat_path = settings.volcengine_chat_path.strip() or "/chat/completions"
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    return f"{base_url}{chat_path}"


def _volcengine_trust_env() -> bool:
    """控制 Volcengine 请求是否继承代理等环境变量。"""
    raw = os.getenv("VOLCENGINE_TRUST_ENV", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# Volcengine is consumed through an OpenAI-compatible chat-completions shape.
# We build one payload here so sync and fallback attempts stay consistent.
def _volcengine_request_payload(
    prompt: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    disable_reasoning: bool,
) -> dict[str, Any]:
    """构造 Volcengine OpenAI 兼容接口所需的请求体。"""
    payload: dict[str, Any] = {
        "model": settings.volcengine_model,
        "messages": [
            {"role": "system", "content": "你是一个擅长中文互动小说场景写作的助手。请直接输出结果，不要暴露思考过程。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if disable_reasoning:
        # 不同兼容层支持的关字段不完全一致，这里先发一组保守参数；
        # 如果服务端不认识，外层会自动降级重试。
        payload["reasoning"] = {"effort": "low"}
        payload["thinking"] = {"type": "disabled"}
        payload["enable_thinking"] = False
    return payload


def _looks_like_unsupported_param_error(body_text: str) -> bool:
    """判断报错是否来自兼容层不支持某些可选字段。"""
    lowered = (body_text or "").lower()
    keywords = [
        "unknown field",
        "unexpected field",
        "invalid param",
        "invalid parameter",
        "response_format",
        "reasoning",
        "thinking",
        "enable_thinking",
    ]
    return any(key in lowered for key in keywords)


def _has_volcengine_prose_provider() -> bool:
    """检查正文生成所需的 Volcengine 配置是否齐全。"""
    return bool(settings.volcengine_api_key.strip() and settings.volcengine_model.strip() and _volcengine_chat_url())


# Some OpenAI-compatible providers return content as a plain string, while
# others return an array of typed content parts. Normalize both here.
def _openai_text_content(payload: Any) -> str:
    """兼容解析 OpenAI 风格响应里的完整文本内容。"""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = []
        for item in payload:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(payload or "")


def _openai_delta_text(payload: Any) -> str:
    """兼容解析流式 delta 里的文本片段。"""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return "".join(
            str(item.get("text", ""))
            for item in payload
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


async def _call_secondme_chat(access_token: str, prompt: str) -> str:
    """调用 SecondMe chat 流接口，返回完整文本。"""
    try:
        async with httpx.AsyncClient(timeout=MODEL_PROVIDER_TIMEOUT_SECONDS, trust_env=False) as client:
            chat_response = await client.post(
                "https://api.mindverse.com/gate/lab/api/secondme/chat/stream",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"message": prompt},
            )
            if chat_response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "SecondMe chat request failed", "body": chat_response.text},
                )
            story_text = _extract_story_from_sse(chat_response.text)
            if not story_text.strip():
                raise HTTPException(status_code=400, detail="SecondMe chat returned empty content")
            return story_text
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe chat API", "error": str(exc)},
        ) from exc


async def _call_secondme_act(
    access_token: str,
    message: str,
    action_control: str,
    max_tokens: int = 2000,
    debug_log: DebugLogger = None,
) -> str:
    """调用 SecondMe act 接口，执行结构化生成任务。"""
    # SecondMe act is our structured-generation path: skeletons, choices, and
    # any prompt where we want the provider to follow tighter control text.
    if debug_log is not None:
        debug_log(
            "[story-provider-call]",
            {
                "provider": "secondme",
                "kind": "choices_or_structured_generation",
                "endpoint": "https://api.mindverse.com/gate/lab/api/secondme/act/stream",
                "model": "secondme-default",
                "message": message,
                "maxTokens": max_tokens,
            },
        )
    try:
        async with httpx.AsyncClient(timeout=MODEL_PROVIDER_TIMEOUT_SECONDS, trust_env=False) as client:
            act_response = await client.post(
                "https://api.mindverse.com/gate/lab/api/secondme/act/stream",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "message": message,
                    "actionControl": action_control,
                    "maxTokens": max_tokens,
                },
            )
            if act_response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "SecondMe act request failed", "body": act_response.text},
                )
            action_text = _extract_story_from_sse(act_response.text)
            if not action_text.strip():
                raise HTTPException(status_code=400, detail="SecondMe act returned empty content")
            return action_text
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe act API", "error": str(exc)},
        ) from exc


async def _call_volcengine_prose(
    prompt: str,
    max_tokens: int = 1200,
    debug_log: DebugLogger = None,
) -> str:
    """调用 Volcengine 生成单次完整正文，并按兼容性逐步降级重试。"""
    api_url = _volcengine_chat_url()
    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Volcengine prose provider is not configured")
    if debug_log is not None:
        debug_log(
            "[story-provider-call]",
            {
                "provider": "volcengine",
                "kind": "node_prose_generation",
                "endpoint": api_url,
                "model": settings.volcengine_model,
                "maxTokens": max_tokens,
            },
        )
    last_error: Optional[Exception] = None
    # 逐步去掉可选兼容参数来重试。
    # 有些托管的 OpenAI 兼容层不接受 response_format 或 reasoning 字段，
    # 所以这里先走严格模式，再逐步降级到兼容性更强的请求体。
    attempt_plan = [
        {"json_mode": True, "disable_reasoning": True, "temperature": 0.3},
        {"json_mode": False, "disable_reasoning": True, "temperature": 0.3},
        {"json_mode": False, "disable_reasoning": False, "temperature": 0.35},
    ]
    for attempt, cfg in enumerate(attempt_plan):
        try:
            async with httpx.AsyncClient(timeout=MODEL_PROVIDER_TIMEOUT_SECONDS, trust_env=_volcengine_trust_env()) as client:
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {settings.volcengine_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=_volcengine_request_payload(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=float(cfg["temperature"]),
                        json_mode=bool(cfg["json_mode"]),
                        disable_reasoning=bool(cfg["disable_reasoning"]),
                    ),
                )
                if response.status_code >= 400:
                    body_text = response.text
                    # If the provider rejects optional compatibility fields,
                    # fall through to the next looser attempt instead of
                    # surfacing a hard failure immediately.
                    if attempt < len(attempt_plan) - 1 and _looks_like_unsupported_param_error(body_text):
                        continue
                    raise HTTPException(
                        status_code=400,
                        detail={"message": "Volcengine prose request failed", "body": body_text},
                    )
                payload = response.json()
                choices = payload.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    raise HTTPException(status_code=400, detail={"message": "Volcengine prose response missing choices", "body": payload})
                message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                content = _openai_text_content(message.get("content", ""))
                if not content.strip():
                    raise HTTPException(status_code=400, detail={"message": "Volcengine prose response was empty", "body": payload})
                return content
        except httpx.RequestError as exc:
            last_error = exc
            if attempt < len(attempt_plan) - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise HTTPException(
                status_code=502,
                detail={"message": "Unable to reach Volcengine prose API", "error": str(exc)},
            ) from exc
        except Exception as exc:
            last_error = exc
            raise
    raise HTTPException(status_code=502, detail={"message": "Unable to reach Volcengine prose API", "error": str(last_error or "unknown")})


async def _stream_volcengine_prose_chunks(
    prompt: str,
    max_tokens: int,
    collector: list[str],
    debug_log: DebugLogger = None,
):
    """以流式方式调用 Volcengine，逐段返回正文增量。"""
    api_url = _volcengine_chat_url()
    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Volcengine prose provider is not configured")

    if debug_log is not None:
        debug_log(
            "[story-provider-call]",
            {
                "provider": "volcengine",
                "kind": "node_prose_generation_stream",
                "endpoint": api_url,
                "model": settings.volcengine_model,
                "maxTokens": max_tokens,
                "stream": True,
            },
        )

    try:
        async with httpx.AsyncClient(timeout=MODEL_PROVIDER_TIMEOUT_SECONDS, trust_env=_volcengine_trust_env()) as client:
            # Streaming is only used for incremental prose reveal, so this path
            # is intentionally lighter than the sync JSON-first retry flow.
            async with client.stream(
                "POST",
                api_url,
                headers={
                    "Authorization": f"Bearer {settings.volcengine_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.volcengine_model,
                    "messages": [
                        {"role": "system", "content": "你是一个擅长中文互动小说场景写作的助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.9,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise HTTPException(
                        status_code=400,
                        detail={"message": "Volcengine prose stream request failed", "body": body.decode("utf-8", errors="ignore")},
                    )

                async for raw_line in response.aiter_lines():
                    line = (raw_line or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = payload.get("choices", [])
                    if not isinstance(choices, list) or not choices:
                        continue
                    # OpenAI-style streaming puts each incremental text chunk in
                    # choices[0].delta.content; collector keeps the full draft.
                    delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
                    text_delta = _openai_delta_text(delta.get("content", ""))
                    if not text_delta:
                        continue
                    collector.append(text_delta)
                    yield text_delta
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach Volcengine prose streaming API", "error": str(exc)},
        ) from exc
