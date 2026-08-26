"""Router สำหรับ metrics — GET /api/v1/hosts/{id}/metrics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from server.api.deps import require_admin
from server.storage.db import Database

router = APIRouter(
    prefix="/api/v1/hosts", tags=["metrics"], dependencies=[Depends(require_admin)]
)

_RANGE_SEC: dict[str, int] = {"1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800}


@router.get("/{host_id}/metrics")
async def get_metrics(
    request: Request,
    host_id: str,
    range: Annotated[str, Query()] = "1h",
    metrics: Annotated[str, Query()] = "",
) -> JSONResponse:
    """คืน time-series ต่อ metric ภายใน range (rollup อัตโนมัติเมื่อช่วงกว้าง)."""

    db: Database = request.app.state.db
    if range not in _RANGE_SEC:
        return JSONResponse({"detail": f"range ไม่รองรับ: {range}"}, status_code=400)

    names = [m.strip() for m in metrics.split(",") if m.strip()]
    if not names:
        names = ["cpu_percent", "memory.percent", "load1", "load5", "load15", "uptime"]
    series = await db.get_metrics(host_id, _RANGE_SEC[range], names)
    return JSONResponse({"host_id": host_id, "range": range, "series": series})
