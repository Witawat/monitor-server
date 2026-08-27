"""Router สำหรับรับ push จาก agent — POST /api/v1/ingest."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.api.deps import client_ip
from server.ingest import IngestError, IngestService
from server.streaming import EVENT_ALERTS, EVENT_HOSTS
from shared.metric import HEADER_TOKEN

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/ingest")
async def ingest(request: Request, body: list[dict[str, Any]]) -> JSONResponse:
    """รับ batch snapshot จาก agent แล้วเขียนลง SQLite.

    Raises:
        HTTPException: 401 token ผิด / 429 rate limit / 400 schema ไม่ตรง.
    """
    service: IngestService = request.app.state.ingest
    token = request.headers.get(HEADER_TOKEN, "")
    ip = client_ip(request)
    try:
        received, host_id, remote_cfg = await service.process_batch(token, ip, body)
    except IngestError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)
    # มี snapshot ใหม่ → fleet/host data เปลี่ยน; alert อาจ fire → push ทั้ง 2 ให้ client refresh
    hub = getattr(request.app.state, "stream", None)
    if hub is not None:
        hub.broadcast(EVENT_HOSTS)
        hub.broadcast(EVENT_ALERTS)
    return JSONResponse({
        "status": "ok", "received": received, "host_id": host_id,
        "config": remote_cfg,   # คืน remote config ให้ agent pull/apply (ถ้ามี)
    })
