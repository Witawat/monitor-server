"""Router alerts — CRUD rules + history + ack."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from server.api.deps import require_admin
from server.storage.db import Database

router = APIRouter(
    prefix="/api/v1/alerts", tags=["alerts"], dependencies=[Depends(require_admin)]
)

_ALLOWED_OPS = {">", ">=", "<", "<=", "=="}


def _validate_rule(data: dict[str, Any]) -> None:
    """ตรวจ rule ว่ามี field จำเป็น + op ถูกต้อง."""

    if not (data.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="ต้องระบุ name")
    if not (data.get("metric") or "").strip():
        raise HTTPException(status_code=400, detail="ต้องระบุ metric")
    if data.get("op") not in _ALLOWED_OPS:
        raise HTTPException(status_code=400, detail=f"op ต้องเป็น {sorted(_ALLOWED_OPS)}")
    threshold = data.get("threshold")
    if threshold is None:
        raise HTTPException(status_code=400, detail="ต้องระบุ threshold")
    try:
        float(threshold)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="threshold ต้องเป็นตัวเลข") from None


@router.get("")
async def list_rules(request: Request) -> JSONResponse:
    """คืนรายการ alert rules."""

    db: Database = request.app.state.db
    return JSONResponse(await db.list_rules())


@router.post("")
async def create_rule(request: Request, body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
    """สร้าง rule ใหม่."""

    _validate_rule(body)
    db: Database = request.app.state.db
    rule_id = await db.create_rule(body)
    return JSONResponse({"id": rule_id}, status_code=201)


@router.put("/{rule_id}")
async def update_rule(request: Request, rule_id: int, body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
    """แก้ rule; 404 ถ้าไม่พบ."""

    if not await _ensure_rule(request, rule_id):
        return JSONResponse({"detail": "ไม่พบ rule"}, status_code=404)
    _validate_rule(body)
    db: Database = request.app.state.db
    await db.update_rule(rule_id, body)
    return JSONResponse({"ok": True, "id": rule_id})


@router.delete("/{rule_id}")
async def delete_rule(request: Request, rule_id: int) -> JSONResponse:
    """ลบ rule; 404 ถ้าไม่พบ."""

    db: Database = request.app.state.db
    if not await db.delete_rule(rule_id):
        return JSONResponse({"detail": "ไม่พบ rule"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/history")
async def list_history(
    request: Request,
    host_id: str | None = None,
    rule_id: int | None = None,
    ack: bool | None = None,
) -> JSONResponse:
    """คืนประวัติ alert trigger (filter host/rule/ack)."""

    db: Database = request.app.state.db
    return JSONResponse(await db.list_history(host_id=host_id, rule_id=rule_id, ack=ack))


@router.post("/history/{history_id}/ack")
async def ack_history(request: Request, history_id: int) -> JSONResponse:
    """ack ประวัติ; 404 ถ้าไม่พบ."""

    db: Database = request.app.state.db
    if not await db.ack_history(history_id):
        return JSONResponse({"detail": "ไม่พบประวัติ"}, status_code=404)
    return JSONResponse({"ok": True})


async def _ensure_rule(request: Request, rule_id: int) -> bool:
    """เช็คว่า rule มีอยู่จริงไหม (helper)."""

    db: Database = request.app.state.db
    return await db.get_rule(rule_id) is not None
