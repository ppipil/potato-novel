"""书城 seed 服务模块，负责 seed 状态查询、首次播种编排、并发锁与结果复用。"""

from __future__ import annotations

import asyncio
import errno
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Type


def build_library_story_rows(
    sessions: Optional[list[dict[str, Any]]],
    load_library_seed_index: Callable[[], dict[str, dict[str, Any]]],
    load_library_story_sources: Callable[[], list[dict[str, Any]]],
    clean_model_text: Callable[[str], str],
    library_seed_user_id: str,
) -> list[dict[str, Any]]:
    """构造书城推荐故事列表及其 seed 播种状态。"""
    seed_map: dict[str, dict[str, Any]] = {}
    if sessions is not None:
        for item in sessions:
            if item.get("kind") != "library_seed_package":
                continue
            if item.get("userId") != library_seed_user_id:
                continue
            opening_id = clean_model_text(item.get("meta", {}).get("openingId", ""))
            if not opening_id:
                continue
            seed_map[opening_id] = item
    else:
        seed_map = load_library_seed_index()

    rows: list[dict[str, Any]] = []
    for source in load_library_story_sources():
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


def resolve_library_opening(
    story_id: str,
    build_library_story_rows: Callable[[], list[dict[str, Any]]],
    http_exception_cls: Type[Exception],
) -> str:
    """根据书城 story id 解析对应的 opening 文案。"""
    for row in build_library_story_rows():
        if row["id"] == story_id:
            return row["opening"]
    raise http_exception_cls(status_code=404, detail="Library story not found")


def find_library_seed_session(
    sessions: Optional[list[dict[str, Any]]],
    story_id: str,
    use_database_storage: bool,
    find_library_seed_session_by_opening_id_from_db: Callable[[str], Optional[dict[str, Any]]],
    load_sessions: Callable[[], list[dict[str, Any]]],
    clean_model_text: Callable[[str], str],
    library_seed_user_id: str,
    package_version: int,
) -> Optional[dict[str, Any]]:
    """在会话列表或数据库中查找某个书城故事的全局 seed session。"""
    if use_database_storage:
        return find_library_seed_session_by_opening_id_from_db(story_id)
    active_sessions = sessions if sessions is not None else load_sessions()
    for item in active_sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != library_seed_user_id:
            continue
        if clean_model_text(item.get("meta", {}).get("openingId", "")) != story_id:
            continue
        package = item.get("package", {})
        if package.get("version") != package_version:
            continue
        return item
    return None


def require_library_seed_session(
    sessions: Optional[list[dict[str, Any]]],
    opening_id: str,
    find_library_seed_session: Callable[[Optional[list[dict[str, Any]]], str], Optional[dict[str, Any]]],
    debug_story_log: Callable[[str, dict[str, Any]], None],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """读取指定书城故事的全局 seed；如果不存在则直接抛错。"""
    seed = find_library_seed_session(sessions, opening_id)
    if not seed:
        debug_story_log("[library-seed-missing]", {"openingId": opening_id})
        raise http_exception_cls(
            status_code=409,
            detail={
                "message": "该故事的公共内容还没播种完成，请先生成 seed。",
                "openingId": opening_id,
            },
        )
    debug_story_log(
        "[library-seed-hit]",
        {
            "openingId": opening_id,
            "seedSessionId": seed.get("id"),
            "generatedNow": False,
        },
    )
    return seed


def _find_library_seed_generation_session(sessions: list[dict[str, Any]], story_id: str, clean_model_text: Callable[[str], str], library_seed_user_id: str) -> Optional[dict[str, Any]]:
    """查找某个书城故事是否已有进行中的 seed 生成占位。"""
    for item in sessions:
        if item.get("kind") != "library_seed_package":
            continue
        if item.get("userId") != library_seed_user_id:
            continue
        if clean_model_text(item.get("meta", {}).get("openingId", "")) != story_id:
            continue
        if item.get("packageStatus") != "generating":
            continue
        return item
    return None


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


def _build_pending_seed_record(
    sessions: list[dict[str, Any]],
    opening: str,
    opening_id: str,
    persona_profile: dict[str, Any],
    find_library_seed_session: Callable[[Optional[list[dict[str, Any]]], str], Optional[dict[str, Any]]],
    clean_model_text: Callable[[str], str],
    library_seed_user_id: str,
) -> dict[str, Any]:
    """构造并写入某个书城 seed 的生成中占位记录。"""
    existing = _find_library_seed_generation_session(sessions, opening_id, clean_model_text, library_seed_user_id)
    existing_ready = find_library_seed_session(sessions, opening_id)
    now = int(time.time())
    pending_record = {
        "id": f"seed-{opening_id}",
        "kind": "library_seed_package",
        "createdAt": existing_ready.get("createdAt") if existing_ready else existing.get("createdAt") if existing else now,
        "updatedAt": now,
        "userId": library_seed_user_id,
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
    return pending_record


def _build_ready_seed_record(
    sessions: list[dict[str, Any]],
    story_package: dict[str, Any],
    opening: str,
    opening_id: str,
    persona_profile: dict[str, Any],
    clean_model_text: Callable[[str], str],
    library_seed_user_id: str,
) -> dict[str, Any]:
    """构造播种完成后的 ready seed 记录。"""
    existing_generating = _find_library_seed_generation_session(sessions, opening_id, clean_model_text, library_seed_user_id)
    now = int(time.time())
    return {
        "id": f"seed-{opening_id}",
        "kind": "library_seed_package",
        "createdAt": existing_generating.get("createdAt") if existing_generating else now,
        "updatedAt": now,
        "userId": library_seed_user_id,
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


def _restore_previous_seed_state(
    sessions: list[dict[str, Any]],
    opening_id: str,
    previous_seed_record: Optional[dict[str, Any]],
) -> None:
    """在播种失败时恢复旧 seed，或清理生成中占位。"""
    if previous_seed_record:
        _upsert_session_by_id(sessions, previous_seed_record)
        return
    _remove_session_by_id(sessions, f"seed-{opening_id}")


def _library_seed_lock_path(lock_dir: Path, opening_id: str) -> Path:
    """返回某个书城 seed 对应的文件锁路径。"""
    return lock_dir / f"{opening_id}.lock"


def _try_acquire_library_seed_generation_lock(
    opening_id: str,
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    lock_dir: Path,
) -> bool:
    """尝试获取某个书城 seed 的生成锁。"""
    if use_database_storage:
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"library-seed:{opening_id}",))
            row = cur.fetchone()
        return bool(row and row[0])
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _library_seed_lock_path(lock_dir, opening_id)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return False
        raise


def _release_library_seed_generation_lock(
    opening_id: str,
    use_database_storage: bool,
    db_connection: Callable[[], Any],
    lock_dir: Path,
) -> None:
    """释放某个书城 seed 的生成锁。"""
    if use_database_storage:
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"library-seed:{opening_id}",))
        return
    lock_path = _library_seed_lock_path(lock_dir, opening_id)
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


