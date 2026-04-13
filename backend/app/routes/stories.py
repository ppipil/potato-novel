"""故事记录路由模块，负责保存、读取、删除和补充已保存故事元数据。"""

from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..security import random_urlsafe


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
        story_id = random_urlsafe(10)
        record = {
            "id": story_id,
            "createdAt": int(time.time()),
            "updatedAt": int(time.time()),
            "userId": server_session["user"].get("userId"),
            "meta": {
                **meta,
                "opening": meta.get("opening", ""),
                "role": meta.get("role", ""),
                "author": meta.get("author") or server_session["user"].get("name") or "SecondMe 用户",
                "sessionId": meta.get("sessionId", ""),
                "turnCount": meta.get("turnCount", 0),
                "status": meta.get("status", ""),
                "state": meta.get("state", {}),
            },
            "story": story,
        }
        stories.insert(0, record)
        deps.save_stories(stories)
        return JSONResponse({"ok": True, "story": record})

    @router.get("/api/stories")
    async def list_stories(request: Request) -> JSONResponse:
        """列出当前用户保存过的故事。"""
        deps.require_env()
        server_session = deps.get_server_session(request)
        user_id = server_session["user"].get("userId")
        stories = [item for item in deps.load_stories() if item.get("userId") == user_id]
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
