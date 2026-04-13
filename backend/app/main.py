"""后端主入口模块，负责应用初始化、共享依赖装配以及路由挂载。"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import httpx

try:
    import psycopg
except ImportError:  # pragma: no cover - 某些环境暂时没装数据库依赖时，允许退回文件存储
    psycopg = None
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .domain.session_models import normalize_source_type as _normalize_source_type
from .domain.session_models import serialize_session
from .domain.story_package import build_template_story_package_skeleton as _domain_build_template_story_package_skeleton
from .domain.story_package import choice_effects as _choice_effects
from .domain.story_package import choice_style as _choice_style
from .domain.story_package import choice_tone as _choice_tone
from .domain.story_package import fallback_choice_by_index as _fallback_choice_by_index
from .domain.story_package import finalize_story_package as _finalize_story_package
from .domain.story_package import normalize_choice_effect_payload as _normalize_choice_effect_payload
from .domain.story_package import story_package_validation_error as _story_package_validation_error
from .integration import build_integration_manifest
from .openings import PRESET_OPENINGS, get_opening_summary, get_opening_title
from .providers import (
    call_secondme_act as _call_secondme_act,
    call_secondme_chat as _call_secondme_chat,
    call_volcengine_prose as _call_volcengine_prose,
    compose_ending_analysis_prompt as _compose_ending_analysis_prompt,
    compose_story_choice_prompt as _compose_story_choice_prompt,
    compose_story_node_prompt as _compose_story_node_prompt,
    compose_story_package_prompt as _compose_story_package_prompt,
    compose_story_prompt as _compose_story_prompt,
    extract_json_object as _extract_json_object,
    has_volcengine_prose_provider as _has_volcengine_prose_provider,
    normalize_ending_analysis as _normalize_ending_analysis,
    normalize_story_node_choices as _provider_normalize_story_node_choices,
    normalize_story_node_content as _provider_normalize_story_node_content,
    normalize_story_package as _provider_normalize_story_package,
    stream_volcengine_prose_chunks as _stream_volcengine_prose_chunks,
    volcengine_chat_url as _volcengine_chat_url,
)
from .repositories import sessions_repo, stories_repo
from .routes import (
    create_auth_router,
    create_frontend_router,
    create_library_router,
    create_mcp_router,
    create_sessions_router,
    create_stories_router,
    create_system_router,
)
from .security import random_urlsafe, sign_payload, verify_payload
from .story_text import _clean_model_text
from .services.story_generation_service import build_story_package_two_stage
from .services.library_seed_service import build_library_story_rows
from .services.library_seed_service import find_library_seed_session
from .services.library_seed_service import generate_library_seed_package
from .services.library_seed_service import load_or_generate_library_seed_package
from .services.library_seed_service import require_library_seed_session
from .services.library_seed_service import resolve_library_opening
from .services.library_import_service import delete_imported_library_story as delete_imported_library_story_service
from .services.library_import_service import import_library_story_package as import_library_story_package_service
from .services.library_workbench_service import ai_complete_workbench_node as ai_complete_workbench_node_service
from .services.library_workbench_service import ai_parse_workbench_outline as ai_parse_workbench_outline_service
from .services.story_session_service import build_ending_analysis_context
from .services.story_session_service import create_or_reuse_story_package
from .services.story_runtime_service import ensure_story_package_runtime
from .services.story_runtime_service import find_reusable_package
from .services.story_runtime_service import build_story_from_completed_run
from .services.story_runtime_service import build_story_from_session
from .services.story_runtime_service import initial_runtime_from_package
from .services.story_runtime_service import package_matches

app = FastAPI(title="Potato Novel Backend")
DEFAULT_DATA_DIR = Path("/tmp/potato-novel-data") if os.getenv("VERCEL") else Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()
STORIES_PATH = DATA_DIR / "stories.json"
SESSIONS_PATH = DATA_DIR / "story_sessions.json"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
COOKIE_PATH = "/"
PACKAGE_VERSION = 2
DEBUG_STORY_GENERATION = os.getenv("SECONDME_DEBUG_STORY", "").strip().lower() in {"1", "true", "yes", "on"}
TEMPLATE_PACKAGE_GENERATOR = "template_split_generation_v1"
LEGACY_PACKAGE_GENERATOR = "secondme_act_two_stage"
LIBRARY_SEED_USER_ID = "__library_seed__"
LIBRARY_SEED_LOCK_DIR = DATA_DIR / "locks"
LIBRARY_SEED_WAIT_TIMEOUT_SECONDS = 90
LIBRARY_SEED_WAIT_INTERVAL_SECONDS = 0.5
GUEST_USER_ID = "__guest_local__"


def _library_workbench_operator_id_set() -> set[str]:
    """解析允许导入/强权限删除书市内容的操作员 ID 白名单。"""
    raw = settings.library_workbench_operator_ids or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_library_workbench_operator(user_id: str, user_name: str = "") -> bool:
    """判断当前用户是否具备书市工作台操作权限。"""
    normalized_name = str(user_name or "").strip().lower()
    if normalized_name.startswith("kk"):
        return True
    # 保留白名单兜底（便于后续运营切换）
    return bool(user_id and user_id in _library_workbench_operator_id_set())


def _require_library_workbench_operator(server_session: dict[str, Any]) -> None:
    """导入书市故事包必须是白名单操作员。"""
    user_id = str(server_session.get("user", {}).get("userId") or "").strip()
    user_name = (
        str(server_session.get("user", {}).get("name") or "").strip()
        or str(server_session.get("user", {}).get("nickname") or "").strip()
    )
    if not _is_library_workbench_operator(user_id, user_name):
        raise HTTPException(status_code=403, detail="Library workbench permission denied")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _initial_runtime_from_package(story_package: dict[str, Any]) -> dict[str, Any]:
    """兼容主模块现有调用，转发到 runtime service 构造初始 runtime。"""
    return initial_runtime_from_package(story_package, _clean_model_text, HTTPException)


def _ensure_story_package_runtime(session: dict[str, Any]) -> dict[str, Any]:
    """兼容主模块现有调用，转发到 runtime service 确保 runtime 存在。"""
    return ensure_story_package_runtime(session, _clean_model_text, HTTPException)


def _serialize_session(session: dict[str, Any]) -> dict[str, Any]:
    """兼容主模块现有调用，转发到会话领域模型序列化逻辑。"""
    return serialize_session(session, _clean_model_text)


def _require_env() -> None:
    """校验后端启动和鉴权所需的关键环境变量。"""
    missing = []
    for name, value in {
        "SECONDME_CLIENT_ID": settings.client_id,
        "SECONDME_CLIENT_SECRET": settings.client_secret,
        "SECONDME_AUTH_URL": settings.auth_url,
        "SECONDME_TOKEN_URL": settings.token_url,
        "SECONDME_USERINFO_URL": settings.userinfo_url,
        "SESSION_SECRET": settings.session_secret,
    }.items():
        if not value or value.startswith("replace-with-"):
            missing.append(name)
    if missing:
        raise HTTPException(status_code=500, detail={"message": "Missing backend configuration", "fields": missing})


def _debug_story_log(tag: str, payload: dict[str, Any]) -> None:
    """在开启调试开关时输出故事生成调试日志。"""
    if not DEBUG_STORY_GENERATION:
        return
    print(tag, json.dumps(payload, ensure_ascii=False), flush=True)


def _json_size_bytes(payload: Any) -> int:
    """粗略计算一个 JSON 负载序列化后的字节数。"""
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0


def _story_generation_debug_metadata() -> dict[str, Any]:
    """返回当前故事生成链路所用 provider 的调试信息。"""
    prose_provider = "volcengine" if _has_volcengine_prose_provider() else "secondme"
    prose_endpoint = _volcengine_chat_url() if prose_provider == "volcengine" else "https://api.mindverse.com/gate/lab/api/secondme/act/stream"
    prose_model = settings.volcengine_model if prose_provider == "volcengine" else "secondme-default"
    choices_provider = "volcengine" if _has_volcengine_prose_provider() else "secondme"
    choices_endpoint = _volcengine_chat_url() if choices_provider == "volcengine" else "https://api.mindverse.com/gate/lab/api/secondme/act/stream"
    choices_model = settings.volcengine_model if choices_provider == "volcengine" else "secondme-default"
    return {
        "structure": {
            "provider": "backend-template",
            "template": "high-drama-short-story-v1",
        },
        "choices": {
            "provider": choices_provider,
            "endpoint": choices_endpoint,
            "model": choices_model,
        },
        "prose": {
            "provider": prose_provider,
            "endpoint": prose_endpoint,
            "model": prose_model,
        },
    }


def _get_server_session(request: Request) -> dict[str, Any]:
    """从签名 cookie 中恢复当前登录用户和 access token。"""
    session = request.cookies.get("session")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_payload(session, settings.session_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid session")
    token = payload.get("token", {})
    user = payload.get("user", {})
    if not token.get("access_token"):
        raise HTTPException(status_code=401, detail="Session expired")
    return {"user": user, "token": token}


def _build_guest_session() -> dict[str, Any]:
    """构造受限游客会话：不包含 SecondMe token，仅用于游客可用能力。"""
    return {
        "isGuest": True,
        "user": {
            "userId": GUEST_USER_ID,
            "name": "游客",
            "route": "guest",
        },
        "token": {},
    }


def _get_server_or_guest_session(request: Request) -> dict[str, Any]:
    """优先返回登录会话，未登录时回退游客会话。"""
    try:
        return _get_server_session(request)
    except HTTPException:
        return _build_guest_session()


def _use_database_storage() -> bool:
    """判断当前是否启用数据库存储。"""
    return bool(settings.database_url.strip())


def _require_psycopg() -> None:
    """在启用数据库模式时确保 psycopg 可用。"""
    if psycopg is None:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is configured but psycopg is not installed on the backend runtime",
        )


@contextmanager
def _db_connection():
    """创建一个带统一错误包装的数据库连接上下文。"""
    _require_psycopg()
    try:
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            yield conn
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": "Database connection failed", "error": str(exc)}) from exc


def _load_stories_from_db() -> list[dict[str, Any]]:
    """从数据库读取已保存故事列表。"""
    return stories_repo.load_stories_from_db(_db_connection, psycopg)


def _load_stories() -> list[dict[str, Any]]:
    """按当前存储模式读取故事列表。"""
    return stories_repo.load_stories(_use_database_storage(), _db_connection, psycopg, STORIES_PATH)


def _save_story_record(record: dict[str, Any]) -> None:
    """把单条故事记录写入数据库。"""
    stories_repo.save_story_record(record, _db_connection)


def _save_stories(stories: list[dict[str, Any]]) -> None:
    """按当前存储模式保存故事列表。"""
    stories_repo.save_stories(stories, _use_database_storage(), _db_connection, DATA_DIR, STORIES_PATH)


def _delete_story_record(story_id: str, user_id: str) -> bool:
    """删除当前用户的一条已保存故事。"""
    return stories_repo.delete_story_record(story_id, user_id, _use_database_storage(), _db_connection, DATA_DIR, STORIES_PATH)


def _default_library_story_rows() -> list[dict[str, Any]]:
    """返回代码内置的默认书城模板，用于文件模式和数据库初始化。"""
    return stories_repo.default_library_story_rows(PRESET_OPENINGS, get_opening_title, get_opening_summary)


def _ensure_library_story_table() -> None:
    """确保数据库中存在书城模板表。"""
    stories_repo.ensure_library_story_table(_use_database_storage(), _db_connection)


def _seed_default_library_stories_in_db() -> None:
    """首次使用数据库模式时，把默认测试故事写入 library_stories。"""
    stories_repo.seed_default_library_stories_in_db(_use_database_storage(), _db_connection, _default_library_story_rows())


def _load_library_story_sources_from_db() -> list[dict[str, Any]]:
    """从数据库读取启用中的书城模板列表。"""
    return stories_repo.load_library_story_sources_from_db(_db_connection, psycopg, _default_library_story_rows())


def _load_library_story_sources() -> list[dict[str, Any]]:
    """按当前存储模式读取书城模板列表。"""
    return stories_repo.load_library_story_sources(
        _use_database_storage(),
        _db_connection,
        psycopg,
        PRESET_OPENINGS,
        get_opening_title,
        get_opening_summary,
    )


def _load_sessions_from_db() -> list[dict[str, Any]]:
    """从数据库读取故事会话列表。"""
    return sessions_repo.load_sessions_from_db(_db_connection, psycopg, _normalize_source_type)


def _load_sessions() -> list[dict[str, Any]]:
    """按当前存储模式读取故事会话列表。"""
    return sessions_repo.load_sessions(_use_database_storage(), _db_connection, psycopg, SESSIONS_PATH, _normalize_source_type)


def _load_library_seed_index_from_db() -> dict[str, dict[str, Any]]:
    """从数据库读取书城 seed package 的索引。"""
    return sessions_repo.load_library_seed_index_from_db(
        _db_connection,
        psycopg,
        LIBRARY_SEED_USER_ID,
        _clean_model_text,
        PACKAGE_VERSION,
    )


def _load_library_seed_index() -> dict[str, dict[str, Any]]:
    """按当前存储模式读取书城 seed 索引。"""
    return sessions_repo.load_library_seed_index(
        _use_database_storage(),
        _db_connection,
        psycopg,
        LIBRARY_SEED_USER_ID,
        _clean_model_text,
        PACKAGE_VERSION,
        SESSIONS_PATH,
        _normalize_source_type,
    )


def _find_library_seed_session_by_opening_id_from_db(story_id: str) -> Optional[dict[str, Any]]:
    """按 openingId 精确读取单条书城 seed，避免整表扫描到 Python 内存。"""
    return sessions_repo.find_library_seed_session_by_opening_id_from_db(
        _db_connection,
        psycopg,
        story_id,
        LIBRARY_SEED_USER_ID,
        PACKAGE_VERSION,
        _normalize_source_type,
    )


def _save_session_record(record: dict[str, Any]) -> None:
    """把单条故事会话记录写入数据库。"""
    sessions_repo.save_session_record(record, _db_connection, _normalize_source_type)


def _save_sessions(sessions: list[dict[str, Any]]) -> None:
    """按当前存储模式保存故事会话列表。"""
    sessions_repo.save_sessions(sessions, _use_database_storage(), _db_connection, _normalize_source_type, DATA_DIR, SESSIONS_PATH)


def _insert_new_session_record(session_record: dict[str, Any], sessions: Optional[list[dict[str, Any]]] = None) -> None:
    """新增单条 session；数据库模式下只写当前记录，避免全量回写。"""
    sessions_repo.insert_new_session_record(
        session_record,
        sessions,
        _use_database_storage(),
        _db_connection,
        _normalize_source_type,
        DATA_DIR,
        SESSIONS_PATH,
        psycopg,
    )

def _normalize_story_package(raw_text: str, opening: str, role: str, persona_profile: dict[str, Any]) -> dict[str, Any]:
    """把整包故事 JSON 解析成内部统一的 story package 结构。"""
    return _provider_normalize_story_package(
        raw_text=raw_text,
        opening=opening,
        role=role,
        persona_profile=persona_profile,
        clean_model_text=_clean_model_text,
        get_opening_title=get_opening_title,
        package_version=PACKAGE_VERSION,
        template_package_generator=TEMPLATE_PACKAGE_GENERATOR,
        story_generation_debug_metadata=_story_generation_debug_metadata,
        http_exception_cls=HTTPException,
    )


def _normalize_story_node_content(raw_text: str) -> dict[str, Any]:
    """把单节点正文 JSON 解析成内部统一结构。"""
    return _provider_normalize_story_node_content(
        raw_text=raw_text,
        clean_model_text=_clean_model_text,
        http_exception_cls=HTTPException,
    )


def _normalize_story_node_choices(raw_text: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    """把单节点选项 JSON 解析成内部统一结构。"""
    return _provider_normalize_story_node_choices(
        raw_text=raw_text,
        node=node,
        clean_model_text=_clean_model_text,
        http_exception_cls=HTTPException,
    )


def _find_session(session_id: str, user_id: str) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """按用户和会话 ID 查找故事会话。"""
    sessions = _load_sessions()
    for index, item in enumerate(sessions):
        if item.get("id") == session_id and item.get("userId") == user_id:
            return sessions, item, index
    raise HTTPException(status_code=404, detail="Story session not found")


def _package_matches(session: dict[str, Any], user_id: str, opening: str, role: str) -> bool:
    """判断一个故事包会话是否命中指定开头和角色。"""
    return package_matches(session, user_id, opening, role)


def _find_reusable_package(
    sessions: list[dict[str, Any]],
    user_id: str,
    opening: str,
    role: str,
    source_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """查找当前用户可直接复用的未完成故事包。"""
    return find_reusable_package(
        sessions=sessions,
        user_id=user_id,
        opening=opening,
        role=role,
        package_version=PACKAGE_VERSION,
        clean_model_text=_clean_model_text,
        legacy_package_generator=LEGACY_PACKAGE_GENERATOR,
        template_package_generator=TEMPLATE_PACKAGE_GENERATOR,
        source_type=source_type,
    )


def _node_generation_progress(
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    phase_nodes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """为节点生成流程计算当前进度信息。"""
    target_ids = phase_nodes or [item.get("id") for item in skeleton_nodes if item.get("id")]
    current_node_id = node.get("id")
    safe_target_ids = [node_id for node_id in target_ids if node_id]
    total = len(safe_target_ids)
    try:
        index = safe_target_ids.index(current_node_id) + 1 if current_node_id else 0
    except ValueError:
        index = 0
    return {
        "current": index,
        "total": total,
        "label": f"{index}/{total}" if index and total else "",
    }


def _build_story_from_session(session: dict[str, Any]) -> str:
    """把会话内容编译成可保存的完整故事文本。"""
    return build_story_from_session(session, _clean_model_text, get_opening_title, HTTPException)


def _build_story_from_completed_run(session: dict[str, Any], completed_run: dict[str, Any]) -> str:
    """把 story package 的 completed run 编译成完整故事文本。"""
    return build_story_from_completed_run(session, completed_run, _clean_model_text, get_opening_title)


def _derive_persona_profile(user: dict[str, Any]) -> dict[str, Any]:
    """根据 SecondMe 用户信息推导一个稳定的人设偏好画像。"""
    seed = f"{user.get('route', '')}|{user.get('name', '')}|{user.get('userId', '')}"
    styles = [
        {
            "key": "strategist",
            "label": "策略型分身",
            "preferredStyles": ["strategy", "manipulation", "observation"],
            "description": "更偏向试探、布局和控制风险。",
        },
        {
            "key": "empath",
            "label": "共情型分身",
            "preferredStyles": ["trust", "support", "observation"],
            "description": "更偏向理解他人、建立关系和稳住局势。",
        },
        {
            "key": "rebel",
            "label": "冲锋型分身",
            "preferredStyles": ["confrontation", "risk", "sacrifice"],
            "description": "更偏向正面碰撞、冒险推进和主动改变局面。",
        },
    ]
    total = sum(ord(char) for char in seed) if seed else 0
    profile = styles[total % len(styles)]
    return {
        **profile,
        "source": "secondme-user-heuristic",
    }




def _build_template_story_package_skeleton(opening: str, role: str) -> dict[str, Any]:
    """兼容主模块现有调用，转发到故事包领域模板骨架构造逻辑。"""
    return _domain_build_template_story_package_skeleton(
        opening=opening,
        role=role,
        get_opening_title=get_opening_title,
        get_opening_summary=get_opening_summary,
        package_version=PACKAGE_VERSION,
    )


def _story_package_validation_error_wrapper(story_package: dict[str, Any]) -> Optional[str]:
    """兼容生成服务现有签名，转发到领域层的故事包校验逻辑。"""
    return _story_package_validation_error(story_package, _clean_model_text)


def _finalize_story_package_wrapper(story_package: dict[str, Any], persona_profile: dict[str, Any]) -> dict[str, Any]:
    """兼容生成服务现有签名，转发到领域层的故事包收尾逻辑。"""
    return _finalize_story_package(
        story_package,
        persona_profile,
        _clean_model_text,
        PACKAGE_VERSION,
        TEMPLATE_PACKAGE_GENERATOR,
        _story_generation_debug_metadata,
    )


async def _generate_story_node_choices(
    access_token: Optional[str],
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    provider: str = "secondme",
    phase_nodes: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """调用指定 provider 为单个节点生成三条选项。"""
    if provider == "volcengine" and not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Volcengine provider is not configured for choice generation")
    endpoint = _volcengine_chat_url() if provider == "volcengine" else "https://api.mindverse.com/gate/lab/api/secondme/act/stream"
    model = settings.volcengine_model if provider == "volcengine" else "secondme-default"
    progress = _node_generation_progress(skeleton_nodes, node, phase_nodes)
    _debug_story_log(
        "[story-step]",
        {
            "step": "generate-node-choices",
            "nodeId": node.get("id"),
            "stageLabel": node.get("stageLabel"),
            "progress": progress["label"],
            "progressCurrent": progress["current"],
            "progressTotal": progress["total"],
            "provider": provider,
            "endpoint": endpoint,
            "model": model,
        },
    )
    last_error: Optional[HTTPException] = None
    for attempt in range(3):
        repair_hint = ""
        if last_error is not None:
            detail = last_error.detail if isinstance(last_error.detail, dict) else {"message": str(last_error.detail)}
            repair_hint = f"上一次选项输出失败，失败原因：{detail.get('message', 'unknown error')}。这次必须返回三个真正不同的选项。"
        prompt = _compose_story_choice_prompt(
            opening=opening,
            role=role,
            title=title,
            skeleton_nodes=skeleton_nodes,
            node=node,
            repair_hint=repair_hint,
        )
        if provider == "volcengine":
            raw_text = await _call_volcengine_prose(prompt=prompt, max_tokens=900, debug_log=_debug_story_log)
        else:
            if not access_token:
                raise HTTPException(status_code=500, detail="SecondMe access token is required for choice generation")
            raw_text = await _call_secondme_act(
                access_token=access_token,
                message=f"请为节点 {node.get('id')} 生成三个戏剧化选项",
                action_control=prompt,
                max_tokens=1400,
                debug_log=_debug_story_log,
            )
        try:
            return _normalize_story_node_choices(raw_text, node)
        except HTTPException as exc:
            _debug_story_log(
                "[story-choice-debug]",
                {
                    "attempt": attempt + 1,
                    "nodeId": node.get("id"),
                    "error": exc.detail,
                    "raw": raw_text,
                },
            )
            last_error = exc

    blueprints = node.get("choiceBlueprints", [])
    return [
        {
            "id": blueprint["id"],
            "text": blueprint["fallbackText"],
            "nextNodeId": blueprint["nextNodeId"],
            "style": blueprint["style"],
            "tone": blueprint["tone"],
            "effects": blueprint["effects"],
        }
        for blueprint in blueprints
    ]

async def _generate_story_node_content(
    access_token: Optional[str],
    opening: str,
    role: str,
    title: str,
    skeleton_nodes: list[dict[str, Any]],
    node: dict[str, Any],
    provider: str = "volcengine",
    phase_nodes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """调用指定 provider 为单个节点生成正文内容。"""
    prose_provider = provider
    if prose_provider == "volcengine" and not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Volcengine prose provider is not configured")
    prose_endpoint = _volcengine_chat_url() if prose_provider == "volcengine" else "https://api.mindverse.com/gate/lab/api/secondme/act/stream"
    prose_model = settings.volcengine_model if prose_provider == "volcengine" else "secondme-default"
    progress = _node_generation_progress(skeleton_nodes, node, phase_nodes)
    _debug_story_log(
        "[story-step]",
        {
            "step": "generate-node-prose",
            "nodeId": node.get("id"),
            "stageLabel": node.get("stageLabel"),
            "progress": progress["label"],
            "progressCurrent": progress["current"],
            "progressTotal": progress["total"],
            "provider": prose_provider,
            "endpoint": prose_endpoint,
            "model": prose_model,
        },
    )
    last_error: Optional[HTTPException] = None
    for attempt in range(3):
        repair_hint = ""
        if last_error is not None:
            detail = last_error.detail if isinstance(last_error.detail, dict) else {"message": str(last_error.detail)}
            repair_hint = f"上一次节点正文输出失败，失败原因：{detail.get('message', 'unknown error')}。这次必须修正。"
        if prose_provider != "volcengine" and not access_token:
            raise HTTPException(status_code=500, detail="SecondMe access token is required for prose generation")
        prompt = _compose_story_node_prompt(
            opening=opening,
            role=role,
            title=title,
            skeleton_nodes=skeleton_nodes,
            node=node,
            repair_hint=repair_hint,
        )
        raw_text = await (
            _call_volcengine_prose(prompt=prompt, max_tokens=1400, debug_log=_debug_story_log)
            if prose_provider == "volcengine"
            else _call_secondme_act(
                access_token=access_token or "",
                message=f"请补全节点 {node.get('id')} 的正文",
                action_control=prompt,
                max_tokens=2500,
                debug_log=_debug_story_log,
            )
        )
        try:
            return _normalize_story_node_content(raw_text)
        except HTTPException as exc:
            print(
                "[story-node-debug]",
                json.dumps(
                    {
                        "attempt": attempt + 1,
                        "nodeId": node.get("id"),
                        "role": role,
                        "error": exc.detail,
                        "raw": raw_text,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_error = exc
    detail = last_error.detail if last_error is not None and isinstance(last_error.detail, dict) else {"message": "Story node generation failed"}
    raise HTTPException(
        status_code=502,
        detail={
            "message": f"Node content generation failed for {node.get('id')} after 3 attempts",
            "reason": detail.get("message"),
        },
    )

#
# 两阶段路径：后端先固定分支结构，再让模型逐节点补选项和正文。
# 当前自定义故事仍然走这条链路。
async def _build_story_package_two_stage(
    access_token: Optional[str],
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
    choice_provider: str = "secondme",
    prose_provider: str = "volcengine",
) -> dict[str, Any]:
    """按“固定骨架，再补选项和正文”的两阶段方式生成故事包。"""
    return await build_story_package_two_stage(
        access_token=access_token,
        opening=opening,
        role=role,
        persona_profile=persona_profile,
        build_story_package_skeleton=_build_template_story_package_skeleton,
        generate_story_node_choices=_generate_story_node_choices,
        generate_story_node_content=_generate_story_node_content,
        finalize_story_package=_finalize_story_package_wrapper,
        story_package_validation_error=_story_package_validation_error_wrapper,
        http_exception_cls=HTTPException,
        choice_provider=choice_provider,
        prose_provider=prose_provider,
    )

#
# 单次整包路径：直接让豆包一次返回完整故事包 JSON。
# 这条链路暂时保留作兼容/实验用途，但书城首访播种已不再默认走这里。
async def _generate_story_package_single_call(
    opening: str,
    role: str,
    user_name: str,
    persona_profile: dict[str, Any],
) -> dict[str, Any]:
    """让模型一次返回完整故事包，用于兼容或实验链路。"""
    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Volcengine prose provider is not configured")
    last_error: Optional[HTTPException] = None
    for attempt in range(3):
        repair_hint = "请优先保证结构正确并一次返回完整故事包。"
        if last_error is not None:
            detail = last_error.detail if isinstance(last_error.detail, dict) else {"message": str(last_error.detail)}
            reason = detail.get("message", "unknown")
            repair_hint = f"上一次输出失败，原因：{reason}。这次请严格输出合法 JSON，不要额外文本。"
        prompt = _compose_story_package_prompt(
            opening=opening,
            role=role,
            user_name=user_name,
            persona_profile=persona_profile,
            repair_hint=repair_hint,
        )
        raw_text = await _call_volcengine_prose(prompt=prompt, max_tokens=2000, debug_log=_debug_story_log)
        try:
            return _normalize_story_package(
                raw_text=raw_text,
                opening=opening,
                role=role,
                persona_profile=persona_profile,
            )
        except HTTPException as exc:
            last_error = exc
            _debug_story_log(
                "[story-package-single-call-retry]",
                {
                    "attempt": attempt + 1,
                    "opening": opening[:80],
                    "error": exc.detail,
                },
            )
            if attempt < 2:
                await asyncio.sleep(0.35 * (attempt + 1))
                continue
            raise
    raise HTTPException(status_code=502, detail={"message": "Story package generation failed"})

def _infer_stage(turn_count: int, status: str) -> str:
    """按旧版逐回合流程推断当前故事阶段。"""
    if status == "complete":
        return "ending"
    if turn_count <= 1:
        return "opening"
    if turn_count <= 3:
        return "conflict"
    if turn_count <= 5:
        return "climax" if status != "ending" else "ending"
    return "ending"


def _update_story_state(previous_state: dict[str, Any], action: str, choice_texts: list[str], turn_count: int, status: str) -> dict[str, Any]:
    """按一次玩家行动更新旧版逐回合故事状态。"""
    flags = list(previous_state.get("flags", []))
    relationship = dict(previous_state.get("relationship", {"favor": 0}))
    persona = dict(
        previous_state.get(
            "persona",
            {"extrovert_introvert": 0, "scheming_naive": 0, "optimistic_pessimistic": 0},
        )
    )
    action_style = _choice_style(action)
    effects = _choice_effects(action_style)

    for key, value in effects.get("persona", {}).items():
        persona[key] = persona.get(key, 0) + value

    relationship["favor"] = relationship.get("favor", 0) + int(effects.get("relationship", {}).get("favor", 0))
    if action_style in {"trust", "support"} and "trust_path" not in flags:
        flags.append("trust_path")
    if action_style in {"confrontation", "risk"} and "conflict_spike" not in flags:
        flags.append("conflict_spike")
    if action_style in {"strategy", "manipulation", "observation"} and "foreshadowing_seed" not in flags:
        flags.append("foreshadowing_seed")
    if action_style == "manipulation" and "hidden_motive" not in flags:
        flags.append("hidden_motive")
    if any("相信" in choice or "利用" in choice or "揭穿" in choice for choice in choice_texts) and "reversal_ready" not in flags and turn_count >= 3:
        flags.append("reversal_ready")

    stage = _infer_stage(turn_count, status)
    ending_hint = ""
    if stage == "ending" and relationship.get("favor", 0) >= 2:
        ending_hint = "你在关键节点持续积累了好感，这条线更容易落到甜系收束。"
    elif stage == "ending" and relationship.get("favor", 0) <= -1:
        ending_hint = "你把关系推向了低好感区，结局会偏克制或遗憾。"
    elif stage == "ending" and "trust_path" in flags and "reversal_ready" in flags:
        ending_hint = "曾经建立的信任正在逼近一次反转兑现。"
    elif stage == "ending" and "hidden_motive" in flags:
        ending_hint = "你埋下的隐藏动机正在改变结局走向。"

    return {
        "stage": stage,
        "flags": flags,
        "relationship": relationship,
        "persona": persona,
        "turn": turn_count,
        "endingHint": ending_hint,
    }

async def _create_or_reuse_story_package(body: dict[str, Any], server_session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """按开头类型选择创建或复用 library/custom 故事包。"""
    return await create_or_reuse_story_package(
        body=body,
        server_session=server_session,
        clean_model_text=_clean_model_text,
        preset_openings=PRESET_OPENINGS,
        start_or_resume_library_story=_start_or_resume_library_story,
        start_or_generate_custom_story=_start_or_generate_custom_story,
        http_exception_cls=HTTPException,
    )


def _build_ending_analysis_context(
    session_id: str,
    story: str,
    meta: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """兼容路由层现有调用，转发到 session service 整理结局分析上下文。"""
    return build_ending_analysis_context(
        session_id=session_id,
        story=story,
        meta=meta,
        user_id=user_id,
        find_session=_find_session,
        http_exception_cls=HTTPException,
    )


def _build_library_story_rows(sessions: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """构造书城推荐故事列表及其 seed 状态。"""
    return build_library_story_rows(
        sessions=sessions,
        load_library_seed_index=_load_library_seed_index,
        load_library_story_sources=_load_library_story_sources,
        clean_model_text=_clean_model_text,
        library_seed_user_id=LIBRARY_SEED_USER_ID,
    )


def _resolve_library_opening(story_id: str) -> str:
    """把书城 story id 解析成对应的 opening 文案。"""
    return resolve_library_opening(
        story_id=story_id,
        build_library_story_rows=_build_library_story_rows,
        http_exception_cls=HTTPException,
    )


def _find_library_seed_session(sessions: Optional[list[dict[str, Any]]], story_id: str) -> Optional[dict[str, Any]]:
    """在会话列表里查找某个书城故事的全局 seed session。"""
    return find_library_seed_session(
        sessions=sessions,
        story_id=story_id,
        use_database_storage=_use_database_storage(),
        find_library_seed_session_by_opening_id_from_db=_find_library_seed_session_by_opening_id_from_db,
        load_sessions=_load_sessions,
        clean_model_text=_clean_model_text,
        library_seed_user_id=LIBRARY_SEED_USER_ID,
        package_version=PACKAGE_VERSION,
    )


def _require_library_seed_session(sessions: Optional[list[dict[str, Any]]], opening_id: str) -> dict[str, Any]:
    """读取指定书城故事的全局 seed；如果不存在则直接报错。"""
    return require_library_seed_session(
        sessions=sessions,
        opening_id=opening_id,
        find_library_seed_session=_find_library_seed_session,
        debug_story_log=_debug_story_log,
        http_exception_cls=HTTPException,
    )


async def _load_or_generate_library_seed_package(
    sessions: list[dict[str, Any]],
    opening: str,
    opening_id: str,
    seed_ready_from_client: bool,
    force_regenerate: bool = False,
    skip_existing_check: bool = False,
) -> tuple[dict[str, Any], bool]:
    """读取或首次生成某个书城开头对应的全局 seed package。"""
    return await load_or_generate_library_seed_package(
        sessions=sessions,
        opening=opening,
        opening_id=opening_id,
        seed_ready_from_client=seed_ready_from_client,
        force_regenerate=force_regenerate,
        skip_existing_check=skip_existing_check,
        load_sessions=_load_sessions,
        save_sessions=_save_sessions,
        clean_model_text=_clean_model_text,
        use_database_storage=_use_database_storage(),
        find_library_seed_session_by_opening_id_from_db=_find_library_seed_session_by_opening_id_from_db,
        has_volcengine_prose_provider=_has_volcengine_prose_provider,
        build_story_package_two_stage=_build_story_package_two_stage,
        debug_story_log=_debug_story_log,
        http_exception_cls=HTTPException,
        package_version=PACKAGE_VERSION,
        library_seed_user_id=LIBRARY_SEED_USER_ID,
        lock_dir=LIBRARY_SEED_LOCK_DIR,
        db_connection=_db_connection,
        wait_timeout_seconds=LIBRARY_SEED_WAIT_TIMEOUT_SECONDS,
        wait_interval_seconds=LIBRARY_SEED_WAIT_INTERVAL_SECONDS,
    )


async def _generate_library_seed_package(
    opening: str,
    opening_id: str,
    force_regenerate: bool = False,
    skip_existing_check: bool = False,
) -> tuple[dict[str, Any], bool]:
    """显式播种某本书城故事的全局 seed。"""
    return await generate_library_seed_package(
        opening=opening,
        opening_id=opening_id,
        force_regenerate=force_regenerate,
        skip_existing_check=skip_existing_check,
        load_sessions=_load_sessions,
        load_or_generate_library_seed_package=_load_or_generate_library_seed_package,
        find_library_seed_session=_find_library_seed_session,
        debug_story_log=_debug_story_log,
    )


def _build_story_package_session_payload(
    server_session: dict[str, Any],
    opening: str,
    role: str,
    source_type: str,
    story_package: dict[str, Any],
    opening_id: str = "",
) -> dict[str, Any]:
    """构造前端可直接游玩的 session-like payload，但不把未完成进度落库。"""
    user = server_session["user"]
    is_guest = bool(server_session.get("isGuest"))
    package_payload = deepcopy(story_package)
    if source_type == "library":
        package_payload["debug"] = {
            "structure": {"provider": "library-seed-cache", "openingId": opening_id},
            "choices": {"provider": "library-seed-cache", "openingId": opening_id},
            "prose": {"provider": "library-seed-cache", "openingId": opening_id},
        }
    persona_profile = _derive_persona_profile(user)
    now = int(time.time())
    session_record = {
        "id": random_urlsafe(10),
        "kind": "story_package",
        "createdAt": now,
        "updatedAt": now,
        "userId": user.get("userId"),
        "status": "ready",
        "packageStatus": "ready",
        "sourceType": source_type,
        "meta": {
            "opening": opening,
            "role": role,
            "author": user.get("name") or ("游客" if is_guest else "SecondMe 用户"),
            "sourceType": source_type,
            "viewerMode": "guest" if is_guest else "authenticated",
        },
        "personaProfile": persona_profile,
        "package": package_payload,
        "runtime": _initial_runtime_from_package(package_payload),
        "completedRun": None,
    }
    if opening_id:
        session_record["meta"]["openingId"] = opening_id
    return session_record


async def _ai_complete_workbench_node(server_session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """薄封装：隐藏工作台 AI 补写逻辑下沉到服务层。"""
    return await ai_complete_workbench_node_service(
        server_session=server_session,
        body=body,
        clean_model_text=_clean_model_text,
        has_volcengine_prose_provider=_has_volcengine_prose_provider,
        generate_story_node_choices=_generate_story_node_choices,
        generate_story_node_content=_generate_story_node_content,
        choice_style=_choice_style,
        choice_tone=_choice_tone,
        choice_effects=_choice_effects,
        fallback_choice_by_index=_fallback_choice_by_index,
        normalize_choice_effect_payload=_normalize_choice_effect_payload,
        package_version=PACKAGE_VERSION,
        template_package_generator=TEMPLATE_PACKAGE_GENERATOR,
        http_exception_cls=HTTPException,
    )


async def _ai_parse_workbench_outline(server_session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """薄封装：把剧情大纲解析为工作台节点图。"""
    return await ai_parse_workbench_outline_service(
        server_session=server_session,
        body=body,
        clean_model_text=_clean_model_text,
        has_volcengine_prose_provider=_has_volcengine_prose_provider,
        call_volcengine_prose=_call_volcengine_prose,
        call_secondme_act=_call_secondme_act,
        extract_json_object=_extract_json_object,
        choice_style=_choice_style,
        choice_tone=_choice_tone,
        choice_effects=_choice_effects,
        fallback_choice_by_index=_fallback_choice_by_index,
        normalize_choice_effect_payload=_normalize_choice_effect_payload,
        package_version=PACKAGE_VERSION,
        template_package_generator=TEMPLATE_PACKAGE_GENERATOR,
        http_exception_cls=HTTPException,
    )


def _import_library_story_package(server_session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """薄包装：把依赖装配后委托给导入服务层。"""
    return import_library_story_package_service(
        server_session=server_session,
        body=body,
        use_database_storage=_use_database_storage(),
        clean_model_text=_clean_model_text,
        story_package_validation_error=_story_package_validation_error_wrapper,
        ensure_library_story_table=_ensure_library_story_table,
        db_connection=_db_connection,
        save_session_record=_save_session_record,
        library_seed_user_id=LIBRARY_SEED_USER_ID,
        package_version=PACKAGE_VERSION,
        template_package_generator=TEMPLATE_PACKAGE_GENERATOR,
        http_exception_cls=HTTPException,
    )


def _delete_imported_library_story(story_id: str, current_user_id: str, is_operator: bool) -> dict[str, Any]:
    """薄包装：删除导入的书市故事与对应 seed。"""
    return delete_imported_library_story_service(
        story_id=story_id,
        current_user_id=current_user_id,
        is_operator=is_operator,
        use_database_storage=_use_database_storage(),
        db_connection=_db_connection,
        library_seed_user_id=LIBRARY_SEED_USER_ID,
        http_exception_cls=HTTPException,
    )


async def _start_or_resume_library_story(
    server_session: dict[str, Any],
    opening: str,
    role: str,
    opening_id: str,
    seed_ready_from_client: bool,
    force_regenerate: bool = False,
) -> tuple[dict[str, Any], bool, bool]:
    """为书城故事创建用户会话；点击书城始终新开一局，只复用全局 seed。"""
    sessions = _load_sessions()
    story_package, generated_now = await _load_or_generate_library_seed_package(
        sessions=sessions,
        opening=opening,
        opening_id=opening_id,
        seed_ready_from_client=seed_ready_from_client,
        force_regenerate=force_regenerate,
    )
    session_record = _build_story_package_session_payload(
        server_session,
        opening=opening,
        role=role,
        source_type="library",
        story_package=story_package,
        opening_id=opening_id,
    )
    if not bool(server_session.get("isGuest")):
        _insert_new_session_record(session_record, sessions)
    return session_record, False, generated_now


async def _start_or_generate_custom_story(
    server_session: dict[str, Any],
    opening: str,
    role: str,
    style_guidance: str = "",
    force_regenerate: bool = False,
) -> tuple[dict[str, Any], bool]:
    """为自定义开头生成一个前端本地游玩的故事 payload。"""
    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Doubao(Volcengine) is not configured for custom story generation")

    started_at = time.perf_counter()
    user = server_session["user"]
    persona_profile = _derive_persona_profile(user)
    generation_opening = (
        f"{opening}\n\n额外创作约束：{style_guidance}"
        if str(style_guidance or "").strip()
        else opening
    )
    print(
        "[custom-story-start]",
        json.dumps(
            {
                "userId": user.get("userId", ""),
                "role": role,
                "openingPreview": opening[:80],
                "hasStyleGuidance": bool(str(style_guidance or "").strip()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        story_package = await _build_story_package_two_stage(
            access_token=server_session["token"].get("access_token"),
            opening=generation_opening,
            role=role,
            user_name=user.get("name") or "SecondMe 用户",
            persona_profile=persona_profile,
            choice_provider="volcengine",
            prose_provider="volcengine",
        )
    except Exception as exc:
        print(
            "[custom-story-failed]",
            json.dumps(
                {
                    "userId": user.get("userId", ""),
                    "elapsedMs": int((time.perf_counter() - started_at) * 1000),
                    "error": repr(exc),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        raise
    print(
        "[custom-story-complete]",
        json.dumps(
            {
                "userId": user.get("userId", ""),
                "title": story_package.get("title", ""),
                "nodeCount": len(story_package.get("nodes", []) or []),
                "elapsedMs": int((time.perf_counter() - started_at) * 1000),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return (
        _build_story_package_session_payload(
            server_session,
            opening=opening,
            role=role,
            source_type="custom",
            story_package=story_package,
        ),
        False,
    )


def _mcp_result(request_id: Any, payload: Any) -> dict[str, Any]:
    """把普通 payload 包装成 MCP 成功响应。"""
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": content,
                }
            ]
        },
    }


def _mcp_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """构造 MCP 错误响应。"""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


ROUTE_DEPS = SimpleNamespace(
    ai_complete_workbench_node=_ai_complete_workbench_node,
    ai_parse_workbench_outline=_ai_parse_workbench_outline,
    build_library_story_rows=_build_library_story_rows,
    build_story_package_session_payload=_build_story_package_session_payload,
    call_secondme_chat=_call_secondme_chat,
    clean_model_text=_clean_model_text,
    compose_ending_analysis_prompt=_compose_ending_analysis_prompt,
    compose_story_prompt=_compose_story_prompt,
    cookie_path=COOKIE_PATH,
    create_or_reuse_story_package=_create_or_reuse_story_package,
    delete_story_record=_delete_story_record,
    build_ending_analysis_context=_build_ending_analysis_context,
    ensure_story_package_runtime=_ensure_story_package_runtime,
    find_session=_find_session,
    frontend_dist_dir=FRONTEND_DIST_DIR,
    generate_library_seed_package=_generate_library_seed_package,
    import_library_story_package=_import_library_story_package,
    delete_imported_library_story=_delete_imported_library_story,
    is_library_workbench_operator=_is_library_workbench_operator,
    require_library_workbench_operator=_require_library_workbench_operator,
    get_opening_summary=get_opening_summary,
    get_opening_title=get_opening_title,
    get_server_or_guest_session=_get_server_or_guest_session,
    get_server_session=_get_server_session,
    load_sessions=_load_sessions,
    load_stories=_load_stories,
    mcp_error=_mcp_error,
    mcp_result=_mcp_result,
    normalize_ending_analysis=_normalize_ending_analysis,
    preset_openings=PRESET_OPENINGS,
    require_env=_require_env,
    require_library_seed_session=_require_library_seed_session,
    resolve_library_opening=_resolve_library_opening,
    insert_new_session_record=_insert_new_session_record,
    save_stories=_save_stories,
    serialize_session=_serialize_session,
    story_package_validation_error=_story_package_validation_error_wrapper,
    start_or_generate_custom_story=_start_or_generate_custom_story,
)

app.include_router(create_system_router(ROUTE_DEPS))
app.include_router(create_auth_router(ROUTE_DEPS))
app.include_router(create_library_router(ROUTE_DEPS))
app.include_router(create_sessions_router(ROUTE_DEPS))
app.include_router(create_stories_router(ROUTE_DEPS))
app.include_router(create_mcp_router(ROUTE_DEPS))

if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    app.include_router(create_frontend_router(ROUTE_DEPS))
