"""会话路由模块，负责故事开局、播放相关会话操作和结局分析接口。"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


def create_sessions_router(deps: SimpleNamespace) -> APIRouter:
    """创建故事会话相关路由。"""
    router = APIRouter()

    @router.post("/api/story/start")
    async def start_story(request: Request) -> JSONResponse:
        """统一的故事开始入口，返回可读的 story session。"""
        deps.require_env()
        server_session = deps.get_server_or_guest_session(request)
        body = await request.json()
        session_record, reused = await deps.create_or_reuse_story_package(body, server_session)
        if session_record.get("kind") == "story_package":
            deps.ensure_story_package_runtime(session_record)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "reused": reused})

    @router.post("/api/custom-stories/generate")
    async def generate_custom_story(request: Request) -> JSONResponse:
        """根据自定义 opening 生成一条新的故事会话。"""
        deps.require_env()
        server_session = deps.get_server_or_guest_session(request)
        started_at = time.time()
        body = await request.json()
        opening = deps.clean_model_text(body.get("opening", ""))
        style_guidance = deps.clean_model_text(body.get("styleGuidance", ""))
        role = deps.clean_model_text(body.get("role", "")) or "主人公"
        if not opening:
            raise HTTPException(status_code=400, detail="Missing opening")
        trace_id = f"custom-{int(started_at * 1000)}"
        print(
            "[custom-story-route-start]",
            json.dumps(
                {
                    "traceId": trace_id,
                    "userId": server_session.get("user", {}).get("userId", ""),
                    "openingPreview": opening[:80],
                    "hasStyleGuidance": bool(style_guidance),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        try:
            session_record, reused = await deps.start_or_generate_custom_story(
                server_session,
                opening=opening,
                role=role,
                style_guidance=style_guidance,
                force_regenerate=bool(body.get("forceRegenerate")),
            )
        except HTTPException as exc:
            print(
                "[custom-story-route-failed]",
                json.dumps(
                    {
                        "traceId": trace_id,
                        "statusCode": exc.status_code,
                        "elapsedMs": int((time.time() - started_at) * 1000),
                        "detail": exc.detail,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            raise
        except Exception as exc:
            print(
                "[custom-story-route-failed]",
                json.dumps(
                    {
                        "traceId": trace_id,
                        "statusCode": 500,
                        "elapsedMs": int((time.time() - started_at) * 1000),
                        "detail": repr(exc),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            raise
        print(
            "[custom-story-route-complete]",
            json.dumps(
                {
                    "traceId": trace_id,
                    "elapsedMs": int((time.time() - started_at) * 1000),
                    "sessionId": session_record.get("id", ""),
                    "reused": reused,
                },
                ensure_ascii=False,
            ),
            flush=True,
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
        started_at = time.time()

        session_id = body.get("sessionId", "").strip()
        story = body.get("story", "")
        meta = body.get("meta", {}) or {}
        trace_id = str(meta.get("traceId") or f"ending-{int(started_at * 1000)}")
        transcript_size = len(meta.get("transcript", []) or [])
        print(
            f"[ending-analysis] start trace={trace_id} session={session_id or 'none'} transcript={transcript_size}",
            flush=True,
        )
        analysis_context = deps.build_ending_analysis_context(
            session_id=session_id,
            story=story,
            meta=meta,
            user_id=server_session["user"].get("userId"),
        )
        print(
            f"[ending-analysis] context trace={trace_id} opening_len={len(str(analysis_context.get('opening', '')))} summary_len={len(str(analysis_context.get('summary', '')))} transcript={len(analysis_context.get('transcript', []) or [])}",
            flush=True,
        )

        prompt = deps.compose_ending_analysis_prompt(
            opening=analysis_context["opening"],
            summary=analysis_context["summary"],
            transcript=analysis_context["transcript"],
            state=analysis_context["state"],
        )
        try:
            raw_analysis = await deps.call_secondme_chat(server_session["token"]["access_token"], prompt)
            print(
                f"[ending-analysis] provider-return trace={trace_id} raw_len={len(str(raw_analysis or ''))}",
                flush=True,
            )
            analysis = deps.normalize_ending_analysis(raw_analysis)
        except Exception as exc:
            elapsed_ms = int((time.time() - started_at) * 1000)
            print(
                f"[ending-analysis] failed trace={trace_id} elapsed_ms={elapsed_ms} error={repr(exc)}",
                flush=True,
            )
            raise
        elapsed_ms = int((time.time() - started_at) * 1000)
        print(f"[ending-analysis] done trace={trace_id} elapsed_ms={elapsed_ms}", flush=True)
        return JSONResponse({"ok": True, "analysis": analysis})

    @router.post("/api/story/generate")
    async def generate_story(request: Request) -> JSONResponse:
        """兼容旧路由，转发到 start_story。"""
        return await start_story(request)

    @router.post("/api/story-packages/import")
    async def import_story_package(request: Request) -> JSONResponse:
        """导入一个完整 story package 并落库存为可直接游玩的会话。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        raw_package = body.get("package")
        if not isinstance(raw_package, dict):
            raise HTTPException(status_code=400, detail="Missing package")

        validation_error = deps.story_package_validation_error(raw_package)
        if validation_error:
            raise HTTPException(status_code=400, detail={"message": validation_error})

        opening = deps.clean_model_text(body.get("opening", "")) or deps.clean_model_text(raw_package.get("title", "")) or "导入故事包"
        role = deps.clean_model_text(body.get("role", "")) or "主人公"
        source_type = deps.clean_model_text(body.get("sourceType", "")) or "custom"
        if source_type not in {"custom", "library"}:
            source_type = "custom"

        session_record = deps.build_story_package_session_payload(
            server_session=server_session,
            opening=opening,
            role=role,
            source_type=source_type,
            story_package=raw_package,
        )
        session_record["meta"] = {
            **(session_record.get("meta") or {}),
            "imported": True,
            "importTag": deps.clean_model_text(body.get("importTag", "")) or "manual",
        }
        deps.insert_new_session_record(session_record)
        deps.ensure_story_package_runtime(session_record)
        return JSONResponse({"ok": True, "session": deps.serialize_session(session_record), "imported": True})

    return router
