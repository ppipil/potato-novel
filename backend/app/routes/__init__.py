"""后端路由模块集合，负责按 API 领域组织 FastAPI 路由入口。"""

from .auth import create_auth_router
from .frontend import create_frontend_router
from .library import create_library_router
from .mcp import create_mcp_router
from .sessions import create_sessions_router
from .stories import create_stories_router
from .system import create_system_router

__all__ = [
    "create_auth_router",
    "create_frontend_router",
    "create_library_router",
    "create_mcp_router",
    "create_sessions_router",
    "create_stories_router",
    "create_system_router",
]
