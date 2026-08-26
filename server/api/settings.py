"""Router settings — notifier webhook/telegram (ตั้งผ่าน WebUI, เก็บใน DB)."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from server.alerting import settings as notifier_settings
from server.api.deps import require_admin

router = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], dependencies=[Depends(require_admin)]
)


@router.get("/notifiers")
async def get_notifiers(request: Request) -> JSONResponse:
    """คืนค่า notifier (merged DB > config.toml) + สถานะ configured/enabled."""

    db = request.app.state.db
    base = request.app.state.config.alerting.notifiers
    return JSONResponse(await notifier_settings.effective_notifiers(db, base))


@router.put("/notifiers")
async def put_notifiers(
    request: Request, body: Annotated[dict[str, Any], Body()]
) -> JSONResponse:
    """บันทึกค่า notifier; ตรวจว่าช่องที่เปิดต้องตั้งค่าจำเป็นให้ครบ."""

    db = request.app.state.db
    base = request.app.state.config.alerting.notifiers
    merged = await notifier_settings.merge_notifiers(db, body)
    checks = (
        ("webhook", bool((merged.get("webhook") or {}).get("url"))),
        (
            "telegram",
            bool(
                (merged.get("telegram") or {}).get("bot_token")
                and (merged.get("telegram") or {}).get("chat_id")
            ),
        ),
    )
    for channel, complete in checks:
        if (merged.get(channel) or {}).get("enabled") and not complete:
            raise HTTPException(
                status_code=400, detail=f"ช่อง {channel} เปิดอยู่แต่ค่ายังไม่ครบ"
            )
    await notifier_settings.save_merged(db, merged)
    return JSONResponse(await notifier_settings.effective_notifiers(db, base))


def _tg_error_detail(resp: httpx.Response) -> str:
    """ดึงข้อความ error จาก Telegram API (json description หรือ body)."""

    try:
        data = resp.json()
        return str(data.get("description") or data)
    except (ValueError, KeyError):
        return resp.text[:200]


@router.post("/notifiers/webhook/test")
async def test_webhook(body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
    """POST payload ตัวอย่างไป webhook url ที่ระบุ (ยังไม่บันทึก)."""

    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="ต้องระบุ url")
    sample: dict[str, Any] = {"event": "test", "message": "การทดสอบจาก monitor-server"}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json=sample)
        return JSONResponse(
            {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "detail": resp.text[:200],
            }
        )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"ok": False, "status": 0, "detail": f"เชื่อมต่อไม่ได้: {exc.__class__.__name__}"}
        )


@router.post("/notifiers/telegram/test")
async def test_telegram(body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
    """ตรวจ bot_token (getMe) แล้วส่งข้อความทดสอบไป chat_id."""

    token = (body.get("bot_token") or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="ต้องระบุ bot_token และ chat_id")
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            me = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if me.status_code != 200:
                return JSONResponse(
                    {"ok": False, "status": me.status_code, "detail": _tg_error_detail(me)}
                )
            sent = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "🧪 การทดสอบจาก monitor-server"},
            )
            if sent.status_code == 200:
                return JSONResponse(
                    {"ok": True, "status": 200, "detail": "ส่งข้อความทดสอบแล้ว"}
                )
            return JSONResponse(
                {"ok": False, "status": sent.status_code, "detail": _tg_error_detail(sent)}
            )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"ok": False, "status": 0, "detail": f"เชื่อมต่อไม่ได้: {exc.__class__.__name__}"}
        )


@router.post("/notifiers/telegram/chatid")
async def telegram_scan_chatid(body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
    """ดึง chat_id อัตโนมัติ (getUpdates) — ผู้ใช้ต้องเคยแชทกับบอทอย่างน้อย 1 ครั้ง."""

    token = (body.get("bot_token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="ต้องระบุ bot_token")
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": -1, "timeout": 1},
            )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"ok": False, "status": 0, "detail": f"เชื่อมต่อไม่ได้: {exc.__class__.__name__}"}
        )
    if resp.status_code != 200:
        return JSONResponse(
            {"ok": False, "status": resp.status_code, "detail": _tg_error_detail(resp)}
        )
    try:
        data = resp.json()
    except ValueError:
        return JSONResponse(
            {"ok": False, "status": resp.status_code, "detail": "คำตอบจาก Telegram ไม่ใช่ JSON"}
        )
    updates = data.get("result") or []
    if not updates:
        return JSONResponse(
            {
                "ok": False,
                "status": 200,
                "detail": "ยังไม่มี chat — แชทกับบอท (กด Start) ก่อน แล้วลองอีกครั้ง",
            }
        )
    upd = updates[-1]
    msg = upd.get("message") or upd.get("channel_post") or upd.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return JSONResponse(
            {"ok": False, "status": 200, "detail": "หา chat_id ไม่เจอใน update ล่าสุด"}
        )
    return JSONResponse({"ok": True, "status": 200, "chat_id": str(chat_id)})
