"""Router สำหรับ metrics — GET /api/v1/hosts/{id}/metrics + export CSV."""

from __future__ import annotations

import csv
import io
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from server.api.deps import require_admin
from server.storage.db import METRIC_COLUMNS, Database

router = APIRouter(
    prefix="/api/v1/hosts", tags=["metrics"], dependencies=[Depends(require_admin)]
)

_RANGE_SEC: dict[str, int] = {"1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800}
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

_EXPORT_METRICS = [
    "cpu_percent",
    "memory.percent",
    "memory.used",
    "memory.total",
    "load1",
    "load5",
    "load15",
    "uptime",
    "procs",
]


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


@router.get("/{host_id}/export")
async def export_csv(request: Request, host_id: str, range: Annotated[str, Query()] = "1d") -> Response:
    """export metrics เป็น CSV (range 1h/6h/1d/7d)."""

    db: Database = request.app.state.db
    if range not in _RANGE_SEC:
        return JSONResponse({"detail": f"range ไม่รองรับ: {range}"}, status_code=400)

    rows = await db.export_rows(host_id, _RANGE_SEC[range], _EXPORT_METRICS)
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers = ["ts"] + _EXPORT_METRICS
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r["ts"]] + [r.get(METRIC_COLUMNS[m], "") for m in _EXPORT_METRICS])

    filename = f"{_SAFE_FILENAME.sub('_', host_id) or 'host'}_{range}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
