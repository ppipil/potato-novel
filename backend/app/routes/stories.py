"""故事记录路由模块，负责保存、读取、删除和补充已保存故事元数据。"""

from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..security import random_urlsafe


def _normalized_session_id(record: dict | None) -> str:
    """读取故事记录里的会话标识，便于保存幂等与列表去重。"""
    if not isinstance(record, dict):
        return ""
    meta = record.get("meta", {})
    return str(meta.get("sessionId", "")).strip() if isinstance(meta, dict) else ""


def _story_sort_key(record: dict) -> tuple[int, int]:
    """统一故事记录排序规则，优先最近更新时间。"""
    return (
        int(record.get("updatedAt", 0) or 0),
        int(record.get("createdAt", 0) or 0),
    )


def _dedupe_story_records(records: list[dict], user_id: str) -> list[dict]:
    """按故事 id 与 sessionId 去重，避免同一完成会话出现多个书架条目。"""
    deduped_by_session: dict[str, dict] = {}
    passthrough: list[dict] = []

    for item in records:
        if item.get("userId") != user_id:
            continue
        session_id = _normalized_session_id(item)
        if not session_id:
            passthrough.append(item)
            continue
        existing = deduped_by_session.get(session_id)
        if existing is None or _story_sort_key(item) > _story_sort_key(existing):
            deduped_by_session[session_id] = item

    merged = passthrough + list(deduped_by_session.values())
    merged.sort(key=_story_sort_key, reverse=True)
    return merged


def create_stories_router(deps: SimpleNamespace) -> APIRouter:
    """创建已保存故事相关路由。"""
    router = APIRouter()

    @router.post("/api/story/save")
    async def save_story(request: Request) -> JSONResponse:
        """把编译后的完整故事保存到持久化存储。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        story = body.get("story", "").strip()
        meta = body.get("meta", {})
        if not story:
            raise HTTPException(status_code=400, detail="Missing story")

        stories = deps.load_stories()
        user_id = server_session["user"].get("userId")
        session_id = str(meta.get("sessionId", "")).strip()
        existing_record = None
        if session_id:
            for item in stories:
                if item.get("userId") == user_id and _normalized_session_id(item) == session_id:
                    if existing_record is None or _story_sort_key(item) > _story_sort_key(existing_record):
                        existing_record = item
        story_id = existing_record.get("id") if existing_record else random_urlsafe(10)
        now = int(time.time())
        record = {
            "id": story_id,
            "createdAt": int(existing_record.get("createdAt", now) if existing_record else now),
            "updatedAt": now,
            "userId": user_id,
            "meta": {
                **meta,
                "opening": meta.get("opening", ""),
                "role": meta.get("role", ""),
                "author": meta.get("author") or server_session["user"].get("name") or "SecondMe 用户",
                "sessionId": session_id,
                "turnCount": meta.get("turnCount", 0),
                "status": meta.get("status", ""),
                "state": meta.get("state", {}),
            },
            "story": story,
        }
        stories = [
            item
            for item in stories
            if not (
                item.get("id") == story_id
                or (session_id and item.get("userId") == user_id and _normalized_session_id(item) == session_id)
            )
        ]
        stories.insert(0, record)
        deps.save_stories(stories)
        return JSONResponse({"ok": True, "story": record})

    @router.get("/api/stories")
    async def list_stories(request: Request) -> JSONResponse:
        """列出当前用户保存过的故事。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        user_id = server_session["user"].get("userId")
        stories = _dedupe_story_records(deps.load_stories(), user_id)
        return JSONResponse({"ok": True, "stories": stories})

    @router.get("/api/stories/{story_id}")
    async def get_story(story_id: str, request: Request) -> JSONResponse:
        """读取当前用户的一条已保存故事。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        user_id = server_session["user"].get("userId")
        for item in deps.load_stories():
            if item.get("id") == story_id and item.get("userId") == user_id:
                return JSONResponse({"ok": True, "story": item})
        raise HTTPException(status_code=404, detail="Story not found")

    @router.delete("/api/stories/{story_id}")
    async def delete_story(story_id: str, request: Request) -> JSONResponse:
        """删除当前用户保存的一条故事。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        user_id = server_session["user"].get("userId")
        if not deps.delete_story_record(story_id, user_id):
            raise HTTPException(status_code=404, detail="Story not found")
        return JSONResponse({"ok": True, "storyId": story_id})

    @router.post("/api/stories/{story_id}/ending-analysis")
    async def cache_story_ending_analysis(story_id: str, request: Request) -> JSONResponse:
        """把结局签语分析缓存到已保存故事的元数据里。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        body = await request.json()
        analysis = body.get("analysis")
        if not isinstance(analysis, dict):
            raise HTTPException(status_code=400, detail="Missing ending analysis")

        stories = deps.load_stories()
        user_id = server_session["user"].get("userId")
        for index, item in enumerate(stories):
            if item.get("id") == story_id and item.get("userId") == user_id:
                meta = item.setdefault("meta", {})
                meta["endingAnalysis"] = analysis
                item["updatedAt"] = int(time.time())
                stories[index] = item
                deps.save_stories(stories)
                return JSONResponse({"ok": True, "story": item})
        raise HTTPException(status_code=404, detail="Story not found")

    return router
