"""SecondMe provider 边界模块，负责暴露 SecondMe 相关模型调用入口。"""

from __future__ import annotations

from ..model_providers import _call_secondme_act, _call_secondme_chat


async def call_secondme_chat(access_token: str, prompt: str) -> str:
    """调用 SecondMe chat 能力并返回完整文本。"""
    return await _call_secondme_chat(access_token, prompt)


async def call_secondme_act(
    access_token: str,
    message: str,
    action_control: str,
    max_tokens: int = 2000,
    debug_log=None,
) -> str:
    """调用 SecondMe act 能力执行结构化生成任务。"""
    return await _call_secondme_act(
        access_token=access_token,
        message=message,
        action_control=action_control,
        max_tokens=max_tokens,
        debug_log=debug_log,
    )
