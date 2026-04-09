"""会话仓储模块，统一封装 story session 与 library seed 的存储读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional


def session_row_to_record(row: dict[str, Any], normalize_source_type: Callable[[Any], str]) -> dict[str, Any]:
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
        "sourceType": normalize_source_type(meta.get("sourceType")),
        "runtime": meta.get("runtime") if isinstance(meta.get("runtime"), dict) else None,
        "personaProfile": row.get("persona_profile_json") or {},
        "package": row.get("package_json") or {},
        "completedRun": row.get("completed_run_json"),
    }


def load_sessions_from_db(db_connection: Callable[[], Any], psycopg_module: Any, normalize_source_type: Callable[[Any], str]) -> list[dict[str, Any]]:
    """从数据库读取故事会话列表。"""
    with db_connection() as conn, conn.cursor(row_factory=psycopg_module.rows.dict_row) as cur:
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
        return [session_row_to_record(row, normalize_source_type) for row in cur.fetchall()]


def load_sessions(
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    sessions_path: Path,
    normalize_source_type: Callable[[Any], str],
) -> list[dict[str, Any]]:
    """按当前存储模式读取故事会话列表。"""
    if use_database_storage:
        return load_sessions_from_db(db_connection, psycopg_module, normalize_source_type)
    if not sessions_path.exists():
        return []
    return json.loads(sessions_path.read_text(encoding="utf-8"))


def load_library_seed_index_from_db(
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    library_seed_user_id: str,
    clean_model_text: Callable[[str], str],
    package_version: int,
) -> dict[str, dict[str, Any]]:
    """从数据库读取书城 seed package 的索引。"""
    with db_connection() as conn, conn.cursor(row_factory=psycopg_module.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, meta_json, package_json, updated_at, status, package_status
            FROM story_sessions
            WHERE kind = 'library_seed_package' AND user_id = %s
            ORDER BY updated_at DESC
            """,
            (library_seed_user_id,),
        )
        rows = cur.fetchall()
    seed_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = row.get("meta_json") or {}
        package = row.get("package_json") or {}
        opening_id = clean_model_text(meta.get("openingId", ""))
        if not opening_id or opening_id in seed_map:
            continue
        if int(package.get("version") or 0) != int(package_version):
            continue
        seed_map[opening_id] = {
            "id": row.get("id"),
            "updatedAt": row.get("updated_at"),
            "status": row.get("status") or "ready",
            "packageStatus": row.get("package_status") or "ready",
        }
    return seed_map


def load_library_seed_index(
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    library_seed_user_id: str,
    clean_model_text: Callable[[str], str],
    package_version: int,
    sessions_path: Path,
    normalize_source_type: Callable[[Any], str],
) -> dict[str, dict[str, Any]]:
    """按当前存储模式读取书城 seed 索引。"""
    if use_database_storage:
        return load_library_seed_index_from_db(
            db_connection,
            psycopg_module,
            library_seed_user_id,
            clean_model_text,
            package_version,
        )
    sessions = load_sessions(False, db_connection, psycopg_module, sessions_path, normalize_source_type)
    seed_map: dict[str, dict[str, Any]] = {}
    for item in sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != library_seed_user_id:
            continue
        opening_id = clean_model_text(item.get("meta", {}).get("openingId", ""))
        if not opening_id or opening_id in seed_map:
            continue
        package = item.get("package", {}) or {}
        if int(package.get("version") or 0) != int(package_version):
            continue
        seed_map[opening_id] = {
            "id": item.get("id"),
            "updatedAt": item.get("updatedAt"),
            "status": item.get("status", "ready"),
            "packageStatus": item.get("packageStatus", "ready"),
        }
    return seed_map


def find_library_seed_session_by_opening_id_from_db(
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    story_id: str,
    library_seed_user_id: str,
    package_version: int,
    normalize_source_type: Callable[[Any], str],
) -> Optional[dict[str, Any]]:
    """按 openingId 精确读取单条书城 seed。"""
    with db_connection() as conn, conn.cursor(row_factory=psycopg_module.rows.dict_row) as cur:
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
            (library_seed_user_id, story_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    record = session_row_to_record(row, normalize_source_type)
    package = record.get("package", {})
    if package.get("version") != package_version:
        return None
    return record


def save_session_record(
    record: dict[str, Any],
    db_connection: Callable[[], Any],
    normalize_source_type: Callable[[Any], str],
) -> None:
    """把单条故事会话记录写入数据库。"""
    meta_payload = {
        **record.get("meta", {}),
        "sourceType": normalize_source_type(record.get("sourceType") or record.get("meta", {}).get("sourceType")),
    }
    if isinstance(record.get("runtime"), dict):
        meta_payload["runtime"] = record.get("runtime")
    with db_connection() as conn, conn.cursor() as cur:
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


def save_sessions(
    sessions: list[dict[str, Any]],
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    normalize_source_type: Callable[[Any], str],
    data_dir: Path,
    sessions_path: Path,
) -> None:
    """按当前存储模式保存故事会话列表。"""
    if use_database_storage:
        for item in sessions:
            save_session_record(item, db_connection, normalize_source_type)
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_path.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def insert_new_session_record(
    session_record: dict[str, Any],
    sessions: Optional[list[dict[str, Any]]],
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    normalize_source_type: Callable[[Any], str],
    data_dir: Path,
    sessions_path: Path,
    psycopg_module: Any,
) -> None:
    """新增单条 session；数据库模式下只写当前记录。"""
    if use_database_storage:
        save_session_record(session_record, db_connection, normalize_source_type)
        return
    active_sessions = sessions if sessions is not None else load_sessions(
        False,
        db_connection,
        psycopg_module,
        sessions_path,
        normalize_source_type,
    )
    active_sessions.insert(0, session_record)
    save_sessions(active_sessions, False, db_connection, normalize_source_type, data_dir, sessions_path)
