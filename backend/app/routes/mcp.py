"""MCP 路由模块，负责统一暴露给 MCP 客户端的协议入口。"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_mcp_router(deps: SimpleNamespace) -> APIRouter:
    """创建 MCP 协议路由。"""
    router = APIRouter()

    @router.post("/mcp")
    async def mcp_endpoint(request: Request) -> JSONResponse:
        """提供给 MCP 客户端调用的统一入口。"""
        body = await request.json()
        method = body.get("method")
        request_id = body.get("id")

        if method == "initialize":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "potato-novel-mcp", "version": "0.1.0"},
                        "capabilities": {"tools": {}},
                    },
                }
            )

        if method == "tools/list":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "list_openings",
                                "description": "列出当前推荐的小说开头。",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "generate_story",
                                "description": "根据开头和角色生成短篇小说。需要请求头带 Authorization: Bearer <SecondMe access token>。",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "opening": {"type": "string"},
                                        "role": {"type": "string"},
                                        "extra_instruction": {"type": "string"},
                                    },
                                    "required": ["opening", "role"],
                                },
                            },
                            {
                                "name": "list_saved_stories",
                                "description": "列出当前服务端已保存的小说记录摘要。",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                        ]
                    },
                }
            )

        if method == "tools/call":
            params = body.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "list_openings":
                openings = [
                    {
                        "title": deps.get_opening_title(opening),
                        "summary": deps.get_opening_summary(opening),
                        "opening": opening,
                    }
                    for opening in deps.preset_openings
                ]
                return JSONResponse(deps.mcp_result(request_id, openings))

            if name == "list_saved_stories":
                stories = [
                    {
                        "id": item["id"],
                        "createdAt": item["createdAt"],
                        "title": item["meta"].get("opening", "")[:40],
                        "role": item["meta"].get("role", ""),
                        "author": item["meta"].get("author", ""),
                    }
                    for item in deps.load_stories()[:20]
                ]
                return JSONResponse(deps.mcp_result(request_id, stories))

            if name == "generate_story":
                opening = (arguments.get("opening") or "").strip()
                role = (arguments.get("role") or "").strip()
                extra_instruction = (arguments.get("extra_instruction") or "").strip()
                auth_header = request.headers.get("Authorization", "")
                if not opening or not role:
                    return JSONResponse(deps.mcp_error(request_id, -32602, "Missing opening or role"))
                if not auth_header.startswith("Bearer "):
                    return JSONResponse(deps.mcp_error(request_id, -32001, "Missing Authorization bearer token"))
                access_token = auth_header.replace("Bearer ", "", 1).strip()
                prompt = deps.compose_story_prompt(opening=opening, role=role, user_name="SecondMe 用户", extra_instruction=extra_instruction)
                story = await deps.call_secondme_chat(access_token=access_token, prompt=prompt)
                return JSONResponse(deps.mcp_result(request_id, {"story": story, "opening": opening, "role": role}))

            return JSONResponse(deps.mcp_error(request_id, -32601, f"Unknown tool: {name}"))

        return JSONResponse(deps.mcp_error(request_id, -32601, f"Unknown method: {method}"))

    return router
