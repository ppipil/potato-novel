from __future__ import annotations

import asyncio
import errno
import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Set
from urllib.parse import urlencode

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
from .integration import build_integration_manifest
from .model_providers import (
    _call_secondme_act,
    _call_secondme_chat,
    _call_volcengine_prose,
    _has_volcengine_prose_provider,
    _stream_volcengine_prose_chunks,
    _volcengine_chat_url,
)
from .openings import PRESET_OPENINGS, get_opening_summary, get_opening_title
from .security import random_urlsafe, sign_payload, verify_payload
from .story_prompts import (
    _compose_ending_analysis_prompt,
    _compose_story_choice_prompt,
    _compose_story_node_prompt,
    _compose_story_package_prompt,
    _compose_story_prompt,
)
from .story_text import (
    _clean_model_text,
    _extract_json_object,
    _normalize_ending_analysis,
    _split_scene_into_paragraphs,
)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _story_row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    """把 stories 表的数据库行转换成接口记录。"""
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "userId": row["user_id"],
        "meta": row.get("meta_json") or {},
        "story": row["story_text"],
    }


def _session_row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    """把 story_sessions 表的数据库行转换成运行时记录。"""
    meta = row.get("meta_json") or {}
    return {
        "id": row["id"],
        "kind": row["kind"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "userId": row["user_id"],
        "status": row.get("status") or "ready",
        "packageStatus": row.get("package_status") or "ready",
        "meta": meta,
        "sourceType": _normalize_source_type(meta.get("sourceType")),
        "runtime": meta.get("runtime") if isinstance(meta.get("runtime"), dict) else None,
        "personaProfile": row.get("persona_profile_json") or {},
        "package": row.get("package_json") or {},
        "completedRun": row.get("completed_run_json"),
    }


def _normalize_source_type(value: Any) -> str:
    """规范化故事来源类型，只保留 library 或 custom。"""
    normalized = str(value or "").strip().lower()
    if normalized in {"library", "custom"}:
        return normalized
    return "custom"


def _load_stories_from_db() -> list[dict[str, Any]]:
    """从数据库读取已保存故事列表。"""
    with _db_connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, user_id, title, story_text, meta_json, created_at, updated_at
            FROM stories
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        return [_story_row_to_record(row) for row in cur.fetchall()]


def _load_stories() -> list[dict[str, Any]]:
    """按当前存储模式读取故事列表。"""
    if _use_database_storage():
        return _load_stories_from_db()
    if not STORIES_PATH.exists():
        return []
    return json.loads(STORIES_PATH.read_text(encoding="utf-8"))


def _save_story_record(record: dict[str, Any]) -> None:
    """把单条故事记录写入数据库。"""
    with _db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stories (id, user_id, title, story_text, meta_json, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                title = EXCLUDED.title,
                story_text = EXCLUDED.story_text,
                meta_json = EXCLUDED.meta_json,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                record["id"],
                record["userId"],
                record.get("meta", {}).get("opening") or record.get("title") or "",
                record["story"],
                json.dumps(record.get("meta", {}), ensure_ascii=False),
                record["createdAt"],
                record.get("updatedAt", record["createdAt"]),
            ),
        )


def _save_stories(stories: list[dict[str, Any]]) -> None:
    """按当前存储模式保存故事列表。"""
    if _use_database_storage():
        for item in stories:
            _save_story_record(item)
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_PATH.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")


def _delete_story_record(story_id: str, user_id: str) -> bool:
    """删除当前用户的一条已保存故事。"""
    if _use_database_storage():
        with _db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM stories
                WHERE id = %s AND user_id = %s
                """,
                (story_id, user_id),
            )
            return cur.rowcount > 0

    stories = _load_stories()
    remaining = [item for item in stories if not (item.get("id") == story_id and item.get("userId") == user_id)]
    if len(remaining) == len(stories):
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_PATH.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _default_library_story_rows() -> list[dict[str, Any]]:
    """返回代码内置的默认书城模板，用于文件模式和数据库初始化。"""
    rows = []
    for index, opening in enumerate(PRESET_OPENINGS, start=1):
        rows.append(
            {
                "id": f"library-{index}",
                "opening": opening,
                "title": get_opening_title(opening),
                "summary": get_opening_summary(opening),
                "enabled": True,
                "sortOrder": index,
            }
        )
    return rows


def _ensure_library_story_table() -> None:
    """确保数据库中存在书城模板表。"""
    if not _use_database_storage():
        return
    with _db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS library_stories (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                opening TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """
        )


def _seed_default_library_stories_in_db() -> None:
    """首次使用数据库模式时，把默认测试故事写入 library_stories。"""
    if not _use_database_storage():
        return
    _ensure_library_story_table()
    defaults = _default_library_story_rows()
    now = int(time.time())
    with _db_connection() as conn, conn.cursor() as cur:
        for row in defaults:
            cur.execute(
                """
                INSERT INTO library_stories (id, title, summary, opening, enabled, sort_order, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    row["id"],
                    row["title"],
                    row["summary"],
                    row["opening"],
                    bool(row.get("enabled", True)),
                    int(row.get("sortOrder", 0)),
                    now,
                    now,
                ),
            )


def _load_library_story_sources_from_db() -> list[dict[str, Any]]:
    """从数据库读取启用中的书城模板列表。"""
    _seed_default_library_stories_in_db()
    with _db_connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, title, summary, opening, enabled, sort_order, created_at, updated_at
            FROM library_stories
            WHERE enabled = TRUE
            ORDER BY sort_order ASC, created_at ASC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "opening": row["opening"],
            "enabled": bool(row.get("enabled", True)),
            "sortOrder": int(row.get("sort_order", 0) or 0),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }
        for row in rows
    ]


def _load_library_story_sources() -> list[dict[str, Any]]:
    """按当前存储模式读取书城模板列表。"""
    if _use_database_storage():
        return _load_library_story_sources_from_db()
    return _default_library_story_rows()


def _load_sessions_from_db() -> list[dict[str, Any]]:
    """从数据库读取故事会话列表。"""
    with _db_connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT
                id,
                user_id,
                kind,
                status,
                package_status,
                meta_json,
                persona_profile_json,
                package_json,
                completed_run_json,
                created_at,
                updated_at
            FROM story_sessions
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        return [_session_row_to_record(row) for row in cur.fetchall()]


def _load_sessions() -> list[dict[str, Any]]:
    """按当前存储模式读取故事会话列表。"""
    if _use_database_storage():
        return _load_sessions_from_db()
    if not SESSIONS_PATH.exists():
        return []
    return json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))


def _load_library_seed_index_from_db() -> dict[str, dict[str, Any]]:
    """从数据库读取书城 seed package 的索引。"""
    with _db_connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, meta_json, updated_at, status, package_status
            FROM story_sessions
            WHERE kind = 'library_seed_package' AND user_id = %s
            ORDER BY updated_at DESC
            """,
            (LIBRARY_SEED_USER_ID,),
        )
        rows = cur.fetchall()
    seed_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = row.get("meta_json") or {}
        opening_id = _clean_model_text(meta.get("openingId", ""))
        if not opening_id:
            continue
        if opening_id in seed_map:
            continue
        seed_map[opening_id] = {
            "id": row.get("id"),
            "updatedAt": row.get("updated_at"),
            "status": row.get("status") or "ready",
            "packageStatus": row.get("package_status") or "ready",
        }
    return seed_map


def _load_library_seed_index() -> dict[str, dict[str, Any]]:
    """按当前存储模式读取书城 seed 索引。"""
    if _use_database_storage():
        return _load_library_seed_index_from_db()
    sessions = _load_sessions()
    seed_map: dict[str, dict[str, Any]] = {}
    for item in sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != LIBRARY_SEED_USER_ID:
            continue
        opening_id = _clean_model_text(item.get("meta", {}).get("openingId", ""))
        if not opening_id or opening_id in seed_map:
            continue
        seed_map[opening_id] = {
            "id": item.get("id"),
            "updatedAt": item.get("updatedAt"),
            "status": item.get("status", "ready"),
            "packageStatus": item.get("packageStatus", "ready"),
        }
    return seed_map


def _find_library_seed_session_by_opening_id_from_db(story_id: str) -> Optional[dict[str, Any]]:
    """按 openingId 精确读取单条书城 seed，避免整表扫描到 Python 内存。"""
    with _db_connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT
                id,
                user_id,
                kind,
                status,
                package_status,
                meta_json,
                persona_profile_json,
                package_json,
                completed_run_json,
                created_at,
                updated_at
            FROM story_sessions
            WHERE kind = 'library_seed_package'
              AND user_id = %s
              AND meta_json ->> 'openingId' = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (LIBRARY_SEED_USER_ID, story_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    record = _session_row_to_record(row)
    package = record.get("package", {})
    if package.get("version") != PACKAGE_VERSION:
        return None
    return record


def _save_session_record(record: dict[str, Any]) -> None:
    """把单条故事会话记录写入数据库。"""
    meta_payload = {
        **record.get("meta", {}),
        "sourceType": _normalize_source_type(record.get("sourceType") or record.get("meta", {}).get("sourceType")),
    }
    if isinstance(record.get("runtime"), dict):
        meta_payload["runtime"] = record.get("runtime")
    with _db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO story_sessions (
                id,
                user_id,
                kind,
                status,
                package_status,
                meta_json,
                persona_profile_json,
                package_json,
                completed_run_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                kind = EXCLUDED.kind,
                status = EXCLUDED.status,
                package_status = EXCLUDED.package_status,
                meta_json = EXCLUDED.meta_json,
                persona_profile_json = EXCLUDED.persona_profile_json,
                package_json = EXCLUDED.package_json,
                completed_run_json = EXCLUDED.completed_run_json,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                record["id"],
                record["userId"],
                record["kind"],
                record.get("status", "ready"),
                record.get("packageStatus", "ready"),
                json.dumps(meta_payload, ensure_ascii=False),
                json.dumps(record.get("personaProfile", {}), ensure_ascii=False),
                json.dumps(record.get("package", {}), ensure_ascii=False),
                json.dumps(record.get("completedRun"), ensure_ascii=False) if record.get("completedRun") is not None else None,
                record["createdAt"],
                record["updatedAt"],
            ),
        )


