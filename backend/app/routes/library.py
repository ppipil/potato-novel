"""书城路由模块，负责模板故事目录、seed 播种与基于 seed 的开局接口。"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


def create_library_router(deps: SimpleNamespace) -> APIRouter:
    """创建书城故事相关路由。"""
    router = APIRouter()

    @router.get("/api/library-stories")
    async def list_library_stories(request: Request) -> JSONResponse:
        """列出书城内置故事及其播种状态。"""
        deps.require_env()
        deps.get_server_session(request)
        return JSONResponse({"ok": True, "stories": deps.build_library_story_rows()})

    @router.post("/api/library-stories/{story_id}/generate-seed")
    async def generate_library_story_seed(story_id: str, request: Request) -> JSONResponse:
        """显式为某本书城故事播种全局 seed。"""
        deps.require_env()
        deps.get_server_session(request)
        body = await request.json()
        opening = deps.resolve_library_opening(story_id)
        _, generated_now = await deps.generate_library_seed_package(
            opening=opening,
            opening_id=story_id,
            force_regenerate=bool(body.get("forceRegenerate")),
            skip_existing_check=not bool(body.get("forceRegenerate")),
        )
        seed = deps.require_library_seed_session(None, story_id)
        return JSONResponse(
            {
                "ok": True,
                "seedReady": True,
                "generatedNow": generated_now,
                "pioneer": generated_now,
                "seedSessionId": seed.get("id"),
                "pioneerMessage": "你是这颗土豆宇宙的播种者，正在为后续读者生成完整章节，请稍等片刻。" if generated_now else "",
            }
        )

    @router.post("/api/library-stories/{story_id}/start-from-seed")
    async def start_library_story_from_seed(story_id: str, request: Request) -> JSONResponse:
        """基于已存在的全局 seed 为当前用户新开一局书城故事。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        role = deps.clean_model_text(body.get("role", "")) or "主人公"
        opening = deps.resolve_library_opening(story_id)
        seed = deps.require_library_seed_session(None, story_id)
        session_record = deps.build_story_package_session_payload(
            server_session,
            opening=opening,
            role=role,
            source_type="library",
            opening_id=story_id,
            story_package=seed.get("package", {}),
        )
        deps.ensure_story_package_runtime(session_record)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "reused": False})

    @router.post("/api/library-stories/{story_id}/start")
    async def start_library_story(story_id: str, request: Request) -> JSONResponse:
        """兼容旧入口：没有 seed 时先播种，再基于 seed 新开一局。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        role = deps.clean_model_text(body.get("role", "")) or "主人公"
        opening = deps.resolve_library_opening(story_id)
        _, generated_now = await deps.generate_library_seed_package(
            opening=opening,
            opening_id=story_id,
            force_regenerate=bool(body.get("forceRegenerate")),
        )
        sessions = deps.load_sessions()
        seed = deps.require_library_seed_session(sessions, story_id)
        session_record = deps.build_story_package_session_payload(
            server_session,
            opening=opening,
            role=role,
            source_type="library",
            opening_id=story_id,
            story_package=seed.get("package", {}),
        )
        deps.ensure_story_package_runtime(session_record)
        return JSONResponse(
            {
                "ok": True,
                "session": deps.serialize_session(session_record),
                "reused": False,
                "pioneer": generated_now,
                "pioneerMessage": "你是这颗土豆宇宙的播种者，正在为后续读者生成完整章节，请稍等片刻。" if generated_now else "",
            }
        )

    return router
