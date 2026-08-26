"""ทดสอบงานเสริม — tags, services, export CSV, host-down notify, login rate-limit, security headers."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server.alerting.offline import HostDownMonitor
from server.config import AppConfig
from server.main import create_app
from server.storage.db import Database
from server.webui.auth import hash_password, sign_session
from shared.metric import ServiceSample, Snapshot

# ── fixtures ──


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "extra.db")
    await database.connect()
    yield database
    await database.close()


def _client(tmp_path):
    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.webui.admin_pass_hash = hash_password("secretpw")
    return TestClient(create_app(cfg))


def _authed(c, tmp_path):
    c.app.state.config.webui.admin_pass_hash = hash_password("secretpw")
    c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})


def _ingest_batch(with_services: bool = False) -> list[dict]:
    now = int(time.time())
    item = {
        "host_id": "h1",
        "hostname": "web-01",
        "platform": "linux",
        "ts": now,
        "cpu_percent": 42.5,
        "memory": {"total": 1000, "used": 400, "percent": 40.0},
    }
    if with_services:
        item["services"] = [{"name": "nginx", "up": True}, {"name": "mysql", "up": False}]
    return [item]


# ── feature 1: tags ──

def test_tags_set_and_filter(tmp_path):
    """ตั้ง tags → list_hosts มี tags + /hosts/tags คืนค่าที่ใช้."""

    with _client(tmp_path) as c:
        _authed(c, tmp_path)
        c.post("/api/v1/ingest", json=_ingest_batch(), headers={"X-Agent-Token": "tok"})
        r = c.put("/api/v1/hosts/h1/tags", json={"tags": ["env=prod", "th"]})
        assert r.status_code == 200
        assert c.get("/api/v1/hosts").json()[0]["tags"] == ["env=prod", "th"]
        assert c.get("/api/v1/hosts/tags").json() == ["env=prod", "th"]


def test_tags_bad_input_400(tmp_path):
    """tags ผิดรูปแบบ → 400."""

    with _client(tmp_path) as c:
        _authed(c, tmp_path)
        r = c.put("/api/v1/hosts/h1/tags", json={"tags": "not-a-list"})
        assert r.status_code == 400


# ── feature 2: services ──

def test_ingest_services_stored(tmp_path):
    """agent ส่ง services → get_host คืนสถานะ up/down."""

    with _client(tmp_path) as c:
        _authed(c, tmp_path)
        c.post("/api/v1/ingest", json=_ingest_batch(with_services=True), headers={"X-Agent-Token": "tok"})
        host = c.get("/api/v1/hosts/h1").json()
        services = {s["name"]: s["up"] for s in host["services"]}
        assert services == {"nginx": True, "mysql": False}


# ── feature 3: export CSV ──

def test_export_csv(tmp_path):
    """export CSV คืนไฟล์ csv พร้อม header + แถวข้อมูล."""

    with _client(tmp_path) as c:
        _authed(c, tmp_path)
        c.post("/api/v1/ingest", json=_ingest_batch(), headers={"X-Agent-Token": "tok"})
        r = c.get("/api/v1/hosts/h1/export?range=1h")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "ts,cpu_percent" in r.text
        assert "42.5" in r.text


# ── feature 4: host-down notification ──

async def test_host_down_fires_notification(db):
    """host offline เกิน timeout (เคยมีข้อมูล) → บันทึก history + ส่ง notifier."""

    cfg = AppConfig()
    cfg.alerting.enabled = True
    cfg.ingest.offline_timeout_sec = 60
    old = int(time.time()) - 1000
    await db.upsert_host("gone-1", "gone", "linux", "tok", now=old)
    await db.insert_batch([Snapshot(host_id="gone-1", hostname="gone", platform="linux", ts=old)])
    fired: list[dict] = []

    class FakeNotifier:
        async def send(self, payload):
            fired.append(payload)

    monitor = HostDownMonitor(db, cfg, notifier=FakeNotifier())
    events = await monitor.check()
    assert len(events) == 1
    assert events[0]["metric"] == "host_down"
    assert len(fired) == 1
    assert await db.list_history() != []

    # ยิงซ้ำ (ยัง offline) → ไม่ยิงซ้ำ
    events2 = await monitor.check()
    assert events2 == []


# ── feature 5: rate-limit login + security headers ──

def test_login_rate_limited(tmp_path):
    """login ผิดเกินลิมิต → 429."""

    with _client(tmp_path) as c:
        for _ in range(10):
            c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429


def test_security_headers(tmp_path):
    """ทุก response มี CSP + security headers."""

    with _client(tmp_path) as c:
        r = c.get("/api/health")
        assert r.headers.get("content-security-policy", "").startswith("default-src 'self'")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"


# ── regression ครอบ bug audit ──

def test_token_takeover_rejected(tmp_path):
    """H2: host ที่มีอยู่แล้ว + token ใหม่ → ไม่อนุญาตแย่งชิง."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.webui.admin_pass_hash = hash_password("secretpw")
    with TestClient(create_app(cfg)) as c:
        c.cookies.set("session", sign_session(c.app.state.session_secret, "admin"))
        # ลงทะเบียน h1 ด้วย token A
        assert c.post("/api/v1/ingest", json=_ingest_batch(), headers={"X-Agent-Token": "tokA"}).status_code == 200
        # ลองแย่งด้วย token B → host มีอยู่แล้ว → 400
        r = c.post("/api/v1/ingest", json=_ingest_batch(), headers={"X-Agent-Token": "tokB"})
        assert r.status_code == 400
        # token เดิมยังใช้ได้
        assert c.post("/api/v1/ingest", json=_ingest_batch(), headers={"X-Agent-Token": "tokA"}).status_code == 200


