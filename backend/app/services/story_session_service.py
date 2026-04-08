"""故事会话服务模块，负责会话开局决策与结局分析上下文整理。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Type


async def create_or_reuse_story_package(
    body: dict[str, Any],
    server_session: dict[str, Any],
    clean_model_text: Callable[[str], str],
    preset_openings: list[str],
    start_or_resume_library_story: Callable[..., Awaitable[tuple[dict[str, Any], bool, bool]]],
    start_or_generate_custom_story: Callable[..., Awaitable[tuple[dict[str, Any], bool]]],
    http_exception_cls: Type[Exception],
) -> tuple[dict[str, Any], bool]:
    """按 opening 类型选择 library 或 custom 的故事会话开局链路。"""
    opening = clean_model_text(body.get("opening", ""))
    role = clean_model_text(body.get("role", ""))
    if not opening or not role:
        raise http_exception_cls(status_code=400, detail="Missing opening or role")
    if opening in preset_openings:
        opening_id = f"library-{preset_openings.index(opening) + 1}"
        session_record, reused, _ = await start_or_resume_library_story(
            server_session,
            opening=opening,
            role=role,
            opening_id=opening_id,
            seed_ready_from_client=False,
            force_regenerate=bool(body.get("forceRegenerate")),
        )
        return session_record, reused
    return await start_or_generate_custom_story(
        server_session,
        opening=opening,
        role=role,
        force_regenerate=bool(body.get("forceRegenerate")),
    )


def build_ending_analysis_context(
    session_id: str,
    story: str,
    meta: dict[str, Any],
    user_id: str,
    find_session: Callable[[str, str], tuple[list[dict[str, Any]], dict[str, Any], int]],
    http_exception_cls: Type[Exception],
) -> dict[str, Any]:
    """根据 session 或直接传入的 meta，整理结局分析所需的输入上下文。"""
    if session_id:
        _, story_session, _ = find_session(session_id, user_id)
        if story_session.get("kind") == "story_package":
            completed_run = story_session.get("completedRun")
            if not completed_run:
                raise http_exception_cls(status_code=400, detail="Story package is not finished yet")
            return {
                "opening": story_session.get("meta", {}).get("opening", ""),
                "summary": completed_run.get("summary", ""),
                "transcript": completed_run.get("transcript", []),
                "state": completed_run.get("state", {}),
            }
        return {
            "opening": story_session.get("meta", {}).get("opening", ""),
            "summary": story_session.get("summary", ""),
            "transcript": story_session.get("transcript", []),
            "state": story_session.get("state", {}),
        }
    return {
        "opening": meta.get("opening", ""),
        "summary": meta.get("summary", "") or story,
        "transcript": meta.get("transcript", []) or [],
        "state": meta.get("state", {}) or {},
    }
