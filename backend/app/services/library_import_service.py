"""书市故事包导入服务：负责把外部 package 导入 library_stories 与 seed 会话。"""

from __future__ import annotations

import time
from typing import Any, Callable, Type


def import_library_story_package(
    server_session: dict[str, Any],
    body: dict[str, Any],
    use_database_storage: bool,
    clean_model_text: Callable[[Any], str],
    story_package_validation_error: Callable[[dict[str, Any]], str | None],
    ensure_library_story_table: Callable[[], None],
    db_connection: Callable[[], Any],
    save_session_record: Callable[[dict[str, Any]], None],
    library_seed_user_id: str,
    package_version: int,
    template_package_generator: str,
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """导入 story package 到书市来源表与 library seed。"""
    if not use_database_storage:
        raise http_exception_cls(status_code=400, detail="Library import requires DATABASE_URL storage mode")

    raw_package = body.get("package")
    if not isinstance(raw_package, dict):
        raise http_exception_cls(status_code=400, detail="Missing package")
    validation_error = story_package_validation_error(raw_package)
    if validation_error:
        raise http_exception_cls(status_code=400, detail={"message": validation_error})
    normalized_package = {**raw_package}
    normalized_package["version"] = int(raw_package.get("version") or package_version)
    normalized_package["generatedBy"] = raw_package.get("generatedBy") or template_package_generator

    now = int(time.time())
    story_id = clean_model_text(body.get("storyId", "")) or f"library-import-{now}"
    if story_id.startswith("library-") and not story_id.startswith("library-import-"):
        raise http_exception_cls(status_code=400, detail="System library IDs are reserved and cannot be overwritten")
    title = clean_model_text(body.get("title", "")) or clean_model_text(raw_package.get("title", "")) or "未命名书市故事"
    opening = clean_model_text(body.get("opening", "")) or title
    summary = clean_model_text(body.get("summary", "")) or opening[:80]
    sort_raw = body.get("sortOrder", now)
    try:
        sort_order = int(sort_raw)
    except (TypeError, ValueError):
        sort_order = now
    enabled = bool(body.get("enabled", True))

    ensure_library_story_table()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO library_stories (id, title, summary, opening, enabled, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                opening = EXCLUDED.opening,
                enabled = EXCLUDED.enabled,
                sort_order = EXCLUDED.sort_order,
                updated_at = EXCLUDED.updated_at
            """,
            (story_id, title, summary, opening, enabled, sort_order, now, now),
        )

    seed_record = {
        "id": f"seed-{story_id}",
        "kind": "library_seed_package",
        "createdAt": now,
        "updatedAt": now,
        "userId": library_seed_user_id,
        "status": "ready",
        "packageStatus": "ready",
        "sourceType": "library",
        "meta": {
            "openingId": story_id,
            "opening": opening,
            "role": "主人公",
            "author": server_session.get("user", {}).get("name") or "Workbench Import",
            "sourceType": "library",
            "importedBy": server_session.get("user", {}).get("userId") or "",
        },
        "personaProfile": {},
        "package": normalized_package,
        "runtime": None,
        "completedRun": None,
    }
    save_session_record(seed_record)
    return {
        "storyId": story_id,
        "seedSessionId": seed_record["id"],
        "title": title,
        "summary": summary,
        "opening": opening,
        "enabled": enabled,
    }


def delete_imported_library_story(
    story_id: str,
    current_user_id: str,
    is_operator: bool,
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    library_seed_user_id: str,
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """删除一个导入到书市的故事（含对应 seed）。"""
    started_at = time.time()
    if not use_database_storage:
        raise http_exception_cls(status_code=400, detail="Library delete requires DATABASE_URL storage mode")
    normalized_story_id = str(story_id or "").strip()
    if not normalized_story_id:
        raise http_exception_cls(status_code=400, detail="Missing story_id")
    is_prefixed_import = normalized_story_id.startswith("library-import-")
    is_marked_import = False
    probe_started = time.time()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(meta_json ->> 'importedBy', '') AS imported_by
            FROM story_sessions
            WHERE id = %s
              AND kind = 'library_seed_package'
              AND user_id = %s
            LIMIT 1
            """,
            (f"seed-{normalized_story_id}", library_seed_user_id),
        )
        row = cur.fetchone()
        imported_by = ""
        if row:
            if isinstance(row, dict):
                imported_by = str(row.get("imported_by") or "")
            elif isinstance(row, (list, tuple)) and row:
                imported_by = str(row[0] or "")
        imported_by = imported_by.strip()
        is_marked_import = bool(imported_by)
    probe_elapsed_ms = int((time.time() - probe_started) * 1000)
    print(
        f"[library-delete] probe story_id={normalized_story_id} is_prefixed={is_prefixed_import} is_marked_import={is_marked_import} elapsed_ms={probe_elapsed_ms}",
        flush=True,
    )
    if not is_prefixed_import and not is_marked_import:
        raise http_exception_cls(status_code=400, detail="Only imported library stories can be deleted here")
    if not is_operator and not is_marked_import:
        raise http_exception_cls(status_code=403, detail="Only operator can delete legacy imported stories without importer metadata")
    if is_marked_import and not is_operator and imported_by != str(current_user_id or "").strip():
        raise http_exception_cls(status_code=403, detail="Only importer or operator can delete this story")

    delete_started = time.time()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM library_stories WHERE id = %s", (normalized_story_id,))
        story_deleted = cur.rowcount > 0
        cur.execute(
            """
            DELETE FROM story_sessions
            WHERE id = %s
              AND kind = 'library_seed_package'
              AND user_id = %s
            """,
            (f"seed-{normalized_story_id}", library_seed_user_id),
        )
        seed_deleted = cur.rowcount > 0
    delete_elapsed_ms = int((time.time() - delete_started) * 1000)
    total_elapsed_ms = int((time.time() - started_at) * 1000)
    print(
        f"[library-delete] sql story_id={normalized_story_id} story_deleted={story_deleted} seed_deleted={seed_deleted} delete_elapsed_ms={delete_elapsed_ms} total_elapsed_ms={total_elapsed_ms}",
        flush=True,
    )

    if not story_deleted:
        if seed_deleted:
            raise http_exception_cls(status_code=409, detail="Seed was deleted but library story row was not found")
        raise http_exception_cls(status_code=404, detail="Imported library story not found")
    return {
        "storyId": normalized_story_id,
        "storyDeleted": story_deleted,
        "seedDeleted": seed_deleted,
    }
