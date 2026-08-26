"""Dependency ที่ใช้ร่วมกันของ routers — require_admin (session cookie)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from server.webui.auth import verify_session

SESSION_COOKIE = "session"


def client_ip(request: Request) -> str:
    """คืน IP ของ client โดยรองรับ reverse proxy (X-Forwarded-For).

    Notes:
        ถ้า deploy หลัง reverse proxy (nginx/คาอ่าว) request.client.host จะเป็น IP ของ proxy
        ทุกครั้ง — จึง優先อ่าน X-Forwarded-For (ตัวแรก) เพื่อให้ rate limit แยกต่อ client จริง.
        ตัวอย่างที่น่าแก้เพิ่ม: config เปิด/ปิด trust proxy — ตอนนี้เปิดตลอด (สมมติ prod อยู่หลัง proxy).
    """

    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first and first.lower() != "unknown":
            return first
    return request.client.host if request.client else "unknown"


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
