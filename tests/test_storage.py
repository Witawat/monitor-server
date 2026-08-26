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