async def test_delete_host_removes_services_and_history(db):
    """M3: delete_host ลบ service_samples + alert_history ด้วย."""

    await db.upsert_host("h1", "h1", "linux", "tok", now=100)
    snap = Snapshot(host_id="h1", hostname="h1", platform="linux", ts=int(time.time()), services=[ServiceSample(name="nginx", up=True)])
    await db.insert_batch([snap])
    await db.add_history(1, "h1", "cpu_percent", 95.0, 90.0)
    assert await db.delete_host("h1") is True
    assert await db.latest_services("h1") == []
    assert await db.list_history(host_id="h1") == []


async def test_retention_removes_services(db):
    """M1: retention_cleanup ลบ service_samples เก่าด้วย."""

    await db.upsert_host("h1", "h1", "linux", "tok", now=100)
    old = int(time.time()) - 999999
    await db.insert_batch([Snapshot(host_id="h1", hostname="h1", platform="linux", ts=old, services=[ServiceSample(name="x", up=True)])])
    await db.retention_cleanup(keep_days=7)
    assert await db.latest_services("h1") == []


async def test_offline_skips_host_without_data(db):
    """M5: host ที่ยังไม่เคยส่ง snapshot → ไม่นับเป็น offline."""

    cfg = AppConfig()
    cfg.ingest.offline_timeout_sec = 60
    await db.upsert_host("newbie", "new", "linux", "tok", now=int(time.time()) - 1000)
    fired = []
    monitor = HostDownMonitor(db, cfg, notifier=_FakeNotifier(fired))
    assert await monitor.check() == []
    assert fired == []


async def test_offline_no_refire_across_instances(db):
    """M5: persist fired state → monitor ใหม่ (หลัง restart) ไม่ยิงซ้ำ."""

    cfg = AppConfig()
    cfg.ingest.offline_timeout_sec = 60
    now = int(time.time())
    await db.upsert_host("gone", "gone", "linux", "tok", now=now - 1000)
    await db.insert_batch([Snapshot(host_id="gone", hostname="gone", platform="linux", ts=now - 1000)])

    fired1 = []
    m1 = HostDownMonitor(db, cfg, notifier=_FakeNotifier(fired1))
    ev1 = await m1.check()
    assert len(ev1) == 1  # fire ครั้งแรก

    fired2 = []
    m2 = HostDownMonitor(db, cfg, notifier=_FakeNotifier(fired2))  # จำลอง restart
    ev2 = await m2.check()
    assert ev2 == []  # ไม่ยิงซ้ำ (state อยู่ใน DB)
    assert fired2 == []


class _FakeNotifier:
    """Notifier จำลองบันทึก payload."""

    def __init__(self, sink):
        self._sink = sink

    async def send(self, payload):
        self._sink.append(payload)
