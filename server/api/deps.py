"""Dependency ที่ใช้ร่วมกันของ routers — require_admin (session cookie)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from server.webui.auth import verify_session

SESSION_COOKIE = "session"


async def require_admin(request: Request) -> str:
    """ตรวจ session cookie; คืน username ถ้าผ่าน (401 ถ้าไม่)."""

    cookie = request.cookies.get(SESSION_COOKIE)
    secret = request.app.state.session_secret
    if not cookie:
        raise HTTPException(status_code=401, detail="ยังไม่ได้เข้าสู่ระบบ")
    username = verify_session(secret, cookie)
    if username is None:
        raise HTTPException(status_code=401, detail="เซสชันหมดอายุหรือไม่ถูกต้อง")
    return username
