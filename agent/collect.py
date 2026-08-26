"""เก็บ metrics ของ host (stdlib เท่านั้น, psutil เป็น optional)."""

from __future__ import annotations

import os
import platform
import time
import uuid
from pathlib import Path
from typing import Protocol

from shared.metric import DiskSample, MemorySample, NetSample, ServiceSample, Snapshot, SwapSample

try:  # psutil เป็น optional — fallback stdlib ถ้าไม่มี
    import psutil  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - ขึ้นกับสภาพแวดล้อม
    psutil = None

# ── host id ──

def host_id(state_file: str | Path) -> str:
    """อ่าน/สร้าง uuid ของ host นี้ให้คงที่ (เก็บใน state_file)."""

    path = Path(state_file)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return value


# ── pure parsers (เทสต์ง่าย, แยกจาก platform) ──

def parse_meminfo(text: str) -> tuple[int, int]:
    """แยก (total, available) bytes จาก /proc/meminfo."""

    from contextlib import suppress

    values: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) == 2:
            kb = parts[1].strip().split()[0]
            with suppress(ValueError):
                values[parts[0]] = int(kb) * 1024
    return values.get("MemTotal", 0), values.get("MemAvailable", values.get("MemFree", 0))


def parse_uptime(text: str) -> int:
    """แยก uptime วินาทีจาก /proc/uptime (เลขแรก)."""

    try:
        return int(float(text.split()[0]))
    except (IndexError, ValueError):
        return 0


def parse_net_dev(text: str) -> list[NetSample]:
    """แยก NetSample จาก /proc/net/dev (cumulative counters)."""

    samples: list[NetSample] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        iface, rest = line.split(":", 1)
        fields = rest.split()
        if len(fields) < 9:
            continue
        samples.append(NetSample(iface=iface.strip(), rx_bytes=int(fields[0]), tx_bytes=int(fields[8])))
    return samples


# ── providers ──

class SysInfoProvider(Protocol):
    """Interface ของแหล่งข้อมูล system metrics (psutil / stdlib fallback)."""

    def cpu_percent(self) -> float: ...
    def load(self) -> list[float]: ...
    def memory(self) -> tuple[int, int, float]: ...
    def swap(self) -> tuple[int, int]: ...
    def disk(self) -> list[DiskSample]: ...
    def net(self) -> list[NetSample]: ...
    def uptime(self) -> int: ...
    def procs(self) -> int: ...
    def services(self, names: list[str]) -> list[ServiceSample]: ...


class _PsutilProvider:
    """เก็บ metrics ผ่าน psutil (ถ้ามี)."""

    def cpu_percent(self) -> float:
        return float(psutil.cpu_percent(interval=0))

    def load(self) -> list[float]:
        if hasattr(os, "getloadavg"):
            return [round(v, 2) for v in os.getloadavg()]
        return [0.0, 0.0, 0.0]

    def memory(self) -> tuple[int, int, float]:
        vm = psutil.virtual_memory()
        return vm.total, vm.used, vm.percent

    def swap(self) -> tuple[int, int]:
        sw = psutil.swap_memory()
        return sw.total, sw.used

    def disk(self) -> list[DiskSample]:
        samples: list[DiskSample] = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            samples.append(
                DiskSample(
                    mount=part.mountpoint,
                    total=usage.total,
                    used=usage.used,
                    percent=usage.percent,
                )
            )
        return samples

    def net(self) -> list[NetSample]:
        return [
            NetSample(iface=k, rx_bytes=v.bytes_recv, tx_bytes=v.bytes_sent)
            for k, v in psutil.net_io_counters(pernic=True).items()
        ]

    def uptime(self) -> int:
        return int(time.time() - psutil.boot_time())

    def procs(self) -> int:
        return len(psutil.pids())

    def services(self, names: list[str]) -> list[ServiceSample]:
        running = {p.info["name"] for p in psutil.process_iter(["name"])}
        lowered = {n.lower() for n in running if n}
        return [
            ServiceSample(name=n, up=n.lower() in lowered)
            for n in names
        ]