def _save_sessions(sessions: list[dict[str, Any]]) -> None:
    """按当前存储模式保存故事会话列表。"""
    if _use_database_storage():
        for item in sessions:
            _save_session_record(item)
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_PATH.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def _insert_new_session_record(session_record: dict[str, Any], sessions: Optional[list[dict[str, Any]]] = None) -> None:
    """新增单条 session；数据库模式下只写当前记录，避免全量回写。"""
    if _use_database_storage():
        _save_session_record(session_record)
        return
    active_sessions = sessions if sessions is not None else _load_sessions()
    active_sessions.insert(0, session_record)
    _save_sessions(active_sessions)

def _normalize_choice_effect_payload(payload: Any, fallback_style: str) -> dict[str, dict[str, int]]:
    """规范化选项 effects，并在缺失时按风格补默认值。"""
    normalized = {"persona": {}, "relationship": {}}
    if isinstance(payload, dict):
        for category in ("persona", "relationship"):
            category_payload = payload.get(category, {})
            if isinstance(category_payload, dict):
                normalized[category] = {
                    _clean_model_text(key): int(value)
                    for key, value in category_payload.items()
                    if _clean_model_text(key) and isinstance(value, (int, float))
                }
    fallback = _choice_effects(fallback_style)
    for category in ("persona", "relationship"):
        if not normalized[category]:
            normalized[category] = fallback.get(category, {})
    return normalized


def _normalize_story_package(raw_text: str, opening: str, role: str, persona_profile: dict[str, Any]) -> dict[str, Any]:
    """把整包故事 JSON 解析成内部统一的 story package 结构。"""
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story package JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_nodes = payload.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise HTTPException(status_code=400, detail={"message": "Story package nodes must be an array", "body": raw_text})

    nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = _clean_model_text(raw_node.get("id", f"N{index}")) or f"N{index}"
        kind = _clean_model_text(raw_node.get("kind", "turn")).lower()
        if kind not in {"turn", "ending"}:
            kind = "turn"
        turn = raw_node.get("turn", index)
        if not isinstance(turn, int):
            turn = index
        scene = _clean_model_text(raw_node.get("scene", ""))
        if not scene:
            continue
        summary = _clean_model_text(raw_node.get("summary", "")) or scene
        stage_label = _clean_model_text(raw_node.get("stageLabel", "剧情推进")) or "剧情推进"
        director_note = _clean_model_text(raw_node.get("directorNote", ""))
        raw_choices = raw_node.get("choices", [])
        if not isinstance(raw_choices, list):
            raw_choices = []
        choices = []
        if kind == "turn":
            for choice_index, raw_choice in enumerate(raw_choices[:3], start=1):
                if not isinstance(raw_choice, dict):
                    continue
                text = _clean_model_text(raw_choice.get("text", ""))
                next_node_id = _clean_model_text(raw_choice.get("nextNodeId", ""))
                if not text or not next_node_id:
                    continue
                style = _clean_model_text(raw_choice.get("style", "")) or _choice_style(text)
                tone = _clean_model_text(raw_choice.get("tone", "")) or _choice_tone(text, style)
                choices.append(
                    {
                        "id": _clean_model_text(raw_choice.get("id", f"{node_id}-C{choice_index}")) or f"{node_id}-C{choice_index}",
                        "text": text,
                        "nextNodeId": next_node_id,
                        "style": style,
                        "tone": tone,
                        "effects": _normalize_choice_effect_payload(raw_choice.get("effects"), style),
                    }
                )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "turn": turn,
                "stageLabel": stage_label,
                "directorNote": director_note,
                "scene": scene,
                "paragraphs": _split_scene_into_paragraphs(scene),
                "summary": summary,
                "choices": choices if kind == "turn" else [],
            }
        )

    story_package = {
        "version": PACKAGE_VERSION,
        "title": _clean_model_text(payload.get("title", "")) or get_opening_title(opening) or "未命名互动宇宙",
        "opening": opening,
        "role": role,
        "rootNodeId": _clean_model_text(payload.get("rootNodeId", "N1")) or "N1",
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"好感": 0, "信任": 0, "警惕": 0},
            "persona": {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0},
            "turn": 1,
            "endingHint": "",
        },
    }
    validation_error = _story_package_validation_error(story_package)
    if validation_error:
        raise HTTPException(status_code=400, detail={"message": validation_error, "body": raw_text})
    return _finalize_story_package(story_package, persona_profile)


def _normalize_story_node_content(raw_text: str) -> dict[str, Any]:
    """把单节点正文 JSON 解析成内部统一结构。"""
    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story node JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc
    scene = _clean_model_text(payload.get("scene", ""))
    if not scene:
        raise HTTPException(status_code=400, detail={"message": "Story node scene is missing", "body": raw_text})
    stage_label = _clean_model_text(payload.get("stageLabel", "剧情推进")) or "剧情推进"
    director_note = _clean_model_text(payload.get("directorNote", ""))
    summary = _clean_model_text(payload.get("summary", "")) or scene
    return {
        "stageLabel": stage_label,
        "directorNote": director_note,
        "scene": scene,
        "paragraphs": _split_scene_into_paragraphs(scene),
        "summary": summary,
    }


def _normalize_story_node_choices(raw_text: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    """把单节点选项 JSON 解析成内部统一结构。"""
    blueprints = node.get("choiceBlueprints", [])
    if not isinstance(blueprints, list) or len(blueprints) != 3:
        raise HTTPException(status_code=400, detail={"message": "Story node is missing choice blueprints", "node": node.get("id")})

    try:
        payload = _extract_json_object(raw_text)
    except HTTPException as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Story choice JSON parse failed",
                "body": raw_text,
                "error": exc.detail if isinstance(exc.detail, dict) else str(exc.detail),
            },
        ) from exc

    raw_choices = payload.get("choices", [])
    if not isinstance(raw_choices, list):
        raw_choices = []

    provided_texts: list[str] = []
    for raw_choice in raw_choices[:3]:
        if isinstance(raw_choice, dict):
            provided_texts.append(_clean_model_text(raw_choice.get("text", "")))
        else:
            provided_texts.append(_clean_model_text(raw_choice))

    distinct_texts: list[str] = []
    seen: set[str] = set()
    for index, blueprint in enumerate(blueprints):
        candidate = provided_texts[index] if index < len(provided_texts) else ""
        if not candidate or candidate in seen:
            candidate = _clean_model_text(blueprint.get("fallbackText", ""))
        if candidate in seen:
            candidate = _fallback_choice_by_index(index, node.get("summary", ""))
        distinct_texts.append(candidate)
        seen.add(candidate)

    choices: list[dict[str, Any]] = []
    for blueprint, text in zip(blueprints, distinct_texts):
        style = _clean_model_text(blueprint.get("style", "")) or _choice_style(text)
        choices.append(
            {
                "id": _clean_model_text(blueprint.get("id", "")) or f"{node.get('id')}-{len(choices) + 1}",
                "text": text,
                "nextNodeId": _clean_model_text(blueprint.get("nextNodeId", "")),
                "style": style,
                "tone": _clean_model_text(blueprint.get("tone", "")) or _choice_tone(text, style),
                "effects": _normalize_choice_effect_payload(blueprint.get("effects"), style),
            }
        )
    return choices


def _ensure_distinct_choices(choices: list[str], scene: str = "") -> list[str]:
    """尽量保证三个选项在风格上彼此不同。"""
    distinct = []
    seen_styles = set()
    fallback_by_style = {
        "confrontation": "我盯着他的眼睛，半点没退：“你要是真想瞒我，就不会露出这种表情。现在，告诉我实话。”",
        "soft": "我放轻声音：“你可以不马上解释清楚，但至少别把我推开。让我陪你一起面对。”",
        "tease": "我偏头笑了一下：“原来你也会紧张？那我是不是该重新认识一下你了？”",
    }
    ordered_styles = ["confrontation", "soft", "tease"]

    for choice in choices:
        style = _choice_style(choice)
        if style in seen_styles:
            continue
        distinct.append(choice)
        seen_styles.add(style)

    for style in ordered_styles:
        if len(distinct) >= 3:
            break
        if style in seen_styles:
            continue
        distinct.append(fallback_by_style[style])
        seen_styles.add(style)

    while len(distinct) < 3:
        distinct.append(_fallback_choice_by_index(len(distinct), scene))
    return distinct[:3]


def _fallback_choice_by_index(index: int, scene: str) -> str:
    """按位置返回一个兜底选项文案。"""
    fallbacks = [
        "我低声开口：“你先别躲，我想听你亲口说。”",
        "我故意弯起眼睛笑了笑：“如果你想试探我，那我也不介意陪你玩到底。”",
        "我没有马上接话，只是顺着他的动作慢慢逼近一步，想看他会不会先失态。"] 
    if 0 <= index < len(fallbacks):
        return fallbacks[index]
    return f"我顺着眼前的局势轻声说出第 {index + 1} 种回应，试探他的真实态度。"

def _find_session(session_id: str, user_id: str) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """按用户和会话 ID 查找故事会话。"""
    sessions = _load_sessions()
    for index, item in enumerate(sessions):
        if item.get("id") == session_id and item.get("userId") == user_id:
            return sessions, item, index
    raise HTTPException(status_code=404, detail="Story session not found")


def _package_matches(session: dict[str, Any], user_id: str, opening: str, role: str) -> bool:
    """判断一个故事包会话是否命中指定开头和角色。"""
    return (
        session.get("userId") == user_id
        and session.get("meta", {}).get("opening", "").strip() == opening.strip()
        and session.get("meta", {}).get("role", "").strip() == role.strip()
    )


