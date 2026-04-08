"""认证路由模块，负责 OAuth 登录、换 token、会话查询与退出登录接口。"""

from __future__ import annotations

import time
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import settings
from ..security import random_urlsafe, sign_payload


def create_auth_router(deps: SimpleNamespace) -> APIRouter:
    """创建认证相关路由。"""
    router = APIRouter()

    @router.get("/api/auth/login")
    async def auth_login() -> RedirectResponse:
        """发起 OAuth 登录跳转并写入防 CSRF 的 state。"""
        deps.require_env()
        state = random_urlsafe(24)
        params = {
            "client_id": settings.client_id,
            "redirect_uri": settings.redirect_uri,
            "response_type": "code",
            "scope": settings.scope,
            "state": state,
        }
        response = RedirectResponse(url=f"{settings.auth_url}?{urlencode(params)}", status_code=302)
        response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600, path=deps.cookie_path)
        return response

    @router.post("/api/auth/exchange")
    async def auth_exchange(request: Request) -> JSONResponse:
        """用 OAuth code 换 token，并建立后端签名 session。"""
        deps.require_env()
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
        response.set_cookie("session", session_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7, path=deps.cookie_path)
        response.delete_cookie("oauth_state", path=deps.cookie_path)
        return response

    @router.get("/api/me")
    async def current_user(request: Request) -> JSONResponse:
        """返回当前是否已登录以及用户信息。"""
        deps.require_env()
        try:
            server_session = deps.get_server_session(request)
        except HTTPException:
            return JSONResponse({"authenticated": False})
        return JSONResponse({"authenticated": True, "user": server_session.get("user", {})})

    @router.post("/api/auth/logout")
    async def auth_logout(request: Request) -> Response:
        """清理登录相关 cookie。"""
        response = JSONResponse({"ok": True})
        response.delete_cookie("session", path=deps.cookie_path)
        response.delete_cookie("oauth_state", path=deps.cookie_path)
        return response

    return router
