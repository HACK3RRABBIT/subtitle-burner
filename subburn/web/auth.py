import hmac
import secrets
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config as appconfig

# ---------------------------------------------------------------------------
# Auth (optional single shared password - only matters once this is reachable
# beyond localhost; if no password is configured, everything is open, same as
# before this existed)
# ---------------------------------------------------------------------------

# Session tokens for the optional shared-password login (used once this app
# is reachable beyond localhost - LAN or a public tunnel - since it has no
# per-user accounts, just one password gating the whole thing). Maps token ->
# expiry epoch seconds. In-memory only: restarting the server logs everyone
# out, which is an acceptable tradeoff for how small/simple this needs to be.
SESSIONS: dict[str, float] = {}
SESSIONS_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 30 * 24 * 3600


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with SESSIONS_LOCK:
        SESSIONS[token] = time.time() + SESSION_TTL_SECONDS
    return token


def require_auth(request: Request):
    password = appconfig.load().get("app_password")
    if not password:
        return
    token = request.cookies.get("session")
    with SESSIONS_LOCK:
        expiry = SESSIONS.get(token) if token else None
        valid = expiry is not None and expiry > time.time()
    if not valid:
        raise HTTPException(401, "Not authenticated")


class LoginRequest(BaseModel):
    password: str


router = APIRouter(prefix="/api/auth")


@router.get("/status")
async def auth_status(request: Request):
    password = appconfig.load().get("app_password")
    if not password:
        return {"auth_required": False, "authenticated": True}
    token = request.cookies.get("session")
    with SESSIONS_LOCK:
        expiry = SESSIONS.get(token) if token else None
        valid = expiry is not None and expiry > time.time()
    return {"auth_required": True, "authenticated": valid}


@router.post("/login")
async def login(body: LoginRequest):
    password = appconfig.load().get("app_password")
    if not password or not hmac.compare_digest(body.password, password):
        raise HTTPException(401, "Incorrect password")
    token = create_session()
    response = JSONResponse({"ok": True})
    response.set_cookie("session", token, max_age=SESSION_TTL_SECONDS, httponly=True, samesite="lax")
    return response


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        with SESSIONS_LOCK:
            SESSIONS.pop(token, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session")
    return response
