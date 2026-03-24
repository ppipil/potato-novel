from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .integration import build_integration_manifest
from .openings import PRESET_OPENINGS, get_opening_summary, get_opening_title
from .security import random_urlsafe, sign_payload, verify_payload

app = FastAPI(title="Potato Novel Backend")
session_store: dict[str, dict[str, Any]] = {}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORIES_PATH = DATA_DIR / "stories.json"
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_env() -> None:
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


def _get_server_session(request: Request) -> dict[str, Any]:
    session = request.cookies.get("session")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_payload(session, settings.session_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid session")
    server_session = session_store.get(payload.get("sid", ""))
    if not server_session:
        raise HTTPException(status_code=401, detail="Session expired")
    return server_session


def _load_stories() -> list[dict[str, Any]]:
    if not STORIES_PATH.exists():
        return []
    return json.loads(STORIES_PATH.read_text(encoding="utf-8"))


def _save_stories(stories: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_PATH.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")


def _compose_story_prompt(opening: str, role: str, user_name: str, extra_instruction: str = "") -> str:
    extra = f"\n补充要求：{extra_instruction.strip()}" if extra_instruction.strip() else ""
    return (
        f"你正在参与一个名为“土豆小说”的多人共创故事。\n"
        f"用户昵称：{user_name or 'SecondMe 用户'}\n"
        f"用户选择的角色：{role}\n"
        f"小说开头：{opening}\n"
        f"{extra}\n\n"
        "请以这个用户的 SecondMe 分身视角，和其他 AI/NPC 一起推进剧情，"
        "创作一篇 800 到 1500 字的中文短篇小说。"
        "要求包含标题、3到5个自然段、明确冲突、角色互动和一个完整结尾。"
    )


async def _call_secondme_chat(access_token: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        chat_response = await client.post(
            "https://api.mindverse.com/gate/lab/api/secondme/chat/stream",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"message": prompt},
        )
        if chat_response.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail={"message": "SecondMe chat request failed", "body": chat_response.text},
            )
        story_text = _extract_story_from_sse(chat_response.text)
        if not story_text.strip():
            raise HTTPException(status_code=400, detail="SecondMe chat returned empty content")
        return story_text


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/integration/manifest.json")
async def integration_manifest(request: Request) -> JSONResponse:
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    manifest = build_integration_manifest(base_url=base_url, app_id=settings.secondme_app_id)
    return JSONResponse(manifest)


@app.get("/api/auth/login")
async def auth_login() -> RedirectResponse:
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
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600)
    return response


@app.post("/api/auth/exchange")
async def auth_exchange(request: Request) -> JSONResponse:
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

    async with httpx.AsyncClient(timeout=20) as client:
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

    # Keep the cookie payload small enough for browsers to reliably store it.
    session_id = random_urlsafe(18)
    session_user = {
        "userId": userinfo.get("userId"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "avatar": userinfo.get("avatar"),
        "route": userinfo.get("route"),
    }
    session_store[session_id] = {
        "created_at": int(time.time()),
        "user": session_user,
        "token": {
            "access_token": access_token,
            "refresh_token": token_data.get("refreshToken") or token_data.get("refresh_token"),
            "expires_in": token_data.get("expiresIn") or token_data.get("expires_in"),
            "scope": token_data.get("scope", settings.scope),
        },
    }
    session_payload = {
        "iat": int(time.time()),
        "sid": session_id,
        "user": session_user,
    }
    session_token = sign_payload(session_payload, settings.session_secret)

    response = JSONResponse({"ok": True, "user": session_user})
    response.set_cookie("session", session_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
    response.delete_cookie("oauth_state")
    return response


@app.get("/api/me")
async def current_user(request: Request) -> JSONResponse:
    _require_env()
    try:
        server_session = _get_server_session(request)
    except HTTPException:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": server_session.get("user", {})})


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> Response:
    session = request.cookies.get("session")
    if session:
        payload = verify_payload(session, settings.session_secret)
        if payload and payload.get("sid") in session_store:
            session_store.pop(payload["sid"], None)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session")
    return response


@app.post("/api/story/generate")
async def generate_story(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)

    body = await request.json()
    opening = body.get("opening", "").strip()
    role = body.get("role", "").strip()
    if not opening or not role:
        raise HTTPException(status_code=400, detail="Missing opening or role")

    user = server_session["user"]
    access_token = server_session["token"]["access_token"]
    prompt = _compose_story_prompt(opening=opening, role=role, user_name=user.get("name") or "SecondMe 用户")
    story_text = await _call_secondme_chat(access_token=access_token, prompt=prompt)

    return JSONResponse(
        {
            "ok": True,
            "story": story_text,
            "meta": {
                "opening": opening,
                "role": role,
                "author": user.get("name") or "SecondMe 用户",
            },
        }
    )


@app.post("/api/story/save")
async def save_story(request: Request) -> JSONResponse:
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
        "userId": server_session["user"].get("userId"),
        "meta": {
            "opening": meta.get("opening", ""),
            "role": meta.get("role", ""),
            "author": meta.get("author") or server_session["user"].get("name") or "SecondMe 用户",
        },
        "story": story,
    }
    stories.insert(0, record)
    _save_stories(stories)
    return JSONResponse({"ok": True, "story": record})


@app.get("/api/stories")
async def list_stories(request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    stories = [item for item in _load_stories() if item.get("userId") == user_id]
    return JSONResponse({"ok": True, "stories": stories})


@app.get("/api/stories/{story_id}")
async def get_story(story_id: str, request: Request) -> JSONResponse:
    _require_env()
    server_session = _get_server_session(request)
    user_id = server_session["user"].get("userId")
    for item in _load_stories():
        if item.get("id") == story_id and item.get("userId") == user_id:
            return JSONResponse({"ok": True, "story": item})
    raise HTTPException(status_code=404, detail="Story not found")


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
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
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        requested = FRONTEND_DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


def _extract_story_from_sse(raw_text: str) -> str:
    chunks: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = httpx.Response(200, content=data).json()
        except Exception:
            continue
        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                chunks.append(content)
    return "".join(chunks)
