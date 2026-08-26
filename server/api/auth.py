"""Router auth — login/logout/me + agent token management."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from server.api.deps import SESSION_COOKIE, client_ip, require_admin
from server.ingest import RateLimiter
from server.storage.db import Database
from server.webui.auth import sign_session, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_LOGIN_LIMIT_PER_MIN = 10


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: Annotated[dict[str, str], Body()],
) -> dict[str, Any]:
    """ตรวจ username/password กับ config; ผ่าน → ตั้ง HttpOnly cookie."""

    ip = client_ip(request)
    limiter: RateLimiter = request.app.state.login_limiter
    if not limiter.allow(ip, _LOGIN_LIMIT_PER_MIN):
        raise HTTPException(status_code=429, detail="ลองเข้าสู่ระบบถี่เกินไป กรุณารอสักครู่")
    cfg = request.app.state.config
    username = body.get("username", "")
    password = body.get("password", "")
    if (
        username == cfg.webui.admin_user
        and cfg.webui.admin_pass_hash
        and verify_password(password, cfg.webui.admin_pass_hash)
    ):
        cookie = sign_session(request.app.state.session_secret, username)
        response.set_cookie(
            SESSION_COOKIE,
            cookie,
            httponly=True,
            samesite="lax",
            secure=cfg.webui.secure_cookie,
            max_age=7 * 86400,
        )
        return {"ok": True}
    raise HTTPException(status_code=401, detail="username หรือ password ไม่ถูกต้อง")


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, Any]:
    """ลบ session cookie."""

    response.delete_cookie(
        SESSION_COOKIE,
        secure=request.app.state.config.webui.secure_cookie,
    )
    return {"ok": True}


@router.get("/me")
async def me(user: Annotated[str, Depends(require_admin)]) -> dict[str, Any]:
    """คืนข้อมูลผู้ใช้ปัจจุบัน."""

    return {"username": user}


@router.get("/tokens")
async def list_tokens(
    request: Request, _: Annotated[str, Depends(require_admin)]
) -> list[dict[str, str]]:
    """คืนรายชื่อ host + token (สำหรับหน้า settings)."""

    db: Database = request.app.state.db
    return await db.list_tokens()


@router.post("/tokens")
async def create_token(
    request: Request,
    _: Annotated[str, Depends(require_admin)],
    body: Annotated[dict[str, str], Body()],
) -> dict[str, str]:
    """สร้าง token ใหม่ให้ host_id (แสดงครั้งเดียว)."""

    host_id = (body.get("host_id") or "").strip()
    if not host_id:
        raise HTTPException(status_code=400, detail="ต้องระบุ host_id")
    db: Database = request.app.state.db
    token = str(uuid.uuid4())
    await db.set_host_token(host_id, token)
    return {"host_id": host_id, "token": token}


@router.delete("/tokens/{host_id}")
async def revoke_token(
    request: Request, host_id: str, _: Annotated[str, Depends(require_admin)]
) -> dict[str, Any]:
    """เพิกถอน token ของ host."""

    db: Database = request.app.state.db
    if not await db.revoke_token(host_id):
        raise HTTPException(status_code=404, detail="ไม่พบ host")
    return {"ok": True, "host_id": host_id}