async def _wait_for_library_seed_package(
    opening_id: str,
    timeout_seconds: float,
    wait_interval_seconds: float,
    load_sessions: Callable[[], list[dict[str, Any]]],
    find_library_seed_session: Callable[[Optional[list[dict[str, Any]]], str], Optional[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """等待其他并发请求完成某个书城 seed 的首次播种。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        existing = find_library_seed_session(load_sessions(), opening_id)
        if existing:
            return existing
        await asyncio.sleep(wait_interval_seconds)
    return None


async def load_or_generate_library_seed_package(
    sessions: list[dict[str, Any]],
    opening: str,
    opening_id: str,
    seed_ready_from_client: bool,
    force_regenerate: bool,
    skip_existing_check: bool,
    load_sessions: Callable[[], list[dict[str, Any]]],
    save_sessions: Callable[[list[dict[str, Any]]], None],
    clean_model_text: Callable[[str], str],
    use_database_storage: bool,
    find_library_seed_session_by_opening_id_from_db: Callable[[str], Optional[dict[str, Any]]],
    has_volcengine_prose_provider: Callable[[], bool],
    build_story_package_two_stage: Callable[..., Awaitable[dict[str, Any]]],
    debug_story_log: Callable[[str, dict[str, Any]], None],
    http_exception_cls: Type[Exception],
    package_version: int,
    library_seed_user_id: str,
    lock_dir: Path,
    db_connection: Callable[[], Any],
    wait_timeout_seconds: float,
    wait_interval_seconds: float,
) -> tuple[dict[str, Any], bool]:
    """读取或首次生成某个书城开头对应的全局 seed package。"""
    def _find_seed(active_sessions: Optional[list[dict[str, Any]]], story_id: str) -> Optional[dict[str, Any]]:
        return find_library_seed_session(
            active_sessions,
            story_id,
            use_database_storage,
            find_library_seed_session_by_opening_id_from_db,
            load_sessions,
            clean_model_text,
            library_seed_user_id,
            package_version,
        )

    existing_seed = None if skip_existing_check else _find_seed(sessions, opening_id)
    if existing_seed and not force_regenerate:
        debug_story_log(
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
        debug_story_log(
            "[library-seed-stale]",
            {
                "openingId": opening_id,
                "seedReadyFromClient": seed_ready_from_client,
                "forceRegenerate": force_regenerate,
            },
        )
        raise http_exception_cls(status_code=409, detail="Seed status changed, please refresh bookshelf and retry")

    if not has_volcengine_prose_provider():
        raise http_exception_cls(status_code=500, detail="Doubao(Volcengine) is required for first-time library story generation")

    persona_profile = {
        "key": "library_seed",
        "label": "图书馆播种者模板",
        "preferredStyles": ["trust", "tease", "confrontation"],
        "description": "用于模板故事全局首次生成。",
        "source": "library-seed-generation",
    }
    debug_story_log(
        "[library-seed-miss]",
        {
            "openingId": opening_id,
            "seedReadyFromClient": seed_ready_from_client,
            "forceRegenerate": force_regenerate,
            "generating": True,
        },
    )

    lock_acquired = _try_acquire_library_seed_generation_lock(
        opening_id=opening_id,
        use_database_storage=use_database_storage,
        db_connection=db_connection,
        lock_dir=lock_dir,
    )
    if not lock_acquired:
        debug_story_log("[library-seed-waiting]", {"openingId": opening_id})
        waited_seed = await _wait_for_library_seed_package(
            opening_id=opening_id,
            timeout_seconds=wait_timeout_seconds,
            wait_interval_seconds=wait_interval_seconds,
            load_sessions=load_sessions,
            find_library_seed_session=_find_seed,
        )
        if waited_seed:
            debug_story_log(
                "[library-seed-wait-hit]",
                {
                    "openingId": opening_id,
                    "seedSessionId": waited_seed.get("id"),
                    "generatedNow": False,
                },
            )
            return waited_seed.get("package", {}), False
        raise http_exception_cls(
            status_code=409,
            detail={
                "message": "该故事的公共内容正在播种中，请稍后重试。",
                "openingId": opening_id,
            },
        )

    try:
        debug_story_log("[library-seed-lock-acquired]", {"openingId": opening_id})
        active_sessions = load_sessions()
        existing_seed = _find_seed(active_sessions, opening_id)
        if existing_seed and not force_regenerate:
            debug_story_log(
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
        pending_record = _build_pending_seed_record(
            sessions=active_sessions,
            opening=opening,
            opening_id=opening_id,
            persona_profile=persona_profile,
            find_library_seed_session=_find_seed,
            clean_model_text=clean_model_text,
            library_seed_user_id=library_seed_user_id,
        )
        save_sessions(active_sessions)
        debug_story_log(
            "[library-seed-pending-saved]",
            {
                "openingId": opening_id,
                "seedSessionId": pending_record["id"],
            },
        )

        try:
            debug_story_log(
                "[library-seed-build-start]",
                {
                    "openingId": opening_id,
                    "choiceNodeCount": 4,
                    "contentNodeCount": 7,
                },
            )
            story_package = await build_story_package_two_stage(
                access_token=None,
                opening=opening,
                role="主人公",
                user_name="土豆图书馆",
                persona_profile=persona_profile,
                choice_provider="volcengine",
                prose_provider="volcengine",
            )
        except Exception as exc:
            active_sessions = load_sessions()
            _restore_previous_seed_state(active_sessions, opening_id, previous_seed_record)
            save_sessions(active_sessions)
            if isinstance(exc, http_exception_cls):
                detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                reason = detail.get("error") or detail.get("reason") or detail.get("message") or "unknown"
                raise http_exception_cls(
                    status_code=502,
                    detail={
                        "message": "首访故事播种失败，请重试。",
                        "reason": reason,
                    },
                ) from exc
            raise

        active_sessions = load_sessions()
        seed_record = _build_ready_seed_record(
            sessions=active_sessions,
            story_package=story_package,
            opening=opening,
            opening_id=opening_id,
            persona_profile=persona_profile,
            clean_model_text=clean_model_text,
            library_seed_user_id=library_seed_user_id,
        )
        _upsert_session_by_id(active_sessions, seed_record)
        save_sessions(active_sessions)
        debug_story_log(
            "[library-seed-generated]",
            {
                "openingId": opening_id,
                "seedSessionId": seed_record["id"],
                "generatedNow": True,
            },
        )
        return story_package, True
    finally:
        _release_library_seed_generation_lock(
            opening_id=opening_id,
            use_database_storage=use_database_storage,
            db_connection=db_connection,
            lock_dir=lock_dir,
        )


async def generate_library_seed_package(
    opening: str,
    opening_id: str,
    force_regenerate: bool,
    skip_existing_check: bool,
    load_sessions: Callable[[], list[dict[str, Any]]],
    load_or_generate_library_seed_package: Callable[..., Awaitable[tuple[dict[str, Any], bool]]],
    find_library_seed_session: Callable[[Optional[list[dict[str, Any]]], str], Optional[dict[str, Any]]],
    debug_story_log: Callable[[str, dict[str, Any]], None],
) -> tuple[dict[str, Any], bool]:
    """显式播种某本书城故事的全局 seed。"""
    sessions = load_sessions()
    if not force_regenerate and not skip_existing_check:
        existing = find_library_seed_session(sessions, opening_id)
        if existing:
            debug_story_log(
                "[library-seed-hit]",
                {
                    "openingId": opening_id,
                    "seedSessionId": existing.get("id"),
                    "generatedNow": False,
                },
            )
            return existing.get("package", {}), False
    return await load_or_generate_library_seed_package(
        sessions=sessions,
        opening=opening,
        opening_id=opening_id,
        seed_ready_from_client=False,
        force_regenerate=force_regenerate,
        skip_existing_check=skip_existing_check,
    )
