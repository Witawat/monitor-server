"""Schema metric + ingest contract ที่ server กับ agent ใช้ร่วมกัน.

บางพอให้ agent (stdlib เท่านั้น) import ได้ — ใช้ dataclasses ล้วน ไม่พึ่ง pydantic.
Server ใช้ validate ฝั่งรับ push; agent ใช้สร้าง snapshot ตอน collect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── ingest contract ──

INGEST_PATH = "/api/v1/ingest"      # endpoint ที่ agent push batch
HEADER_TOKEN = "X-Agent-Token"      # header ระบุตัวตน host
MAX_BATCH_SIZE = 100                # snapshot สูงสุดต่อ request (ค่าเริ่มต้น)

PLATFORMS = ("linux", "windows")    # platform ที่รองรับ


# ── schema (dataclass) ──

@dataclass
class MemorySample:
    """สถิติหน่วยความจำ RAM ของ host."""

    total: int = 0
    used: int = 0
    percent: float = 0.0


@dataclass
class SwapSample:
    """สถิติ swap ของ host."""

    total: int = 0
    used: int = 0


@dataclass
class DiskSample:
    """สถิติของหนึ่ง mount/filesystem."""

    mount: str = ""
    total: int = 0
    used: int = 0
    percent: float = 0.0


@dataclass
class NetSample:
    """สถิติ cumulative counter ของหนึ่ง network interface.

    Notes:
        rx_bytes/tx_bytes เป็น cumulative counter — server คำนวณ rate (bytes/s)
        จาก delta ของสองจุดเอง.
    """

    iface: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0


@dataclass
class ServiceSample:
    """สถานะ up/down ของหนึ่ง service/process ที่ agent เฝ้าดู."""

    name: str = ""
    up: bool = False


@dataclass
class Snapshot:
    """หนึ่งจุดข้อมูล metric ของ host ณ เวลา ts (วินาที epoch)."""

    host_id: str
    hostname: str
    platform: str
    ts: int
    cpu_percent: float = 0.0
    load: list[float] = field(default_factory=list)
    memory: MemorySample = field(default_factory=MemorySample)
    swap: SwapSample = field(default_factory=SwapSample)
    disk: list[DiskSample] = field(default_factory=list)
    net: list[NetSample] = field(default_factory=list)
    services: list[ServiceSample] = field(default_factory=list)
    uptime: int = 0
    procs: int = 0


# ── helpers ──

def _as_int(value: Any, default: int = 0) -> int:
    """แปลงค่าเป็น int; คืน default ถ้าแปลงไม่ได้ (ป้องกันค่าขยะจาก agent)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    """แปลงค่าเป็น float; คืน default ถ้าแปลงไม่ได้."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def snapshot_from_dict(data: dict[str, Any]) -> Snapshot:
    """สร้าง Snapshot จาก dict ฝั่ง server โดยกัน field ขาด/ค่าผิดโดยไม่พัง.

    Notes:
        ทำ validation แบบ lenient ที่นี่ — ฝั่ง server ยังตรวจ host_id/platform
        ซ้ำอีกชั้นใน ingest ก่อนเขียนลง DB.
    """
    mem = data.get("memory") or {}
    swap = data.get("swap") or {}
    return Snapshot(
        host_id=str(data.get("host_id", "")),
        hostname=str(data.get("hostname", "")),
        platform=str(data.get("platform", "")),
        ts=_as_int(data.get("ts")),
        cpu_percent=_as_float(data.get("cpu_percent")),
        load=[_as_float(x) for x in (data.get("load") or [])],
        memory=MemorySample(
            total=_as_int(mem.get("total")),
            used=_as_int(mem.get("used")),
            percent=_as_float(mem.get("percent")),
        ),
        swap=SwapSample(
            total=_as_int(swap.get("total")),
            used=_as_int(swap.get("used")),
        ),
        disk=[
            DiskSample(
                mount=str(d.get("mount", "")),
                total=_as_int(d.get("total")),
                used=_as_int(d.get("used")),
                percent=_as_float(d.get("percent")),
            )
            for d in (data.get("disk") or [])
        ],
        net=[
            NetSample(
                iface=str(n.get("iface", "")),
                rx_bytes=_as_int(n.get("rx_bytes")),
                tx_bytes=_as_int(n.get("tx_bytes")),
            )
            for n in (data.get("net") or [])
        ],
        services=[
            ServiceSample(
                name=str(s.get("name", "")),
                up=bool(s.get("up", False)),
            )
            for s in (data.get("services") or [])
        ],
        uptime=_as_int(data.get("uptime")),
        procs=_as_int(data.get("procs")),
    )


def snapshot_to_dict(snap: Snapshot) -> dict[str, Any]:
    """แปลง Snapshot เป็น dict สำหรับ serialize เป็น JSON ก่อน push."""

    return {
        "host_id": snap.host_id,
        "hostname": snap.hostname,
        "platform": snap.platform,
        "ts": snap.ts,
        "cpu_percent": snap.cpu_percent,
        "load": list(snap.load),
        "memory": {"total": snap.memory.total, "used": snap.memory.used, "percent": snap.memory.percent},
        "swap": {"total": snap.swap.total, "used": snap.swap.used},
        "disk": [
            {"mount": d.mount, "total": d.total, "used": d.used, "percent": d.percent}
            for d in snap.disk
        ],
        "net": [
            {"iface": n.iface, "rx_bytes": n.rx_bytes, "tx_bytes": n.tx_bytes}
            for n in snap.net
        ],
        "services": [{"name": s.name, "up": s.up} for s in snap.services],
        "uptime": snap.uptime,
        "procs": snap.procs,
    }
