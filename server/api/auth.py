"""Router auth — login/logout/me + agent token management + audit log."""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from server.api.deps import SESSION_COOKIE, client_ip, require_admin
from server.storage.db import Database
from server.webui.auth import sign_session, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_LOGIN_WINDOW = 60  # sliding window (วินาที) สำหรับ rate limit


async def _check_login_rate(request: Request, ip: str, db: Database) -> None:
    """ตรวจอัตรา login ต่อ IP + รวมทุก IP (กัน brute-force/botnet) — เกิน → 429.

    เก็บใน DB (`login_attempts`) เพื่อ persist ข้าม restart + ใช้ได้กับทุก worker.
    """

    cfg = request.app.state.config.auth
    now = time.time()
    since = now - _LOGIN_WINDOW
    await db.prune_login_attempts(since)
    if cfg.login_rate_per_min > 0:
        per_ip = await db.count_login_attempts(ip, since)
        if per_ip >= cfg.login_rate_per_min:
            await db.add_audit("login.blocked", ip, "เกินอัตรา/นาทีต่อ IP", False)
            raise HTTPException(status_code=429, detail="ลองเข้าสู่ระบบถี่เกินไป กรุณารอสักครู่")
    if cfg.login_global_per_min > 0:
        total = await db.count_login_attempts_all(since)
        if total >= cfg.login_global_per_min:
            await db.add_audit("login.blocked", ip, "เกินอัตรารวมทุก IP", False)
            raise HTTPException(status_code=429, detail="ระบบกำลังถูกโจมตี กรุณารอสักครู่")


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: Annotated[dict[str, str], Body()],
) -> dict[str, Any]:
    """ตรวจ username/password กับ config; ผ่าน → ตั้ง HttpOnly cookie.

    บันทึกทุกความพยายาม (สำเร็จ/ล้มเหลว/ถูกจำกัด) ลง audit log.
    """

    ip = client_ip(request)
    db: Database = request.app.state.db
    cfg = request.app.state.config
    await _check_login_rate(request, ip, db)
    username = body.get("username", "")
    password = body.get("password", "")
    await db.record_login_attempt(ip)
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
        await db.add_audit("login.ok", ip, f"user={username}", True)
        return {"ok": True}
    await db.add_audit("login.fail", ip, f"user={username}", False)
    raise HTTPException(status_code=401, detail="username หรือ password ไม่ถูกต้อง")


@router.get("/audit")
async def audit_log(
    request: Request, _: Annotated[str, Depends(require_admin)]
) -> JSONResponse:
    """คืนประวัติความปลอดภัย (login สำเร็จ/ล้มเหลว/ถูกจำกัด) สำหรับ admin."""

    db: Database = request.app.state.db
    cfg = request.app.state.config
    keep_sec = cfg.auth.audit_keep_days * 86400
    if keep_sec > 0:
        await db.prune_audit(time.time() - keep_sec)
    return JSONResponse(await db.list_audit())


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
