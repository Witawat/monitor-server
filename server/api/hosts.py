"""Router สำหรับ hosts — list/detail/delete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from server.api.deps import require_admin
from server.storage.db import Database

router = APIRouter(
    prefix="/api/v1/hosts", tags=["hosts"], dependencies=[Depends(require_admin)]
)


@router.get("")
async def list_hosts(
    request: Request,
    online: Annotated[bool | None, Query()] = None,
) -> JSONResponse:
    """คืนรายชื่อ host + สถานะ online/offline + summary ล่าสุด."""

    db: Database = request.app.state.db
    timeout = request.app.state.config.ingest.offline_timeout_sec
    hosts = await db.list_hosts(online_only=bool(online), timeout_sec=timeout)
    return JSONResponse(hosts)


@router.get("/{host_id}")
async def get_host(request: Request, host_id: str) -> JSONResponse:
    """คืน detail host เดียว + snapshot ล่าสุด; 404 ถ้าไม่พบ."""

    db: Database = request.app.state.db
    timeout = request.app.state.config.ingest.offline_timeout_sec
    host = await db.get_host(host_id, timeout_sec=timeout)
    if host is None:
        return JSONResponse({"detail": "ไม่พบ host"}, status_code=404)
    return JSONResponse(host)


@router.delete("/{host_id}")
async def delete_host(request: Request, host_id: str) -> JSONResponse:
    """ลบ host + metrics + revoke token; 404 ถ้าไม่พบ."""

    db: Database = request.app.state.db
    deleted = await db.delete_host(host_id)
    if not deleted:
        return JSONResponse({"detail": "ไม่พบ host"}, status_code=404)
    return JSONResponse({"status": "ok", "deleted": host_id})
