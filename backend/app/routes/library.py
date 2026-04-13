"""书城路由模块，负责模板故事目录、seed 播种与基于 seed 的开局接口。"""

from __future__ import annotations

import time
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
        return JSONResponse({"ok": True, "stories": deps.build_library_story_rows()})

    @router.post("/api/library-stories/{story_id}/generate-seed")
    async def generate_library_story_seed(story_id: str, request: Request) -> JSONResponse:
        """显式为某本书城故事播种全局 seed。"""
        deps.require_env()
        deps.get_server_or_guest_session(request)
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
        server_session = deps.get_server_or_guest_session(request)
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
        server_session = deps.get_server_or_guest_session(request)
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

    @router.post("/api/library-stories/import-package")
    async def import_library_story_package(request: Request) -> JSONResponse:
        """从工作台导入故事包并同步到书市和 library seed。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        deps.require_library_workbench_operator(server_session)
        body = await request.json()
        result = deps.import_library_story_package(server_session, body)
        return JSONResponse({"ok": True, **result})

    @router.post("/api/library-workbench/ai-complete-node")
    async def ai_complete_library_workbench_node(request: Request) -> JSONResponse:
        """为隐藏工作台的单节点生成正文/选项，便于继续人工编辑。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        deps.require_library_workbench_operator(server_session)
        body = await request.json()
        result = await deps.ai_complete_workbench_node(server_session, body)
        return JSONResponse({"ok": True, **result})

    @router.post("/api/library-workbench/ai-parse-outline")
    async def ai_parse_library_workbench_outline(request: Request) -> JSONResponse:
        """把用户输入的大纲自动解析为工作台节点图。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        deps.require_library_workbench_operator(server_session)
        body = await request.json()
        result = await deps.ai_parse_workbench_outline(server_session, body)
        return JSONResponse({"ok": True, **result})

    @router.delete("/api/library-stories/{story_id}/imported")
    async def delete_imported_library_story(story_id: str, request: Request) -> JSONResponse:
        """删除一个导入的书市故事与对应 seed。"""
        print(
            f"[library-delete] incoming path={request.url.path} story_id={story_id}",
            flush=True,
        )
        deps.require_env()
        server_session = deps.get_server_session(request)
        current_user_id = str(server_session.get("user", {}).get("userId") or "").strip()
        current_user_name = (
            str(server_session.get("user", {}).get("name") or "").strip()
            or str(server_session.get("user", {}).get("nickname") or "").strip()
        )
        is_operator = bool(deps.is_library_workbench_operator(current_user_id, current_user_name))
        started_at = time.time()
        print(
            f"[library-delete] start story_id={story_id} user_id={current_user_id or 'unknown'} is_operator={is_operator}",
            flush=True,
        )
        trace_id = f"lib-del-{int(started_at * 1000)}"
        result = deps.delete_imported_library_story(story_id, current_user_id, is_operator)
        elapsed_ms = int((time.time() - started_at) * 1000)
        print(
            f"[library-delete] done trace={trace_id} story_id={story_id} elapsed_ms={elapsed_ms} story_deleted={result.get('storyDeleted')} seed_deleted={result.get('seedDeleted')}",
            flush=True,
        )
        return JSONResponse({"ok": True, **result})

    return router