def _find_reusable_package(
    sessions: list[dict[str, Any]],
    user_id: str,
    opening: str,
    role: str,
    source_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """查找当前用户可直接复用的未完成故事包。"""
    for item in sessions:
        if not _package_matches(item, user_id, opening, role):
            continue
        if item.get("kind") != "story_package":
            continue
        if source_type and _normalize_source_type(item.get("sourceType") or item.get("meta", {}).get("sourceType")) != source_type:
            continue
        if source_type == "library" and not _clean_model_text(item.get("meta", {}).get("openingId", "")):
            # 忽略旧版本遗留的 library session；那时还没有 openingId 级别的 seed 复用。
            continue
        if item.get("completedRun"):
            continue
        if str(item.get("status", "")).strip().lower() == "complete":
            continue
        runtime = item.get("runtime")
        if isinstance(runtime, dict) and str(runtime.get("status", "")).strip().lower() == "complete":
            continue
        if item.get("packageStatus") not in {"ready", "hydrating"}:
            continue
        package = item.get("package", {})
        if package.get("version") != PACKAGE_VERSION:
            continue
        if package.get("generatedBy") not in {LEGACY_PACKAGE_GENERATOR, TEMPLATE_PACKAGE_GENERATOR}:
            continue
        return item
    return None


def _initial_runtime_from_package(story_package: dict[str, Any]) -> dict[str, Any]:
    """根据故事包根节点构造初始阅读 runtime。"""
    root_node_id = story_package.get("rootNodeId")
    nodes = story_package.get("nodes", [])
    node_map = {node.get("id"): node for node in nodes}
    root_node = node_map.get(root_node_id)
    if not root_node:
        raise HTTPException(status_code=400, detail="Story package root node is missing")
    entries = [
        {"turn": root_node.get("turn"), "label": root_node.get("stageLabel"), "text": root_node.get("scene", "")},
    ]
    director_note = _clean_model_text(root_node.get("directorNote", ""))
    if director_note:
        entries.append({"turn": root_node.get("turn"), "label": "局势提示", "text": director_note})
    return {
        "currentNodeId": root_node_id,
        "entries": entries,
        "path": [],
        "state": story_package.get("initialState", {}),
        "status": "complete" if root_node.get("kind") == "ending" else "ongoing",
        "endingNodeId": root_node_id if root_node.get("kind") == "ending" else "",
        "summary": _clean_model_text(root_node.get("summary", "")) if root_node.get("kind") == "ending" else "",
    }


def _ensure_story_package_runtime(session: dict[str, Any]) -> dict[str, Any]:
    """确保故事包会话上始终带有可用的 runtime。"""
    runtime = session.get("runtime")
    package = session.get("package", {})
    node_map = {node.get("id"): node for node in package.get("nodes", [])}
    if isinstance(runtime, dict) and runtime.get("currentNodeId") in node_map:
        return runtime
    runtime = _initial_runtime_from_package(package)
    session["runtime"] = runtime
    return runtime


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


def _serialize_session(session: dict[str, Any]) -> dict[str, Any]:
    """把内部会话结构裁剪成前端可消费的响应格式。"""
    if session.get("kind") == "story_package":
        source_type = _normalize_source_type(session.get("sourceType") or session.get("meta", {}).get("sourceType"))
        meta = {**session.get("meta", {})}
        meta.pop("runtime", None)
        meta["sourceType"] = source_type
        return {
            "id": session["id"],
            "kind": "story_package",
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"],
            "status": session.get("status", "ready"),
            "packageStatus": session.get("packageStatus", "ready"),
            "sourceType": source_type,
            "meta": meta,
            "package": session.get("package", {}),
            "completedRun": session.get("completedRun"),
            "runtime": session.get("runtime"),
        }
    return {
        "id": session["id"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "status": session["status"],
        "turnCount": session["turnCount"],
        "meta": session["meta"],
        "summary": _clean_model_text(session.get("summary", "")),
        "currentScene": _clean_model_text(session.get("currentScene", "")),
        "paragraphs": [_clean_model_text(item) for item in session.get("paragraphs", []) if _clean_model_text(item)],
        "choices": session.get("choices", []),
        "stageLabel": _clean_model_text(session.get("stageLabel", "剧情推进")) or "剧情推进",
        "directorNote": _clean_model_text(session.get("directorNote", "")),
        "state": session.get("state", {}),
        "personaProfile": session.get("personaProfile", {}),
        "recommendedChoiceId": session.get("recommendedChoiceId"),
        "aiChoiceId": session.get("aiChoiceId"),
        "transcript": [
            {
                **item,
                "label": _clean_model_text(item.get("label", "")),
                "text": _clean_model_text(item.get("text", "")),
            }
            for item in session.get("transcript", [])
        ],
    }


def _build_story_from_session(session: dict[str, Any]) -> str:
    """把会话内容编译成可保存的完整故事文本。"""
    if session.get("kind") == "story_package":
        completed_run = session.get("completedRun")
        if not completed_run:
            raise HTTPException(status_code=400, detail="Story package has not been completed")
        return _build_story_from_completed_run(session, completed_run)

    title = get_opening_title(session["meta"].get("opening", "")) or "未命名故事"
    lines = [
        f"《{title}：互动版》",
        f"玩家身份：{session['meta'].get('role', '')}",
        f"创作者：{session['meta'].get('author', '')}",
        "",
        "【故事开端】",
        session["meta"].get("opening", ""),
        "",
    ]
    for item in session.get("transcript", []):
        label = item.get("label", "事件")
        turn = item.get("turn")
        prefix = f"第 {turn} 回合" if turn else "故事片段"
        lines.append(f"【{prefix}·{label}】")
        lines.append(item.get("text", ""))
        lines.append("")
    if session.get("summary"):
        lines.extend(["【结局摘要】", session["summary"], ""])
    state = session.get("state", {})
    if state:
        lines.extend(
            [
                "【结局状态】",
                f"阶段：{state.get('stage', '')}",
                f"旗标：{', '.join(state.get('flags', [])) or '无'}",
                f"关系：{json.dumps(state.get('relationship', {}), ensure_ascii=False)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _build_story_from_completed_run(session: dict[str, Any], completed_run: dict[str, Any]) -> str:
    """把 story package 的 completed run 编译成完整故事文本。"""
    title = session.get("package", {}).get("title") or get_opening_title(session["meta"].get("opening", "")) or "未命名故事"
    lines = [
        f"《{title}：互动版》",
        f"玩家身份：{session['meta'].get('role', '')}",
        f"创作者：{session['meta'].get('author', '')}",
        "",
        "【故事开端】",
        session["meta"].get("opening", ""),
        "",
    ]
    for item in completed_run.get("transcript", []):
        label = item.get("label", "事件")
        turn = item.get("turn")
        prefix = f"第 {turn} 回合" if turn else "故事片段"
        lines.append(f"【{prefix}·{label}】")
        lines.append(_clean_model_text(item.get("text", "")))
        lines.append("")
    summary = _clean_model_text(completed_run.get("summary", ""))
    if summary:
        lines.extend(["【结局摘要】", summary, ""])
    state = completed_run.get("state", {})
    if state:
        lines.extend(
            [
                "【结局状态】",
                f"阶段：{state.get('stage', '')}",
                f"旗标：{', '.join(state.get('flags', [])) or '无'}",
                f"关系：{json.dumps(state.get('relationship', {}), ensure_ascii=False)}",
                f"人格：{json.dumps(state.get('persona', {}), ensure_ascii=False)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


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


def _choice_style(choice: str) -> str:
    """根据选项文案粗略推断其风格标签。"""
    mapping = [
        ("“", "dialogue"),
        ("”", "dialogue"),
        ("我笑", "tease"),
        ("笑了一下", "tease"),
        ("偏头", "tease"),
        ("靠近", "tease"),
        ("质问", "confrontation"),
        ("揭穿", "confrontation"),
        ("逼", "confrontation"),
        ("你到底", "confrontation"),
        ("为什么", "confrontation"),
        ("试探", "strategy"),
        ("假装", "strategy"),
        ("套话", "strategy"),
        ("离开", "observation"),
        ("观察", "observation"),
        ("躲", "observation"),
        ("相信", "trust"),
        ("陪你", "soft"),
        ("别怕", "soft"),
        ("没关系", "soft"),
        ("我会", "soft"),
        ("保护", "support"),
        ("安抚", "support"),
        ("利用", "manipulation"),
        ("诱导", "manipulation"),
        ("交易", "manipulation"),
        ("冒险", "risk"),
        ("闯", "risk"),
        ("牺牲", "sacrifice"),
    ]
    for keyword, style in mapping:
        if keyword in choice:
            return style
    return "dialogue"


def _choice_tone(choice: str, style: str) -> str:
    """根据风格映射出更适合展示的语气标签。"""
    if style == "tease":
        return "撩拨"
    if style in {"soft", "support", "trust"}:
        return "温柔"
    if style == "confrontation":
        return "强势"
    if style in {"strategy", "manipulation"}:
        return "试探"
    if style == "observation":
        return "克制"
    if style == "risk":
        return "冒险"
    return "生活化"


def _choice_effects(style: str) -> dict[str, dict[str, int]]:
    """根据选项风格生成默认的人格与关系数值影响。"""
    persona_effect = {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0}
    relationship_effect = {"好感": 0, "信任": 0, "警惕": 0}

    if style in {"soft", "support", "trust"}:
        persona_effect["真诚"] += 1
        relationship_effect["好感"] += 1
        relationship_effect["信任"] += 1
    elif style == "tease":
        persona_effect["胆量"] += 1
        relationship_effect["好感"] += 1
    elif style == "confrontation":
        persona_effect["嘴硬"] += 1
        persona_effect["胆量"] += 1
        relationship_effect["警惕"] += 1
    elif style in {"strategy", "manipulation"}:
        persona_effect["心机"] += 1
        relationship_effect["警惕"] += 1
    elif style == "observation":
        persona_effect["心机"] += 1
    elif style == "risk":
        persona_effect["胆量"] += 1
        relationship_effect["警惕"] += 1

    return {
        "persona": {key: value for key, value in persona_effect.items() if value},
        "relationship": {key: value for key, value in relationship_effect.items() if value},
    }

def _infer_stage_from_turn(turn_count: int, total_turns: int, kind: str) -> str:
    """根据节点回合数推断它在整局中的戏剧阶段。"""
    if kind == "ending":
        return "ending"
    if turn_count <= 1:
        return "opening"
    if turn_count >= max(total_turns - 1, 3):
        return "climax"
    return "conflict"


def _build_choice_objects(choice_texts: list[str], persona_profile: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    """把纯文本选项补齐成前端可直接展示的完整对象。"""
    preferred_styles = persona_profile.get("preferredStyles", [])
    choice_objects = []
    recommended_choice_id = None
    ai_choice_id = None

    for index, text in enumerate(choice_texts, start=1):
        style = _choice_style(text)
        choice_id = f"C{index}"
        effects = _choice_effects(style)
        choice = {
            "id": choice_id,
            "text": text,
            "style": style,
            "tone": _choice_tone(text, style),
            "effects": effects,
            "isRecommended": False,
            "isAiChoice": False,
        }
        if recommended_choice_id is None and (style in preferred_styles or (style == "soft" and "support" in preferred_styles)):
            recommended_choice_id = choice_id
        choice_objects.append(choice)

    if recommended_choice_id is None and choice_objects:
        recommended_choice_id = choice_objects[0]["id"]
    ai_choice_id = recommended_choice_id

    for choice in choice_objects:
        if choice["id"] == recommended_choice_id:
            choice["isRecommended"] = True
        if choice["id"] == ai_choice_id:
            choice["isAiChoice"] = True
    return choice_objects, recommended_choice_id, ai_choice_id


def _finalize_story_package(story_package: dict[str, Any], persona_profile: dict[str, Any]) -> dict[str, Any]:
    """为故事包补齐推荐信息、阶段信息和调试元数据。"""
    story_package["version"] = PACKAGE_VERSION
    story_package["generatedBy"] = TEMPLATE_PACKAGE_GENERATOR
    story_package["debug"] = _story_generation_debug_metadata()
    nodes = story_package.get("nodes", [])
    node_map = {node["id"]: node for node in nodes}
    playable_count = sum(1 for node in nodes if node.get("kind") == "turn")
    for node in nodes:
        if node.get("kind") != "turn":
            continue
        choice_objects = []
        raw_choices = node.get("choices", [])
        if not raw_choices:
            continue
        choice_payloads = [choice.get("text", "") for choice in raw_choices]
        recommendation_basis, _, _ = _build_choice_objects(choice_payloads, persona_profile)
        for index, choice in enumerate(raw_choices, start=1):
            style = choice.get("style") or _choice_style(choice.get("text", ""))
            tone = choice.get("tone") or _choice_tone(choice.get("text", ""), style)
            normalized_choice = {
                "id": choice.get("id") or f"{node['id']}-C{index}",
                "text": _clean_model_text(choice.get("text", "")),
                "nextNodeId": _clean_model_text(choice.get("nextNodeId", "")),
                "style": style,
                "tone": tone,
                "effects": _normalize_choice_effect_payload(choice.get("effects"), style),
                "isRecommended": False,
                "isAiChoice": False,
            }
            basis = recommendation_basis[index - 1] if index - 1 < len(recommendation_basis) else {}
            normalized_choice["isRecommended"] = bool(basis.get("isRecommended"))
            normalized_choice["isAiChoice"] = bool(basis.get("isAiChoice"))
            choice_objects.append(normalized_choice)
        node["choices"] = choice_objects
        node["turn"] = int(node.get("turn", 1))
        node["stage"] = _infer_stage_from_turn(node["turn"], playable_count, "turn")
        for choice in node["choices"]:
            next_node = node_map.get(choice["nextNodeId"])
            if next_node and next_node.get("kind") == "ending":
                choice["effects"]["relationship"] = {
                    **choice["effects"].get("relationship", {}),
                }
    story_package["playableTurnCount"] = playable_count
    story_package["endingNodeIds"] = [node["id"] for node in nodes if node.get("kind") == "ending"]
    return story_package
    
# 单次整包生成和两阶段生成共用这一套故事包校验逻辑。
def _story_package_validation_error(story_package: dict[str, Any]) -> Optional[str]:
    """校验 story package 是否满足当前可玩结构约束。"""
    nodes = story_package.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return "Story package must contain nodes"
    node_map = {node.get("id"): node for node in nodes if node.get("id")}
    root_node_id = story_package.get("rootNodeId")
    if root_node_id not in node_map:
        return "rootNodeId must point to an existing node"
    playable_nodes = [node for node in nodes if node.get("kind") == "turn"]
    ending_nodes = [node for node in nodes if node.get("kind") == "ending"]
    if len(playable_nodes) < 2:
        return "Story package must contain at least 2 playable turn nodes"
    if len(ending_nodes) != 3:
        return "Story package must contain exactly 3 ending nodes"
    path_depths: list[int] = []
    stack: list[tuple[str, int]] = [(root_node_id, 1)]
    visited_depth: set[tuple[str, int]] = set()
    while stack:
        node_id, depth = stack.pop()
        if (node_id, depth) in visited_depth:
            continue
        visited_depth.add((node_id, depth))
        node = node_map.get(node_id)
        if not node:
            continue
        if node.get("kind") == "ending":
            path_depths.append(depth)
            continue
        for choice in node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            next_node = node_map.get(next_node_id)
            if not next_node_id or not next_node:
                continue
            next_depth = depth if next_node.get("kind") == "ending" else depth + 1
            stack.append((next_node_id, next_depth))
    if not path_depths:
        return "No ending path depth found from rootNodeId"
    if min(path_depths) < 2 or max(path_depths) > 4:
        return "Each playable path must reach an ending after 2 to 4 turn nodes"
    for node in playable_nodes:
        choices = node.get("choices", [])
        if len(choices) != 3:
            return f"Turn node {node.get('id', 'unknown')} must contain exactly 3 choices"
        for choice in choices:
            if not _clean_model_text(choice.get("text", "")):
                return f"Choice text is missing in node {node.get('id', 'unknown')}"
            if _clean_model_text(choice.get("nextNodeId", "")) not in node_map:
                return f"Choice nextNodeId is invalid in node {node.get('id', 'unknown')}"

    visited = set()
    stack = [root_node_id]
    reached_ending = False
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = node_map.get(node_id)
        if not node:
            return f"Node {node_id} is missing from node map"
        if node.get("kind") == "ending":
            reached_ending = True
            continue
        for choice in node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            if next_node_id and next_node_id not in visited:
                stack.append(next_node_id)
    if not reached_ending:
        return "No reachable ending node found from rootNodeId"
    return None


def _initial_hydrate_node_ids(skeleton: dict[str, Any]) -> set[str]:
    """计算首屏默认要提前补全的节点集合。"""
    node_map = {node.get("id"): node for node in skeleton.get("nodes", [])}
    root_node_id = skeleton.get("rootNodeId")
    hydrate_ids: set[str] = set()
    if root_node_id and root_node_id in node_map:
        hydrate_ids.add(root_node_id)
        root_node = node_map[root_node_id]
        for choice in root_node.get("choices", []):
            next_node_id = choice.get("nextNodeId")
            if next_node_id in node_map:
                hydrate_ids.add(next_node_id)
    return hydrate_ids


def _choice_blueprint(
    choice_id: str,
    strategy: str,
    prompt_label: str,
    fallback_text: str,
    next_node_id: str,
    style: Optional[str] = None,
    tone: Optional[str] = None,
) -> dict[str, Any]:
    """创建模板骨架里一条 choice blueprint。"""
    resolved_style = style or strategy
    return {
        "id": choice_id,
        "strategy": strategy,
        "promptLabel": prompt_label,
        "fallbackText": fallback_text,
        "nextNodeId": next_node_id,
        "style": resolved_style,
        "tone": tone or _choice_tone(fallback_text, resolved_style),
        "effects": _choice_effects(resolved_style),
    }


def _build_template_story_package_skeleton(opening: str, role: str) -> dict[str, Any]:
    """生成后端内置的高戏剧互动故事骨架模板。"""
    title = get_opening_title(opening) or "未命名互动宇宙"
    opening_summary = get_opening_summary(opening) or opening.split("\n")[0].strip() or opening
    nodes = [
        {
            "id": "N1",
            "kind": "turn",
            "turn": 1,
            "stageLabel": "第一幕·直接出事",
            "directorNote": "异常已经摆到台面上了，你得马上接球、试探，或者直接掀桌。",
            "summary": "故事一开场就出现明显异常，主角必须立刻用自己的态度回应局势。",
            "beat": "开场异常",
            "pathSummary": f"开头已经给出核心异常：{opening_summary}",
            "choiceBlueprints": [
                _choice_blueprint("N1-C1", "soft", "软接情绪", "我放轻声音：「你先别躲，我想知道这件事里，你最怕我看见的到底是什么。」", "N2-soft", style="soft", tone="温柔"),
                _choice_blueprint("N1-C2", "tease", "带笑试探", "我偏头笑了一下：「你把气氛搞得这么暧昧，我要是再装傻，是不是就太不给面子了？」", "N2-tease", style="tease", tone="撩拨"),
                _choice_blueprint("N1-C3", "confrontation", "直接掀桌", "我抬眼盯住他：「既然都把我逼到这一步了，那你就别想再含糊过去。」", "N2-hard", style="confrontation", tone="强势"),
            ],
        },
        {
            "id": "N2-soft",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·柔软反扑",
            "directorNote": "你先接住了局面，对方的软肋浮出来了。第二次选择会决定这场关系是落向真心、暧昧，还是清醒抽身。",
            "summary": "温柔路线让对方开始松动，真正的情绪爆点已经来到眼前。",
            "beat": "中段推进",
            "pathSummary": "你在第一步选择先接住情绪，于是局势从对撞转向带伤的靠近。",
            "choiceBlueprints": [
                _choice_blueprint("N2-soft-C1", "trust", "认真接住", "我伸手握住他：「那这次换我认真一点，不让你一个人撑着。」", "E-sweet", style="trust", tone="真诚"),
                _choice_blueprint("N2-soft-C2", "tease", "留一点余温", "我弯起眼睛：「你都说到这一步了，再嘴硬就太可惜了吧？」", "E-slowburn", style="tease", tone="暧昧"),
                _choice_blueprint("N2-soft-C3", "observation", "先把自己稳住", "我深吸一口气：「今天先到这里，我得先把自己理清楚。」", "E-open", style="observation", tone="克制"),
            ],
        },
        {
            "id": "N2-tease",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·暧昧升温",
            "directorNote": "你把场面拧得更暧昧了，对方已经快被你撩到失控。第二次选择会决定这是甜蜜兑现、慢热拉扯，还是临门收手。",
            "summary": "撩拨路线让张力拉满，关系已经走到要落地的前一秒。",
            "beat": "中段推进",
            "pathSummary": "你在第一步选择带笑试探，把场面推成了一场带火花的拉扯。",
            "choiceBlueprints": [
                _choice_blueprint("N2-tease-C1", "trust", "把玩笑落地", "我忽然认真起来：「如果你愿意说实话，这次我不会再笑着糊弄过去。」", "E-sweet", style="trust", tone="真诚"),
                _choice_blueprint("N2-tease-C2", "tease", "继续续杯", "我抬手替他理了一下衣领：「你都快把心事写脸上了，还要我继续猜吗？」", "E-slowburn", style="tease", tone="撩拨"),
                _choice_blueprint("N2-tease-C3", "observation", "停在门口", "我把笑意收了一点：「今天就先到这里，剩下的话改天再说。」", "E-open", style="observation", tone="克制"),
            ],
        },
        {
            "id": "N2-hard",
            "kind": "turn",
            "turn": 2,
            "stageLabel": "第二幕·正面冲撞",
            "directorNote": "你把话挑明了，对方也被逼到边缘。第二次选择会决定你是强硬拿下、半退半撩，还是先抽身止损。",
            "summary": "强势路线把局势直接推到悬崖边，情绪和真相一起翻上来。",
            "beat": "中段推进",
            "pathSummary": "你在第一步直接掀桌，把关系推进到了最容易出真相也最容易失控的位置。",
            "choiceBlueprints": [
                _choice_blueprint("N2-hard-C1", "confrontation", "强硬拿下", "我还是不退：「你可以生气，但你得把理由一字一句说清楚。」", "E-sweet", style="confrontation", tone="强势"),
                _choice_blueprint("N2-hard-C2", "tease", "边退边撩", "我忽然放缓一点：「如果我真的伤到你，那你至少要让我知道我错在哪。」", "E-slowburn", style="tease", tone="松动"),
                _choice_blueprint("N2-hard-C3", "observation", "先行止损", "我盯着他看了几秒，最后还是后退半步：「今天先到这里，等我们都冷静了再说。」", "E-open", style="observation", tone="冷静"),
            ],
        },
        {
            "id": "E-sweet",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局·糖分超标",
            "directorNote": "高好感路线达成。",
            "summary": "你选择直球接住感情，这个宇宙以高好感的双向奔赴收束。",
            "beat": "高糖收束",
            "pathSummary": "你选择把真心直接落地，故事朝着高好感兑现收束。",
            "endingType": "good",
            "choices": [],
        },
        {
            "id": "E-slowburn",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局·暧昧续杯",
            "directorNote": "慢热但极有后劲的结局。",
            "summary": "你没有一口气跳进结局，而是选择把关系留在最有余温的慢热区。",
            "beat": "留白收束",
            "pathSummary": "你没有强行圆满，而是把气氛停在最有后劲的位置。",
            "endingType": "bittersweet",
            "choices": [],
        },
        {
            "id": "E-open",
            "kind": "ending",
            "turn": 3,
            "stageLabel": "结局·先把自己找回来",
            "directorNote": "克制路线达成开放式结局。",
            "summary": "你把关系按在开放式收束上，没有强行圆满，却保住了自己的节奏。",
            "beat": "开放收束",
            "pathSummary": "你选择先把自己找回来，让这段关系停在足够诚实的位置。",
            "endingType": "open",
            "choices": [],
        },
    ]

    for node in nodes:
        if node.get("kind") != "turn":
            continue
        blueprints = node.get("choiceBlueprints", [])
        node["choices"] = [
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

    return {
        "version": PACKAGE_VERSION,
        "title": title,
        "opening": opening,
        "role": role,
        "rootNodeId": "N1",
        "nodes": nodes,
        "initialState": {
            "stage": "opening",
            "flags": [],
            "relationship": {"好感": 0, "信任": 0, "警惕": 0},
            "persona": {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0},
            "turn": 1,
            "endingHint": "",
        },
    }


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
    hydrate_node_ids: Optional[Set[str]] = None,
    choice_provider: str = "secondme",
    prose_provider: str = "volcengine",
) -> dict[str, Any]:
    """按“固定骨架，再补选项和正文”的两阶段方式生成故事包。"""
    skeleton = _build_template_story_package_skeleton(opening=opening, role=role)
    skeleton_nodes = skeleton.get("nodes", [])
    if hydrate_node_ids is None:
        hydrate_node_ids = {node.get("id") for node in skeleton_nodes if node.get("id")}
    elif not hydrate_node_ids:
        hydrate_node_ids = _initial_hydrate_node_ids(skeleton)
    choice_phase_nodes = [node.get("id") for node in skeleton_nodes if node.get("kind") == "turn" and node.get("id") in hydrate_node_ids]
    prose_phase_nodes = [node.get("id") for node in skeleton_nodes if node.get("id") in hydrate_node_ids]
    prepared_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        if node.get("kind") != "turn" or node.get("id") not in hydrate_node_ids:
            prepared_nodes.append(node)
            continue
        prepared_nodes.append(
            {
                **node,
                "choices": await _generate_story_node_choices(
                    access_token=access_token,
                    opening=opening,
                    role=role,
                    title=skeleton.get("title", ""),
                    skeleton_nodes=skeleton_nodes,
                    node=node,
                    provider=choice_provider,
                    phase_nodes=choice_phase_nodes,
                ),
            }
        )
    skeleton["nodes"] = prepared_nodes
    skeleton_nodes = prepared_nodes
    completed_nodes: list[dict[str, Any]] = []
    for node in skeleton_nodes:
        if node.get("id") in hydrate_node_ids:
            content = await _generate_story_node_content(
                access_token=access_token,
                opening=opening,
                role=role,
                title=skeleton.get("title", ""),
                skeleton_nodes=skeleton_nodes,
                node=node,
                provider=prose_provider,
                phase_nodes=prose_phase_nodes,
            )
            completed_nodes.append(
                {
                    **node,
                    "stageLabel": content.get("stageLabel") or node.get("stageLabel", "剧情推进"),
                    "directorNote": content.get("directorNote") or node.get("directorNote", ""),
                    "scene": content["scene"],
                    "paragraphs": content["paragraphs"],
                    "summary": content.get("summary") or node.get("summary", ""),
                    "loaded": True,
                }
            )
        else:
            completed_nodes.append(
                {
                    **node,
                    "scene": "",
                    "paragraphs": [],
                    "loaded": False,
                }
            )
    package = {
        **skeleton,
        "nodes": completed_nodes,
        "hydratedNodeIds": sorted(hydrate_node_ids),
    }
    validation_error = _story_package_validation_error(package)
    if validation_error:
        raise HTTPException(status_code=400, detail={"message": validation_error})
    return _finalize_story_package(package, persona_profile)

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
    relationship = dict(previous_state.get("relationship", {"hero": 0, "villain": 0}))
    persona = dict(previous_state.get("persona", {"真诚": 0, "嘴硬": 0, "心机": 0, "胆量": 0}))
    action_style = _choice_style(action)
    effects = _choice_effects(action_style)

    for key, value in effects.get("persona", {}).items():
        persona[key] = persona.get(key, 0) + value

    if action_style in {"trust", "support"}:
        relationship["hero"] = relationship.get("hero", 0) + 1
        if "trust_path" not in flags:
            flags.append("trust_path")
    if action_style in {"soft", "tease"}:
        relationship["hero"] = relationship.get("hero", 0) + 1
    if action_style in {"confrontation", "risk"}:
        relationship["hero"] = relationship.get("hero", 0) - 1
        relationship["villain"] = relationship.get("villain", 0) - 1
        if "conflict_spike" not in flags:
            flags.append("conflict_spike")
    if action_style in {"strategy", "manipulation", "observation"}:
        if "foreshadowing_seed" not in flags:
            flags.append("foreshadowing_seed")
    if action_style == "manipulation" and "hidden_motive" not in flags:
        flags.append("hidden_motive")
    if any("相信" in choice or "利用" in choice or "揭穿" in choice for choice in choice_texts) and "reversal_ready" not in flags and turn_count >= 3:
        flags.append("reversal_ready")

    stage = _infer_stage(turn_count, status)
    ending_hint = ""
    if stage == "ending" and "trust_path" in flags and "reversal_ready" in flags:
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
    opening = _clean_model_text(body.get("opening", ""))
    role = _clean_model_text(body.get("role", ""))
    if not opening or not role:
        raise HTTPException(status_code=400, detail="Missing opening or role")
    if opening in PRESET_OPENINGS:
        opening_id = f"library-{PRESET_OPENINGS.index(opening) + 1}"
        session_record, reused, _ = await _start_or_resume_library_story(
            server_session,
            opening=opening,
            role=role,
            opening_id=opening_id,
            seed_ready_from_client=False,
            force_regenerate=bool(body.get("forceRegenerate")),
        )
        return session_record, reused
    return await _start_or_generate_custom_story(server_session, opening=opening, role=role, force_regenerate=bool(body.get("forceRegenerate")))


def _build_library_story_rows(sessions: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """构造书城推荐故事列表及其 seed 状态。"""
    seed_map: dict[str, dict[str, Any]] = {}
    if sessions is not None:
        for item in sessions:
            if item.get("kind") != "library_seed_package":
                continue
            if item.get("userId") != LIBRARY_SEED_USER_ID:
                continue
            opening_id = _clean_model_text(item.get("meta", {}).get("openingId", ""))
            if not opening_id:
                continue
            seed_map[opening_id] = item
    else:
        seed_map = _load_library_seed_index()
    rows = []
    for source in _load_library_story_sources():
        opening_id = source["id"]
        seed = seed_map.get(opening_id)
        seed_status = seed.get("packageStatus") if seed else ""
        rows.append(
            {
                "id": opening_id,
                "opening": source["opening"],
                "title": source["title"],
                "summary": source["summary"],
                "seedReady": bool(seed) and seed_status == "ready",
                "seedGenerating": bool(seed) and seed_status == "generating",
                "seedUpdatedAt": seed.get("updatedAt") if seed else None,
                "seedSessionId": seed.get("id") if seed else "",
            }
        )
    return rows


def _resolve_library_opening(story_id: str) -> str:
    """把书城 story id 解析成对应的 opening 文案。"""
    for row in _build_library_story_rows():
        if row["id"] == story_id:
            return row["opening"]
    raise HTTPException(status_code=404, detail="Library story not found")


def _find_library_seed_session(sessions: Optional[list[dict[str, Any]]], story_id: str) -> Optional[dict[str, Any]]:
    """在会话列表里查找某个书城故事的全局 seed session。"""
    if _use_database_storage():
        return _find_library_seed_session_by_opening_id_from_db(story_id)
    if sessions is None:
        sessions = _load_sessions()
    for item in sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != LIBRARY_SEED_USER_ID:
            continue
        if _clean_model_text(item.get("meta", {}).get("openingId", "")) != story_id:
            continue
        package = item.get("package", {})
        if package.get("version") != PACKAGE_VERSION:
            continue
        return item
    return None


def _find_library_seed_generation_session(sessions: list[dict[str, Any]], story_id: str) -> Optional[dict[str, Any]]:
    """查找某个书城故事是否已有进行中的 seed 生成占位。"""
    for item in sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != LIBRARY_SEED_USER_ID:
            continue
        if _clean_model_text(item.get("meta", {}).get("openingId", "")) != story_id:
            continue
        if item.get("packageStatus") != "generating":
            continue
        return item
    return None


def _require_library_seed_session(sessions: Optional[list[dict[str, Any]]], opening_id: str) -> dict[str, Any]:
    """读取指定书城故事的全局 seed；如果不存在则直接报错。"""
    seed = _find_library_seed_session(sessions, opening_id)
    if not seed:
        _debug_story_log(
            "[library-seed-missing]",
            {
                "openingId": opening_id,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "该故事的公共内容还没播种完成，请先生成 seed。",
                "openingId": opening_id,
            },
        )
    _debug_story_log(
        "[library-seed-hit]",
        {
            "openingId": opening_id,
            "seedSessionId": seed.get("id"),
            "generatedNow": False,
        },
    )
    return seed


def _upsert_session_by_id(sessions: list[dict[str, Any]], record: dict[str, Any]) -> None:
    """按 id 更新或插入一条会话记录。"""
    record_id = record.get("id")
    for index, item in enumerate(sessions):
        if item.get("id") == record_id:
            sessions[index] = record
            return
    sessions.insert(0, record)


def _remove_session_by_id(sessions: list[dict[str, Any]], record_id: str) -> None:
    """按 id 删除一条会话记录。"""
    for index, item in enumerate(sessions):
        if item.get("id") == record_id:
            sessions.pop(index)
            return


def _mark_library_seed_generation_pending(
    sessions: list[dict[str, Any]],
    opening: str,
    opening_id: str,
    persona_profile: dict[str, Any],
) -> dict[str, Any]:
    """把某个书城 seed 标记为生成中，方便并发请求感知。"""
    existing = _find_library_seed_generation_session(sessions, opening_id)
    existing_ready = _find_library_seed_session(sessions, opening_id)
    now = int(time.time())
    pending_record = {
        "id": f"seed-{opening_id}",
        "kind": "library_seed_package",
        "createdAt": existing_ready.get("createdAt") if existing_ready else existing.get("createdAt") if existing else now,
        "updatedAt": now,
        "userId": LIBRARY_SEED_USER_ID,
        "status": "generating",
        "packageStatus": "generating",
        "sourceType": "library",
        "meta": {
            "openingId": opening_id,
            "opening": opening,
            "role": "主人公",
            "author": "Potato Library Seed",
            "sourceType": "library",
        },
        "personaProfile": persona_profile,
        "package": existing_ready.get("package", {}) if existing_ready else {},
        "runtime": None,
        "completedRun": None,
    }
    _upsert_session_by_id(sessions, pending_record)
    _save_sessions(sessions)
    return pending_record


def _library_seed_lock_path(opening_id: str) -> Path:
    """返回某个书城 seed 对应的文件锁路径。"""
    return LIBRARY_SEED_LOCK_DIR / f"{opening_id}.lock"


def _try_acquire_library_seed_generation_lock(opening_id: str) -> bool:
    """尝试获取某个书城 seed 的生成锁。"""
    if _use_database_storage():
        with _db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"library-seed:{opening_id}",))
            row = cur.fetchone()
        return bool(row and row[0])
    LIBRARY_SEED_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _library_seed_lock_path(opening_id)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return False
        raise


def _release_library_seed_generation_lock(opening_id: str) -> None:
    """释放某个书城 seed 的生成锁。"""
    if _use_database_storage():
        with _db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"library-seed:{opening_id}",))
        return
    lock_path = _library_seed_lock_path(opening_id)
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


async def _wait_for_library_seed_package(opening_id: str, timeout_seconds: float = LIBRARY_SEED_WAIT_TIMEOUT_SECONDS) -> Optional[dict[str, Any]]:
    """等待其他并发请求完成某个书城 seed 的首次播种。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        sessions = _load_sessions()
        existing = _find_library_seed_session(sessions, opening_id)
        if existing:
            return existing
        await asyncio.sleep(LIBRARY_SEED_WAIT_INTERVAL_SECONDS)
    return None

#
# 书城故事按 opening id 维护全局 seed。
# 首次访问时生成并落库，后续访问直接复用已有 seed。
async def _load_or_generate_library_seed_package(
    sessions: list[dict[str, Any]],
    opening: str,
    opening_id: str,
    seed_ready_from_client: bool,
    force_regenerate: bool = False,
    skip_existing_check: bool = False,
) -> tuple[dict[str, Any], bool]:
    """读取或首次生成某个书城开头对应的全局 seed package。"""
    existing_seed = None if skip_existing_check else _find_library_seed_session(sessions, opening_id)
    if existing_seed and not force_regenerate:
        _debug_story_log(
            "[library-seed-hit]",
            {
                "openingId": opening_id,
                "seedSessionId": existing_seed.get("id"),
                "seedReadyFromClient": seed_ready_from_client,
                "forceRegenerate": force_regenerate,
                "generatedNow": False,
            },
        )
        return existing_seed.get("package", {}), False
    if seed_ready_from_client and not force_regenerate and not existing_seed:
        _debug_story_log(
            "[library-seed-stale]",
            {
                "openingId": opening_id,
                "seedReadyFromClient": seed_ready_from_client,
                "forceRegenerate": force_regenerate,
            },
        )
        raise HTTPException(status_code=409, detail="Seed status changed, please refresh bookshelf and retry")

    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Doubao(Volcengine) is required for first-time library story generation")

    persona_profile = {
        "key": "library_seed",
        "label": "图书馆播种者模板",
        "preferredStyles": ["trust", "tease", "confrontation"],
        "description": "用于模板故事全局首次生成。",
        "source": "library-seed-generation",
    }
    _debug_story_log(
        "[library-seed-miss]",
        {
            "openingId": opening_id,
            "seedReadyFromClient": seed_ready_from_client,
            "forceRegenerate": force_regenerate,
            "generating": True,
        },
    )
    lock_acquired = _try_acquire_library_seed_generation_lock(opening_id)
    if not lock_acquired:
        _debug_story_log(
            "[library-seed-waiting]",
            {
                "openingId": opening_id,
            },
        )
        waited_seed = await _wait_for_library_seed_package(opening_id)
        if waited_seed:
            _debug_story_log(
                "[library-seed-wait-hit]",
                {
                    "openingId": opening_id,
                    "seedSessionId": waited_seed.get("id"),
                    "generatedNow": False,
                },
            )
            return waited_seed.get("package", {}), False
        raise HTTPException(
            status_code=409,
            detail={
                "message": "该故事的公共内容正在播种中，请稍后重试。",
                "openingId": opening_id,
            },
        )

    try:
        _debug_story_log(
            "[library-seed-lock-acquired]",
            {
                "openingId": opening_id,
            },
        )
        sessions = _load_sessions()
        existing_seed = _find_library_seed_session(sessions, opening_id)
        if existing_seed and not force_regenerate:
            _debug_story_log(
                "[library-seed-hit]",
                {
                    "openingId": opening_id,
                    "seedSessionId": existing_seed.get("id"),
                    "seedReadyFromClient": seed_ready_from_client,
                    "forceRegenerate": force_regenerate,
                    "generatedNow": False,
                    "resolvedAfterLock": True,
                },
            )
            return existing_seed.get("package", {}), False
        previous_seed_record = deepcopy(existing_seed) if existing_seed else None
        _mark_library_seed_generation_pending(sessions, opening, opening_id, persona_profile)
        _debug_story_log(
            "[library-seed-pending-saved]",
            {
                "openingId": opening_id,
                "seedSessionId": f"seed-{opening_id}",
            },
        )
        try:
            _debug_story_log(
                "[library-seed-build-start]",
                {
                    "openingId": opening_id,
                    "choiceNodeCount": 4,
                    "contentNodeCount": 7,
                },
            )
            story_package = await _build_story_package_two_stage(
                access_token=None,
                opening=opening,
                role="主人公",
                user_name="土豆图书馆",
                persona_profile=persona_profile,
                hydrate_node_ids=None,
                choice_provider="volcengine",
                prose_provider="volcengine",
            )
        except HTTPException as exc:
            sessions = _load_sessions()
            if previous_seed_record:
                _upsert_session_by_id(sessions, previous_seed_record)
            else:
                _remove_session_by_id(sessions, f"seed-{opening_id}")
            _save_sessions(sessions)
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            reason = detail.get("error") or detail.get("reason") or detail.get("message") or "unknown"
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "首访故事播种失败，请重试。",
                    "reason": reason,
                },
            ) from exc
        sessions = _load_sessions()
        existing_generating = _find_library_seed_generation_session(sessions, opening_id)
        now = int(time.time())
        seed_record = {
            "id": f"seed-{opening_id}",
            "kind": "library_seed_package",
            "createdAt": existing_generating.get("createdAt") if existing_generating else now,
            "updatedAt": now,
            "userId": LIBRARY_SEED_USER_ID,
            "status": "ready",
            "packageStatus": "ready",
            "sourceType": "library",
            "meta": {
                "openingId": opening_id,
                "opening": opening,
                "role": "主人公",
                "author": "Potato Library Seed",
                "sourceType": "library",
            },
            "personaProfile": persona_profile,
            "package": story_package,
            "runtime": None,
            "completedRun": None,
        }
        _upsert_session_by_id(sessions, seed_record)
        _save_sessions(sessions)
        _debug_story_log(
            "[library-seed-generated]",
            {
                "openingId": opening_id,
                "seedSessionId": seed_record["id"],
                "generatedNow": True,
            },
        )
        return story_package, True
    finally:
        _release_library_seed_generation_lock(opening_id)


async def _generate_library_seed_package(
    opening: str,
    opening_id: str,
    force_regenerate: bool = False,
    skip_existing_check: bool = False,
) -> tuple[dict[str, Any], bool]:
    """显式播种某本书城故事的全局 seed。"""
    sessions = _load_sessions()
    if not force_regenerate and not skip_existing_check:
        existing = _find_library_seed_session(sessions, opening_id)
        if existing:
            _debug_story_log(
                "[library-seed-hit]",
                {
                    "openingId": opening_id,
                    "seedSessionId": existing.get("id"),
                    "generatedNow": False,
                },
            )
            return existing.get("package", {}), False
    return await _load_or_generate_library_seed_package(
        sessions=sessions,
        opening=opening,
        opening_id=opening_id,
        seed_ready_from_client=False,
        force_regenerate=force_regenerate,
        skip_existing_check=skip_existing_check,
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
            "author": user.get("name") or "SecondMe 用户",
            "sourceType": source_type,
        },
        "personaProfile": persona_profile,
        "package": package_payload,
        "runtime": _initial_runtime_from_package(package_payload),
        "completedRun": None,
    }
    if opening_id:
        session_record["meta"]["openingId"] = opening_id
    return session_record


async def _start_or_resume_library_story(
    server_session: dict[str, Any],
    opening: str,
    role: str,
    opening_id: str,
    seed_ready_from_client: bool,
    force_regenerate: bool = False,
) -> tuple[dict[str, Any], bool, bool]:
    """为书城故事创建用户会话；点击书城始终新开一局，只复用全局 seed。"""
    user = server_session["user"]
    sessions = _load_sessions()

    story_package, generated_now = await _load_or_generate_library_seed_package(
        sessions=sessions,
        opening=opening,
        opening_id=opening_id,
        seed_ready_from_client=seed_ready_from_client,
        force_regenerate=force_regenerate,
    )
    package_payload = deepcopy(story_package)
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
        "sourceType": "library",
        "meta": {
            "openingId": opening_id,
            "opening": opening,
            "role": role,
            "author": user.get("name") or "SecondMe 用户",
            "sourceType": "library",
        },
        "personaProfile": persona_profile,
        "package": package_payload,
        "runtime": _initial_runtime_from_package(package_payload),
        "completedRun": None,
    }
    sessions.insert(0, session_record)
    _save_sessions(sessions)
    return session_record, False, generated_now


async def _start_or_generate_custom_story(
    server_session: dict[str, Any],
    opening: str,
    role: str,
    force_regenerate: bool = False,
) -> tuple[dict[str, Any], bool]:
    """为自定义开头生成一个前端本地游玩的故事 payload。"""
    if not _has_volcengine_prose_provider():
        raise HTTPException(status_code=500, detail="Doubao(Volcengine) is not configured for custom story generation")

    user = server_session["user"]
    persona_profile = _derive_persona_profile(user)
    story_package = await _build_story_package_two_stage(
        access_token=server_session["token"].get("access_token"),
        opening=opening,
        role=role,
        user_name=user.get("name") or "SecondMe 用户",
        persona_profile=persona_profile,
        hydrate_node_ids=None,
        choice_provider="volcengine",
        prose_provider="volcengine",
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


@app.get("/api/health")
async def health() -> dict[str, str]:
    """健康检查接口。"""
    return {"status": "ok"}


@app.get("/api/debug-config")
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


@app.get("/integration/manifest.json")
async def integration_manifest(request: Request) -> JSONResponse:
    """返回 SecondMe 集成 manifest。"""
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    manifest = build_integration_manifest(base_url=base_url, app_id=settings.secondme_app_id)
    return JSONResponse(manifest)


@app.get("/api/auth/login")
async def auth_login() -> RedirectResponse:
    """发起 OAuth 登录跳转并写入防 CSRF 的 state。"""
    _require_env()
    state = random_urlsafe(24)
    params = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": settings.scope,
        "state": state,
    }
    response = RedirectResponse(url=f"{settings.auth_url}?{urlencode(params)}", status_code=302)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600, path=COOKIE_PATH)
    return response


@app.post("/api/auth/exchange")
async def auth_exchange(request: Request) -> JSONResponse:
    """用 OAuth code 换 token，并建立后端签名 session。"""
    _require_env()
    body = await request.json()
    code = body.get("code")
    state = body.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    expected_state = request.cookies.get("oauth_state")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "code": code,
        "redirect_uri": settings.redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            token_response = await client.post(settings.token_url, data=token_payload)
            if token_response.status_code >= 400:
                raise HTTPException(status_code=400, detail={"message": "Token exchange failed", "body": token_response.text})
            token_result = token_response.json()
            token_data = token_result.get("data", token_result)
            access_token = token_data.get("accessToken") or token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail={"message": "Token response missing access token", "body": token_result})

            userinfo_response = await client.get(
                settings.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code >= 400:
                raise HTTPException(status_code=400, detail={"message": "Failed to fetch user info", "body": userinfo_response.text})
            userinfo_result = userinfo_response.json()
            userinfo = userinfo_result.get("data", userinfo_result)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to reach SecondMe OAuth API", "error": str(exc)},
        ) from exc

    # 控制 cookie 体积，避免浏览器因为过长而存不下 session。
    session_user = {
        "userId": userinfo.get("userId"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "avatar": userinfo.get("avatar"),
        "route": userinfo.get("route"),
    }
    session_payload = {
        "iat": int(time.time()),
        "user": session_user,
        "token": {
            "access_token": access_token,
            "refresh_token": token_data.get("refreshToken") or token_data.get("refresh_token"),
            "expires_in": token_data.get("expiresIn") or token_data.get("expires_in"),
            "scope": token_data.get("scope", settings.scope),
        },
    }
    session_token = sign_payload(session_payload, settings.session_secret)

    response = JSONResponse({"ok": True, "user": session_user})
    response.set_cookie("session", session_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7, path=COOKIE_PATH)
    response.delete_cookie("oauth_state", path=COOKIE_PATH)
    return response


@app.get("/api/me")
async def current_user(request: Request) -> JSONResponse:
    """返回当前是否已登录以及用户信息。"""
    _require_env()
    try:
        server_session = _get_server_session(request)
    except HTTPException:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": server_session.get("user", {})})


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> Response:
    """清理登录相关 cookie。"""
    response = JSONResponse({"ok": True})
    response.delete_cookie("session", path=COOKIE_PATH)
    response.delete_cookie("oauth_state", path=COOKIE_PATH)
    return response


@app.post("/api/story/start")
async def start_story(request: Request) -> JSONResponse:
    """统一的故事开始入口，返回可读的 story session。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_record, reused = await _create_or_reuse_story_package(body, server_session)
    if session_record.get("kind") == "story_package":
        _ensure_story_package_runtime(session_record)

    return JSONResponse(
        {
            "ok": True,
            "session": _serialize_session(session_record),
            "reused": reused,
        }
    )


@app.get("/api/library-stories")
async def list_library_stories(request: Request) -> JSONResponse:
    """列出书城内置故事及其播种状态。"""
    _require_env()
    _get_server_session(request)
    return JSONResponse({"ok": True, "stories": _build_library_story_rows()})


@app.post("/api/library-stories/{story_id}/generate-seed")
async def generate_library_story_seed(story_id: str, request: Request) -> JSONResponse:
    """显式为某本书城故事播种全局 seed。"""
    _require_env()
    _get_server_session(request)
    body = await request.json()
    opening = _resolve_library_opening(story_id)
    _, generated_now = await _generate_library_seed_package(
        opening=opening,
        opening_id=story_id,
        force_regenerate=bool(body.get("forceRegenerate")),
        skip_existing_check=not bool(body.get("forceRegenerate")),
    )
    seed = _require_library_seed_session(None, story_id)
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


@app.post("/api/library-stories/{story_id}/start-from-seed")
async def start_library_story_from_seed(story_id: str, request: Request) -> JSONResponse:
    """基于已存在的全局 seed 为当前用户新开一局书城故事。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    role = _clean_model_text(body.get("role", "")) or "主人公"
    opening = _resolve_library_opening(story_id)
    seed = _require_library_seed_session(None, story_id)
    session_record = _build_story_package_session_payload(
        server_session,
        opening=opening,
        role=role,
        source_type="library",
        opening_id=story_id,
        story_package=seed.get("package", {}),
    )
    _ensure_story_package_runtime(session_record)
    return JSONResponse({"ok": True, "session": _serialize_session(session_record), "reused": False})


@app.post("/api/library-stories/{story_id}/start")
async def start_library_story(story_id: str, request: Request) -> JSONResponse:
    """兼容旧入口：没有 seed 时先播种，再基于 seed 新开一局。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    role = _clean_model_text(body.get("role", "")) or "主人公"
    opening = _resolve_library_opening(story_id)
    _, generated_now = await _generate_library_seed_package(
        opening=opening,
        opening_id=story_id,
        force_regenerate=bool(body.get("forceRegenerate")),
    )
    sessions = _load_sessions()
    seed = _require_library_seed_session(sessions, story_id)
    session_record = _build_story_package_session_payload(
        server_session,
        opening=opening,
        role=role,
        source_type="library",
        opening_id=story_id,
        story_package=seed.get("package", {}),
    )
    _ensure_story_package_runtime(session_record)
    return JSONResponse(
        {
            "ok": True,
            "session": _serialize_session(session_record),
            "reused": False,
            "pioneer": generated_now,
            "pioneerMessage": "你是这颗土豆宇宙的播种者，正在为后续读者生成完整章节，请稍等片刻。" if generated_now else "",
        }
    )


@app.post("/api/custom-stories/generate")
async def generate_custom_story(request: Request) -> JSONResponse:
    """根据自定义 opening 生成一条新的故事会话。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    opening = _clean_model_text(body.get("opening", ""))
    role = _clean_model_text(body.get("role", "")) or "主人公"
    if not opening:
        raise HTTPException(status_code=400, detail="Missing opening")
    session_record, reused = await _start_or_generate_custom_story(
        server_session,
        opening=opening,
        role=role,
        force_regenerate=bool(body.get("forceRegenerate")),
    )
    _ensure_story_package_runtime(session_record)
    return JSONResponse({"ok": True, "session": _serialize_session(session_record), "reused": reused})


@app.post("/api/story/preload")
async def preload_story_package(request: Request) -> JSONResponse:
    """兼容预加载入口，实际复用 start_story。"""
    return await start_story(request)


@app.post("/api/story/regenerate")
async def regenerate_story_package(request: Request) -> JSONResponse:
    """强制重新生成一个新的故事包。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    session_record, _ = await _create_or_reuse_story_package({**body, "forceRegenerate": True}, server_session)
    return JSONResponse({"ok": True, "session": _serialize_session(session_record), "reused": False})


@app.post("/api/story/analyze-ending")
async def analyze_story_ending(request: Request) -> JSONResponse:
    """根据完成后的故事轨迹生成结局签语分析。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()

    session_id = body.get("sessionId", "").strip()
    story = body.get("story", "")
    meta = body.get("meta", {}) or {}

    if session_id:
        _, story_session, _ = _find_session(session_id, server_session["user"].get("userId"))
        if story_session.get("kind") == "story_package":
            completed_run = story_session.get("completedRun")
            if not completed_run:
                raise HTTPException(status_code=400, detail="Story package is not finished yet")
            opening = story_session.get("meta", {}).get("opening", "")
            summary = completed_run.get("summary", "")
            transcript = completed_run.get("transcript", [])
            state = completed_run.get("state", {})
        else:
            opening = story_session.get("meta", {}).get("opening", "")
            summary = story_session.get("summary", "")
            transcript = story_session.get("transcript", [])
            state = story_session.get("state", {})
    else:
        opening = meta.get("opening", "")
        summary = meta.get("summary", "") or story
        transcript = meta.get("transcript", []) or []
        state = meta.get("state", {}) or {}

    prompt = _compose_ending_analysis_prompt(
        opening=opening,
        summary=summary,
        transcript=transcript,
        state=state,
    )
    analysis = _normalize_ending_analysis(
        await _call_secondme_chat(server_session["token"]["access_token"], prompt)
    )
    return JSONResponse({"ok": True, "analysis": analysis})


@app.post("/api/story/generate")
async def generate_story(request: Request) -> JSONResponse:
    """兼容旧路由，转发到 start_story。"""
    return await start_story(request)


@app.post("/api/story/save")
async def save_story(request: Request) -> JSONResponse:
    """把编译后的完整故事保存到持久化存储。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    story = body.get("story", "").strip()
    meta = body.get("meta", {})
    if not story:
        raise HTTPException(status_code=400, detail="Missing story")

    stories = _load_stories()
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
    _save_stories(stories)
    return JSONResponse({"ok": True, "story": record})


@app.get("/api/stories")
async def list_stories(request: Request) -> JSONResponse:
    """列出当前用户保存过的故事。"""
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    stories = [item for item in _load_stories() if item.get("userId") == user_id]
    return JSONResponse({"ok": True, "stories": stories})


@app.get("/api/stories/{story_id}")
async def get_story(story_id: str, request: Request) -> JSONResponse:
    """读取当前用户的一条已保存故事。"""
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    for item in _load_stories():
        if item.get("id") == story_id and item.get("userId") == user_id:
            return JSONResponse({"ok": True, "story": item})
    raise HTTPException(status_code=404, detail="Story not found")


@app.delete("/api/stories/{story_id}")
async def delete_story(story_id: str, request: Request) -> JSONResponse:
    """删除当前用户保存的一条故事。"""
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    if not _delete_story_record(story_id, user_id):
        raise HTTPException(status_code=404, detail="Story not found")
    return JSONResponse({"ok": True, "storyId": story_id})


@app.post("/api/stories/{story_id}/ending-analysis")
async def cache_story_ending_analysis(story_id: str, request: Request) -> JSONResponse:
    """把结局签语分析缓存到已保存故事的元数据里。"""
    _require_env()
    server_session = _get_server_session(request)
    body = await request.json()
    analysis = body.get("analysis")
    if not isinstance(analysis, dict):
        raise HTTPException(status_code=400, detail="Missing ending analysis")

    stories = _load_stories()
    user_id = server_session["user"].get("userId")
    for index, item in enumerate(stories):
        if item.get("id") == story_id and item.get("userId") == user_id:
            meta = item.setdefault("meta", {})
            meta["endingAnalysis"] = analysis
            item["updatedAt"] = int(time.time())
            stories[index] = item
            _save_stories(stories)
            return JSONResponse({"ok": True, "story": item})
    raise HTTPException(status_code=404, detail="Story not found")


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """提供给 MCP 客户端调用的统一入口。"""
    body = await request.json()
    method = body.get("method")
    request_id = body.get("id")

    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "potato-novel-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        )

    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "list_openings",
                            "description": "列出当前推荐的小说开头。",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "generate_story",
                            "description": "根据开头和角色生成短篇小说。需要请求头带 Authorization: Bearer <SecondMe access token>。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "opening": {"type": "string"},
                                    "role": {"type": "string"},
                                    "extra_instruction": {"type": "string"},
                                },
                                "required": ["opening", "role"],
                            },
                        },
                        {
                            "name": "list_saved_stories",
                            "description": "列出当前服务端已保存的小说记录摘要。",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            }
        )

    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "list_openings":
            openings = [
                {
                    "title": get_opening_title(opening),
                    "summary": get_opening_summary(opening),
                    "opening": opening,
                }
                for opening in PRESET_OPENINGS
            ]
            return JSONResponse(_mcp_result(request_id, openings))

        if name == "list_saved_stories":
            stories = [
                {
                    "id": item["id"],
                    "createdAt": item["createdAt"],
                    "title": item["meta"].get("opening", "")[:40],
                    "role": item["meta"].get("role", ""),
                    "author": item["meta"].get("author", ""),
                }
                for item in _load_stories()[:20]
            ]
            return JSONResponse(_mcp_result(request_id, stories))

        if name == "generate_story":
            opening = (arguments.get("opening") or "").strip()
            role = (arguments.get("role") or "").strip()
            extra_instruction = (arguments.get("extra_instruction") or "").strip()
            auth_header = request.headers.get("Authorization", "")
            if not opening or not role:
                return JSONResponse(_mcp_error(request_id, -32602, "Missing opening or role"))
            if not auth_header.startswith("Bearer "):
                return JSONResponse(_mcp_error(request_id, -32001, "Missing Authorization bearer token"))
            access_token = auth_header.replace("Bearer ", "", 1).strip()
            prompt = _compose_story_prompt(opening=opening, role=role, user_name="SecondMe 用户", extra_instruction=extra_instruction)
            story = await _call_secondme_chat(access_token=access_token, prompt=prompt)
            return JSONResponse(_mcp_result(request_id, {"story": story, "opening": opening, "role": role}))

        return JSONResponse(_mcp_error(request_id, -32601, f"Unknown tool: {name}"))

    return JSONResponse(_mcp_error(request_id, -32601, f"Unknown method: {method}"))


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


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        """在生产构建存在时返回前端入口页。"""
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        """为前端 SPA 提供静态资源和回退路由。"""
        requested = FRONTEND_DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
