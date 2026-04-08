"""故事仓储模块，统一封装 stories 和 library story sources 的存储读写。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional


def story_row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    """把 stories 表的数据库行转换成接口记录。"""
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "userId": row["user_id"],
        "meta": row.get("meta_json") or {},
        "story": row["story_text"],
    }


def load_stories_from_db(db_connection: Callable[[], Any], psycopg_module: Any) -> list[dict[str, Any]]:
    """从数据库读取已保存故事列表。"""
    with db_connection() as conn, conn.cursor(row_factory=psycopg_module.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, user_id, title, story_text, meta_json, created_at, updated_at
            FROM stories
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        return [story_row_to_record(row) for row in cur.fetchall()]


def load_stories(
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    stories_path: Path,
) -> list[dict[str, Any]]:
    """按当前存储模式读取故事列表。"""
    if use_database_storage:
        return load_stories_from_db(db_connection, psycopg_module)
    if not stories_path.exists():
        return []
    return json.loads(stories_path.read_text(encoding="utf-8"))


def save_story_record(record: dict[str, Any], db_connection: Callable[[], Any]) -> None:
    """把单条故事记录写入数据库。"""
    with db_connection() as conn, conn.cursor() as cur:
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


def save_stories(
    stories: list[dict[str, Any]],
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    data_dir: Path,
    stories_path: Path,
) -> None:
    """按当前存储模式保存故事列表。"""
    if use_database_storage:
        for item in stories:
            save_story_record(item, db_connection)
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    stories_path.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_story_record(
    story_id: str,
    user_id: str,
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    data_dir: Path,
    stories_path: Path,
) -> bool:
    """删除当前用户的一条已保存故事。"""
    if use_database_storage:
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM stories
                WHERE id = %s AND user_id = %s
                """,
                (story_id, user_id),
            )
            return cur.rowcount > 0

    stories = load_stories(False, db_connection, None, stories_path)
    remaining = [item for item in stories if not (item.get("id") == story_id and item.get("userId") == user_id)]
    if len(remaining) == len(stories):
        return False
    data_dir.mkdir(parents=True, exist_ok=True)
    stories_path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def default_library_story_rows(preset_openings: list[str], get_opening_title: Callable[[str], str], get_opening_summary: Callable[[str], str]) -> list[dict[str, Any]]:
    """返回代码内置的默认书城模板。"""
    rows = []
    for index, opening in enumerate(preset_openings, start=1):
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


def ensure_library_story_table(use_database_storage: bool, db_connection: Callable[[], Any]) -> None:
    """确保数据库中存在书城模板表。"""
    if not use_database_storage:
        return
    with db_connection() as conn, conn.cursor() as cur:
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


def seed_default_library_stories_in_db(
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    defaults: list[dict[str, Any]],
) -> None:
    """首次使用数据库模式时，把默认测试故事写入 library_stories。"""
    if not use_database_storage:
        return
    ensure_library_story_table(use_database_storage, db_connection)
    now = int(time.time())
    with db_connection() as conn, conn.cursor() as cur:
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


def load_library_story_sources_from_db(
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    defaults: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从数据库读取启用中的书城模板列表。"""
    seed_default_library_stories_in_db(True, db_connection, defaults)
    with db_connection() as conn, conn.cursor(row_factory=psycopg_module.rows.dict_row) as cur:
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


def load_library_story_sources(
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    psycopg_module: Any,
    preset_openings: list[str],
    get_opening_title: Callable[[str], str],
    get_opening_summary: Callable[[str], str],
) -> list[dict[str, Any]]:
    """按当前存储模式读取书城模板列表。"""
    defaults = default_library_story_rows(preset_openings, get_opening_title, get_opening_summary)
    if use_database_storage:
        return load_library_story_sources_from_db(db_connection, psycopg_module, defaults)
    return defaults
