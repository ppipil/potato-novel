"""Volcengine provider 边界模块，负责暴露豆包兼容接口相关能力。"""

from __future__ import annotations

from ..model_providers import (
    _call_volcengine_prose,
    _has_volcengine_prose_provider,
    _stream_volcengine_prose_chunks,
    _volcengine_chat_url,
)


def volcengine_chat_url() -> str:
    """返回当前豆包兼容 chat completions 地址。"""
    return _volcengine_chat_url()


def has_volcengine_prose_provider() -> bool:
    """判断当前是否具备豆包正文生成配置。"""
    return _has_volcengine_prose_provider()


async def call_volcengine_prose(prompt: str, max_tokens: int = 1200, debug_log=None) -> str:
    """调用豆包生成单次完整正文。"""
    return await _call_volcengine_prose(prompt=prompt, max_tokens=max_tokens, debug_log=debug_log)


async def stream_volcengine_prose_chunks(prompt: str, max_tokens: int = 1200, collector=None, debug_log=None):
    """流式调用豆包正文生成接口。"""
    async for chunk in _stream_volcengine_prose_chunks(
        prompt=prompt,
        max_tokens=max_tokens,
        collector=collector,
        debug_log=debug_log,
    ):
        yield chunk
