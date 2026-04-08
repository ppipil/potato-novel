"""前端静态资源路由模块，负责 SPA 入口页与前端路由回退。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse


def create_frontend_router(deps: SimpleNamespace) -> APIRouter:
    """为已构建的前端产物创建静态入口路由。"""
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        """在生产构建存在时返回前端入口页。"""
        return FileResponse(deps.frontend_dist_dir / "index.html")

    @router.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        """为前端 SPA 提供静态资源和回退路由。"""
        requested = deps.frontend_dist_dir / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(deps.frontend_dist_dir / "index.html")

    return router
