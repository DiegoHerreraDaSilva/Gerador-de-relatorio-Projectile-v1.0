"""Rotas de autenticação (`/auth/*`) — extraído de `main.py` na Fase 5."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ... import management
from ...auth import (
    LoginError,
    RateLimitError,
    check_rate_limit,
    create_session,
    delete_session,
    get_session,
    register_login_failure,
    register_login_success,
    verify_projectile_login,
)
from ...projectile_db import ProjectileDbError
from ..dependencies import SESSION_COOKIE
from ..errors import log_and_generic_error

router = APIRouter()


class LoginRequest(BaseModel):
    login: str
    password: str


@router.post("/auth/login")
async def login_endpoint(payload: LoginRequest, request: Request, response: Response):
    client_key = request.client.host if request.client else "unknown"

    try:
        check_rate_limit(client_key)
    except RateLimitError as e:
        raise HTTPException(429, str(e))

    try:
        user = verify_projectile_login(payload.login.strip(), payload.password)
    except LoginError as e:
        register_login_failure(client_key)
        raise HTTPException(401, str(e))
    except ProjectileDbError as e:
        raise log_and_generic_error(e)

    register_login_success(client_key)
    token = create_session(user)
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", max_age=8 * 60 * 60,
        # secure=True automaticamente quando servido via HTTPS — hoje é HTTP puro
        # (rede interna), então isso já fica pronto pro dia que rodar atrás de TLS.
        secure=(request.url.scheme == "https"),
    )
    return {
        "name": user["name"], "login": user["login"], "email": user["email"],
        "is_manager": user["login"].lower() in management.MANAGEMENT_PANEL_LOGINS,
        "is_translate_allowed": user["login"].lower() in management.TRANSLATE_ALLOWED_LOGINS,
    }


@router.get("/auth/me")
async def me_endpoint(request: Request):
    session = get_session(request.cookies.get(SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Não autenticado.")
    return {
        "name": session["name"], "login": session["login"], "email": session["email"],
        "is_manager": session["login"].lower() in management.MANAGEMENT_PANEL_LOGINS,
        "is_translate_allowed": session["login"].lower() in management.TRANSLATE_ALLOWED_LOGINS,
    }


@router.post("/auth/logout")
async def logout_endpoint(request: Request, response: Response):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}
