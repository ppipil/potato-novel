"""系统路由模块，负责健康检查、公开调试配置和集成清单接口。"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..integration import build_integration_manifest


def create_system_router(deps: SimpleNamespace) -> APIRouter:
    """创建系统与集成相关路由。"""
    router = APIRouter()

    @router.get("/api/health")
    async def health() -> dict[str, str]:
        """健康检查接口。"""
        return {"status": "ok"}

    @router.get("/api/debug-config")
    async def debug_config() -> JSONResponse:
        """返回当前运行时的关键公开配置，便于排障。"""
        return JSONResponse(
            {
                "redirect_uri": settings.redirect_uri,
                "frontend_origin": settings.frontend_origin,
                "public_base_url": settings.public_base_url,
                "app_id": settings.secondme_app_id,
            }
        )

    @router.get("/integration/manifest.json")
    async def integration_manifest(request: Request) -> JSONResponse:
        """返回 SecondMe 集成 manifest。"""
        base_url = settings.public_base_url or str(request.base_url).rstrip("/")
        manifest = build_integration_manifest(base_url=base_url, app_id=settings.secondme_app_id)
        return JSONResponse(manifest)

    return router
