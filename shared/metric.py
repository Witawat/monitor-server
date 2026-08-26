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
class PortSample:
    """สถานะเปิด/ปิดของหนึ่ง TCP port ที่ agent เฝ้าดู (ตาม config ports)."""

    port: int = 0
    name: str = ""
    up: bool = False  # True = port กำลัง listen


@dataclass
class DiskIOSample:
    """cumulative I/O counter ของหนึ่งอุปกรณ์ดิสก์ (server คำนวณ rate จาก delta)."""

    device: str = ""
    read_bytes: int = 0
    write_bytes: int = 0


@dataclass
class TopProcessSample:
    """หนึ่ง process ที่ใช้ CPU/หน่วยความจำสูง (สำหรับแสดงใน host view)."""

    pid: int = 0
    name: str = ""
    cpu_percent: float = 0.0
    mem_percent: float = 0.0


@dataclass
class NicSample:
    """สถานะของหนึ่ง network interface (up/down + ip + mac)."""

    iface: str = ""
    up: bool = False
    ip: str = ""
    mac: str = ""


@dataclass
class HostInfo:
    """ข้อมูลระบบของ host (OS/arch/kernel) — เปลี่ยนนาน ๆ ครั้ง."""

    os_name: str = ""
    os_version: str = ""
    arch: str = ""
    kernel: str = ""


@dataclass
class ProcessDetail:
    """สถิติ per process ของ service ที่ agent เฝ้าดู (watch)."""

    name: str = ""
    pid: int = 0
    cpu_percent: float = 0.0
    mem_percent: float = 0.0


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
    ports: list[PortSample] = field(default_factory=list)
    uptime: int = 0
    procs: int = 0
    disk_io: list[DiskIOSample] = field(default_factory=list)
    top_process: list[TopProcessSample] = field(default_factory=list)
    host_info: HostInfo = field(default_factory=HostInfo)
    cpu_cores: int = 0
    nic_status: list[NicSample] = field(default_factory=list)
    process_detail: list[ProcessDetail] = field(default_factory=list)


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
    hi = data.get("host_info") or {}
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
        ports=[
            PortSample(
                port=_as_int(p.get("port")),
                name=str(p.get("name", "")),
                up=bool(p.get("up", False)),
            )
            for p in (data.get("ports") or [])
        ],
        uptime=_as_int(data.get("uptime")),
        procs=_as_int(data.get("procs")),
        disk_io=[
            DiskIOSample(
                device=str(x.get("device", "")),
                read_bytes=_as_int(x.get("read_bytes")),
                write_bytes=_as_int(x.get("write_bytes")),
            )
            for x in (data.get("disk_io") or [])
        ],
        top_process=[
            TopProcessSample(
                pid=_as_int(x.get("pid")),
                name=str(x.get("name", "")),
                cpu_percent=_as_float(x.get("cpu_percent")),
                mem_percent=_as_float(x.get("mem_percent")),
            )
            for x in (data.get("top_process") or [])
        ],
        host_info=HostInfo(
            os_name=str(hi.get("os_name", "")),
            os_version=str(hi.get("os_version", "")),
            arch=str(hi.get("arch", "")),
            kernel=str(hi.get("kernel", "")),
        ),
        cpu_cores=_as_int(data.get("cpu_cores")),
        nic_status=[
            NicSample(
                iface=str(x.get("iface", "")),
                up=bool(x.get("up", False)),
                ip=str(x.get("ip", "")),
                mac=str(x.get("mac", "")),
            )
            for x in (data.get("nic_status") or [])
        ],
        process_detail=[
            ProcessDetail(
                name=str(x.get("name", "")),
                pid=_as_int(x.get("pid")),
                cpu_percent=_as_float(x.get("cpu_percent")),
                mem_percent=_as_float(x.get("mem_percent")),
            )
            for x in (data.get("process_detail") or [])
        ],
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
        "ports": [{"port": p.port, "name": p.name, "up": p.up} for p in snap.ports],
        "uptime": snap.uptime,
        "procs": snap.procs,
        "disk_io": [
            {"device": d.device, "read_bytes": d.read_bytes, "write_bytes": d.write_bytes}
            for d in snap.disk_io
        ],
        "top_process": [
            {"pid": p.pid, "name": p.name, "cpu_percent": p.cpu_percent, "mem_percent": p.mem_percent}
            for p in snap.top_process
        ],
        "host_info": {
            "os_name": snap.host_info.os_name,
            "os_version": snap.host_info.os_version,
            "arch": snap.host_info.arch,
            "kernel": snap.host_info.kernel,
        },
        "cpu_cores": snap.cpu_cores,
        "nic_status": [
            {"iface": n.iface, "up": n.up, "ip": n.ip, "mac": n.mac}
            for n in snap.nic_status
        ],
        "process_detail": [
            {"name": p.name, "pid": p.pid, "cpu_percent": p.cpu_percent, "mem_percent": p.mem_percent}
            for p in snap.process_detail
        ],
    }