class _StdlibProvider:
    """เก็บ metrics ด้วย stdlib (Linux อ่าน /proc, Windows ใช้ ctypes)."""

    def cpu_percent(self) -> float:
        # stdlib ไม่มี cpu% ตรงๆ ง่ายๆ — คืน 0 (ดู load แทน)
        return 0.0

    def load(self) -> list[float]:
        if hasattr(os, "getloadavg"):
            return [round(v, 2) for v in os.getloadavg()]
        return [0.0, 0.0, 0.0]

    def memory(self) -> tuple[int, int, float]:
        if platform.system() == "Linux":
            try:
                total, avail = parse_meminfo(Path("/proc/meminfo").read_text(encoding="utf-8"))
                used = total - avail
                percent = used / total * 100 if total else 0.0
                return total, used, round(percent, 1)
            except OSError:
                pass
        elif platform.system() == "Windows":
            win_mem = self._windows_memory()
            if win_mem:
                return win_mem
        return 0, 0, 0.0

    @staticmethod
    def _windows_memory() -> tuple[int, int, float] | None:
        """อ่าน RAM ด้วย ctypes GlobalMemoryStatusEx (Windows stdlib)."""

        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = int(status.ullTotalPhys)
            avail = int(status.ullAvailPhys)
            used = total - avail
            percent = used / total * 100 if total else 0.0
            return total, used, round(percent, 1)
        return None

    def swap(self) -> tuple[int, int]:
        return 0, 0

    def disk(self) -> list[DiskSample]:
        if platform.system() != "Linux":
            return []
        samples: list[DiskSample] = []
        try:
            for line in Path("/proc/self/mounts").read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) < 3 or not parts[2].startswith(("ext", "xfs", "btrfs", "zfs", "vfat", "ntfs")):
                    continue
                mount = parts[1].replace("\\040", " ")
                try:
                    stat = os.statvfs(mount)  # type: ignore[attr-defined]
                except OSError:
                    continue
                total = stat.f_frsize * stat.f_blocks
                used = (stat.f_blocks - stat.f_bavail) * stat.f_frsize
                percent = used / total * 100 if total else 0.0
                samples.append(DiskSample(mount=mount, total=total, used=used, percent=round(percent, 1)))
        except OSError:
            pass
        return samples

    def net(self) -> list[NetSample]:
        if platform.system() == "Linux":
            try:
                return parse_net_dev(Path("/proc/net/dev").read_text(encoding="utf-8"))
            except OSError:
                pass
        return []

    def uptime(self) -> int:
        if platform.system() == "Linux":
            try:
                return parse_uptime(Path("/proc/uptime").read_text(encoding="utf-8"))
            except OSError:
                pass
        elif platform.system() == "Windows":
            try:
                import ctypes

                return int(ctypes.windll.kernel32.GetTickCount64() // 1000)
            except (ImportError, AttributeError):
                pass
        return 0

    def procs(self) -> int:
        if platform.system() == "Linux":
            try:
                return len(list(Path("/proc").iterdir()))
            except OSError:
                pass
        return 0

    def services(self, names: list[str]) -> list[ServiceSample]:
        # stdlib ไม่มีวิธีระบุ process ได้ครบทุกแพลตฟอร์ม — คืน not-up เพื่อความชัดเจน
        return [ServiceSample(name=n, up=False) for n in names]


def _make_provider() -> SysInfoProvider:
    """เลือก provider ตามว่า import psutil ได้หรือไม่."""

    return _PsutilProvider() if psutil is not None else _StdlibProvider()


def snapshot(
    host_id: str, provider: SysInfoProvider | None = None, watch: list[str] | tuple[str, ...] = ()
) -> Snapshot:
    """สร้าง Snapshot ปัจจุบันของ host (ใช้ provider ที่ระบุ หรือ auto-select)."""

    prov = provider or _make_provider()
    total, used, percent = prov.memory()
    swap_total, swap_used = prov.swap()
    return Snapshot(
        host_id=host_id,
        hostname=platform.node(),
        platform=platform.system().lower(),
        ts=int(time.time()),
        cpu_percent=prov.cpu_percent(),
        load=prov.load(),
        memory=MemorySample(total=total, used=used, percent=percent),
        swap=SwapSample(total=swap_total, used=swap_used),
        disk=prov.disk(),
        net=prov.net(),
        services=prov.services(list(watch)),
        uptime=prov.uptime(),
        procs=prov.procs(),
    )
