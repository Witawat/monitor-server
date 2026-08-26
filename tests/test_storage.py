"""ทดสอบ server/storage/db.py — upsert host + insert snapshot + query."""

from __future__ import annotations

import time

import pytest

from server.storage.db import Database
from shared.metric import Snapshot, snapshot_from_dict


@pytest.fixture
async def db(tmp_path):
    """Database ชี้ไฟล์ temp + เปิด connection."""

    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


def _snap(ts: int, cpu: float = 10.0) -> Snapshot:
    """สร้าง Snapshot แบบเต็มพร้อม disk/net อย่างละตัว."""

    return snapshot_from_dict(
        {
            "host_id": "h1",
            "hostname": "web-01",
            "platform": "linux",
            "ts": ts,
            "cpu_percent": cpu,
            "load": [0.5, 0.4, 0.3],
            "memory": {"total": 1000, "used": 400, "percent": 40.0},
            "disk": [{"mount": "/", "total": 100, "used": 50, "percent": 50.0}],
            "net": [{"iface": "eth0", "rx_bytes": 1000, "tx_bytes": 500}],
            "ports": [{"port": 80, "name": "web", "up": True}, {"port": 443, "name": "https", "up": False}],
            "uptime": 3600,
            "procs": 42,
        }
    )


async def test_upsert_and_list_host(db):
    """upsert_host 2 ครั้ง → host เดียวกัน มี last_seen ล่าสุด."""

    await db.upsert_host("h1", "web-01", "linux", "tok", now=100)
    await db.upsert_host("h1", "web-01", "linux", "tok", now=200)
    hosts = await db.list_hosts(timeout_sec=60)
    assert len(hosts) == 1
    assert hosts[0]["host_id"] == "h1"
    assert hosts[0]["last_seen"] == 200


async def test_host_by_token(db):
    """ค้น host ด้วย token."""

    await db.upsert_host("h1", "web-01", "linux", "secret", now=100)
    found = await db.host_by_token("secret")
    assert found is not None and found["host_id"] == "h1"
    assert await db.host_by_token("wrong") is None


async def test_insert_batch_and_metrics(db):
    """insert batch → get_metrics คืน series ถูกต้อง."""

    now = int(time.time())
    await db.upsert_host("h1", "web-01", "linux", "tok", now=now)
    await db.insert_batch([_snap(now, 20.0), _snap(now + 1, 30.0)])
    series = await db.get_metrics("h1", 3600, ["cpu_percent", "memory.percent"])
    assert series["cpu_percent"]["unit"] == "%"
    assert [p[1] for p in series["cpu_percent"]["points"]] == [20.0, 30.0]
    assert [p[1] for p in series["memory.percent"]["points"]] == [40.0, 40.0]


async def test_get_metrics_empty(db):
    """ไม่มีข้อมูล → series ว่าง."""

    series = await db.get_metrics("h1", 3600, ["cpu_percent"])
    assert series["cpu_percent"]["points"] == []


async def test_latest_summary(db):
    """summary ล่าสุดดึงจาก snapshot ตัวล่าสุด."""

    now = int(time.time())
    await db.upsert_host("h1", "web-01", "linux", "tok", now=now)
    await db.insert_batch([_snap(now - 60, 10.0), _snap(now, 55.0)])
    hosts = await db.list_hosts(timeout_sec=3600)
    assert hosts[0]["summary"]["cpu_percent"] == 55.0


async def test_summary_includes_chunk_b(db):
    """summary คืน field เพิ่ม (Chunk B): cpu_cores/host_info/top_process/nic/process_detail/disk_io_rate."""

    now = int(time.time())

    def snap(ts: int, rd: int, wr: int) -> Snapshot:
        return snapshot_from_dict(
            {
                "host_id": "h1",
                "hostname": "web-01",
                "platform": "linux",
                "ts": ts,
                "cpu_percent": 10.0,
                "cpu_cores": 8,
                "host_info": {"os_name": "Linux", "os_version": "1", "arch": "x86_64", "kernel": "6.1"},
                "top_process": [{"pid": 1, "name": "init", "cpu_percent": 1.0, "mem_percent": 2.0}],
                "nic_status": [{"iface": "eth0", "up": True, "ip": "10.0.0.1", "mac": "aa:bb"}],
                "process_detail": [{"name": "nginx", "pid": 10, "cpu_percent": 1.0, "mem_percent": 2.0}],
                "disk_io": [{"device": "sda", "read_bytes": rd, "write_bytes": wr}],
            }
        )

    await db.upsert_host("h1", "web-01", "linux", "tok", now=now)
    await db.insert_batch([snap(now - 10, 1000, 500), snap(now, 2000, 1000)])
    s = await db._latest_summary("h1")
    assert s["cpu_cores"] == 8
    assert s["host_info"]["os_name"] == "Linux"
    assert s["top_process"][0]["name"] == "init"
    assert s["nic_status"][0]["iface"] == "eth0"
    assert s["process_detail"][0]["name"] == "nginx"
    assert s["disk_io_rate"]["read_bps"] > 0
    assert s["disk_io_rate"]["write_bps"] > 0


async def test_delete_host(db):
    """ลบ host + data ทั้งหมด."""

    await db.upsert_host("h1", "web-01", "linux", "tok", now=100)
    await db.insert_batch([_snap(1000)])
    assert await db.delete_host("h1") is True


async def test_latest_ports(db):
    """latest_ports คืนสถานะ port ของ snapshot ล่าสุด."""

    now = int(time.time())
    await db.upsert_host("h1", "web-01", "linux", "tok", now=now)
    await db.insert_batch([_snap(now, 20.0)])
    ports = await db.latest_ports("h1")
    assert len(ports) == 2
    assert any(p["port"] == 80 and p["up"] == 1 for p in ports)
    assert any(p["port"] == 443 and p["up"] == 0 for p in ports)
