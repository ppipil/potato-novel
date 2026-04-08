"""会话路由模块，负责故事开局、播放相关会话操作和结局分析接口。"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_sessions_router(deps: SimpleNamespace) -> APIRouter:
    """创建故事会话相关路由。"""
    router = APIRouter()

    @router.post("/api/story/start")
    async def start_story(request: Request) -> JSONResponse:
        """统一的故事开始入口，返回可读的 story session。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        session_record, reused = await deps.create_or_reuse_story_package(body, server_session)
        if session_record.get("kind") == "story_package":
            deps.ensure_story_package_runtime(session_record)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "reused": reused})

    @router.post("/api/custom-stories/generate")
    async def generate_custom_story(request: Request) -> JSONResponse:
        """根据自定义 opening 生成一条新的故事会话。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        opening = deps.clean_model_text(body.get("opening", ""))
        role = deps.clean_model_text(body.get("role", "")) or "主人公"
        if not opening:
            raise HTTPException(status_code=400, detail="Missing opening")
        session_record, reused = await deps.start_or_generate_custom_story(
            server_session,
            opening=opening,
            role=role,
            force_regenerate=bool(body.get("forceRegenerate")),
        )
        deps.ensure_story_package_runtime(session_record)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "reused": reused})

    @router.post("/api/story/preload")
    async def preload_story_package(request: Request) -> JSONResponse:
        """兼容预加载入口，实际复用 start_story。"""
        return await start_story(request)

    @router.post("/api/story/regenerate")
    async def regenerate_story_package(request: Request) -> JSONResponse:
        """强制重新生成一个新的故事包。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        session_record, _ = await deps.create_or_reuse_story_package({**body, "forceRegenerate": True}, server_session)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "reused": False})

    @router.post("/api/story/analyze-ending")
    async def analyze_story_ending(request: Request) -> JSONResponse:
        """根据完成后的故事轨迹生成结局签语分析。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()

        session_id = body.get("sessionId", "").strip()
        story = body.get("story", "")
        meta = body.get("meta", {}) or {}
        analysis_context = deps.build_ending_analysis_context(
            session_id=session_id,
            story=story,
            meta=meta,
            user_id=server_session["user"].get("userId"),
        )

        prompt = deps.compose_ending_analysis_prompt(
            opening=analysis_context["opening"],
            summary=analysis_context["summary"],
            transcript=analysis_context["transcript"],
            state=analysis_context["state"],
        )
        analysis = deps.normalize_ending_analysis(
            await deps.call_secondme_chat(server_session["token"]["access_token"], prompt)
        )
        return JSONResponse({"ok": True, "analysis": analysis})

    @router.post("/api/story/generate")
    async def generate_story(request: Request) -> JSONResponse:
        """兼容旧路由，转发到 start_story。"""
        return await start_story(request)

    return router
