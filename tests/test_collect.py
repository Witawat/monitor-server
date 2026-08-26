"""ทดสอบ agent/collect.py — pure parsers + snapshot ผ่าน provider."""

from __future__ import annotations

import platform

from agent.collect import (
    check_ports,
    host_id,
    parse_meminfo,
    parse_net_dev,
    parse_uptime,
    snapshot,
)
from agent.config import _parse_ports
from shared.metric import (
    DiskSample,
    MemorySample,
    NetSample,
    PortSample,
    ServiceSample,
    Snapshot,
    SwapSample,
)


class _FakeProvider:
    """Provider จำลองสำหรับ snapshot — กำหนดค่าคงที่."""

    def cpu_percent(self) -> float:
        return 12.5

    def load(self) -> list[float]:
        return [0.5, 0.4, 0.3]

    def memory(self) -> tuple[int, int, float]:
        return (1000, 400, 40.0)

    def swap(self) -> tuple[int, int]:
        return (200, 50)

    def disk(self) -> list[DiskSample]:
        return [DiskSample(mount="/", total=100, used=50, percent=50.0)]

    def net(self) -> list[NetSample]:
        return [NetSample(iface="eth0", rx_bytes=1000, tx_bytes=500)]

    def uptime(self) -> int:
        return 86400

    def procs(self) -> int:
        return 42

    def services(self, names):
        return [ServiceSample(name=n, up=(n == "nginx")) for n in names]

    def ports(self, ports):
        return [PortSample(port=p, name=n, up=False) for p, n in ports]


def test_parse_meminfo():
    """แยก MemTotal/MemAvailable จาก /proc/meminfo."""

    text = "MemTotal:       1000 kB\nMemFree:        100 kB\nMemAvailable:   250 kB\n"
    total, avail = parse_meminfo(text)
    assert total == 1000 * 1024
    assert avail == 250 * 1024


def test_parse_uptime():
    """แยก uptime วินาที."""

    assert parse_uptime("86400.5 123.4") == 86400


def test_parse_net_dev():
    """แยก NetSample จาก /proc/net/dev."""

    text = "Inter-|   Receive\n eth0: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0\n"
    samples = parse_net_dev(text)
    assert len(samples) == 1
    assert samples[0].iface == "eth0"
    assert samples[0].rx_bytes == 100
    assert samples[0].tx_bytes == 200


def test_snapshot_uses_provider():
    """snapshot() สร้างค่าจาก provider ที่ส่งเข้าไป."""

    snap = snapshot("h1", provider=_FakeProvider(), watch=["nginx", "mysql"], ports=[(80, "web"), (443, "https")])
    assert isinstance(snap, Snapshot)
    assert snap.host_id == "h1"
    assert snap.cpu_percent == 12.5
    assert snap.memory == MemorySample(total=1000, used=400, percent=40.0)
    assert snap.swap == SwapSample(total=200, used=50)
    assert snap.disk[0].mount == "/"
    assert snap.net[0].rx_bytes == 1000
    assert snap.uptime == 86400
    assert snap.procs == 42
    assert snap.platform == platform.system().lower()
    assert snap.services == [ServiceSample(name="nginx", up=True), ServiceSample(name="mysql", up=False)]
    assert snap.ports == [PortSample(port=80, name="web", up=False), PortSample(port=443, name="https", up=False)]


def test_parse_ports():
    """แปลงสตริง '80:web,443:https,22' → ((80,'web'),(443,'https'),(22,''))."""

    assert _parse_ports("80:web,443:https,22") == ((80, "web"), (443, "https"), (22, ""))
    assert _parse_ports("") == ()
    assert _parse_ports("abc, 8080") == ((8080, ""),)  # ข้ามค่าที่ไม่ใช่ตัวเลข


def test_check_ports(monkeypatch):
    """check_ports แปลงผล connect_ex เป็น PortSample.up."""


    class _FakeSock:
        def __init__(self, *a): pass
        def settimeout(self, t): pass
        def connect_ex(self, addr) -> int:
            return 0 if addr[1] == 80 else 1  # port 80 เปิด, 443 ปิด
        def close(self): pass

    monkeypatch.setattr("socket.socket", lambda *a: _FakeSock())
    samples = check_ports([(80, "web"), (443, "https")])
    assert samples[0] == PortSample(port=80, name="web", up=True)
    assert samples[1] == PortSample(port=443, name="https", up=False)


def test_host_id_persistent(tmp_path):
    """host_id อ่านค่าซ้ำจาก state_file เดิม."""

    state = tmp_path / "host_id"
    first = host_id(state)
    second = host_id(state)
    assert first == second
    assert len(first) == 36
