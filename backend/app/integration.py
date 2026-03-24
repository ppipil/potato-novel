from __future__ import annotations

from typing import Any

from .config import settings


def build_integration_manifest(base_url: str, app_id: str = "") -> dict[str, Any]:
    return {
        "skill": {
            "key": "potato-novel",
            "displayName": "土豆小说",
            "description": "选择小说开头和角色，基于 SecondMe 分身生成共创短篇小说。",
            "keywords": ["story", "novel", "roleplay", "secondme", "co-creation"],
        },
        "prompts": {
            "activationShort": "帮我进入土豆小说，选一个开头和角色，生成一篇短篇共创小说。",
            "activationLong": "当用户想进行小说共创时，先展示可选开头，再确认角色身份，然后调用土豆小说工具生成短篇故事。",
            "systemSummary": "土豆小说可以提供推荐开头、根据角色生成短篇小说，并查看已保存的小说记录。",
        },
        "actions": [
            {
                "name": "list_openings",
                "description": "列出当前可用的推荐小说开头。",
                "toolName": "list_openings",
                "displayHint": "先给用户看有哪些推荐开头可选。",
                "payloadTemplate": {},
            },
            {
                "name": "generate_story",
                "description": "根据小说开头和角色身份生成一篇短篇小说。",
                "toolName": "generate_story",
                "displayHint": "当用户确认了开头和角色后调用。",
                "payloadTemplate": {
                    "opening": "{{opening}}",
                    "role": "{{role}}",
                    "extra_instruction": "{{extra_instruction}}",
                },
            },
            {
                "name": "list_saved_stories",
                "description": "查看当前用户已经保存过的小说记录。",
                "toolName": "list_saved_stories",
                "displayHint": "当用户想查看历史共创内容时调用。",
                "payloadTemplate": {},
            },
        ],
        "mcp": {
            "endpoint": f"{base_url.rstrip('/')}/mcp",
            "timeoutMs": 12000,
            "authMode": "none",
            "toolAllow": ["list_openings", "generate_story", "list_saved_stories"],
            "headersTemplate": {},
        },
        "oauth": {
            "appId": app_id,
            "requiredScopes": ["user.info", "chat"],
        } if app_id else None,
        "envBindings": {
            "release": {
                "enabled": False,
            }
        },
    }


def public_base_url() -> str:
    return getattr(settings, "public_base_url", "").rstrip("/")
