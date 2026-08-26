"""ทดสอบ API เฟส 1 แบบ end-to-end ผ่าน TestClient (DB temp จริง)."""

from __future__ import annotations

import time
from contextlib import contextmanager

from fastapi.testclient import TestClient

from server.config import AppConfig
from server.main import create_app
from server.webui.auth import hash_password, sign_session
from shared.metric import HEADER_TOKEN


def _batch() -> list[dict]:
    """batch 1 snapshot ใช้ส่งผ่าน HTTP."""

    now = int(time.time())
    return [
        {
            "host_id": "h1",
            "hostname": "web-01",
            "platform": "linux",
            "ts": now,
            "cpu_percent": 42.5,
            "load": [0.5, 0.4, 0.3],
            "memory": {"total": 1000, "used": 400, "percent": 40.0},
        }
    ]


@contextmanager
def _client(tmp_path, *, authed: bool = True):
    """สร้าง TestClient (data_dir=temp); authed=True ตั้ง session cookie ให้แล้ว."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.webui.admin_pass_hash = hash_password("secretpw")
    client = TestClient(create_app(cfg))
    with client:
        if authed:
            secret = client.app.state.session_secret
            client.cookies.set("session", sign_session(secret, "admin"))
        yield client


def test_ingest_then_hosts_and_metrics(tmp_path):
    """POST ingest → host ขึ้น + query metrics คืน series."""

    with _client(tmp_path) as c:
        r = c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "tok1"})
        assert r.status_code == 200
        assert r.json()["received"] == 1

        hosts = c.get("/api/v1/hosts")
        assert hosts.status_code == 200
        assert len(hosts.json()) == 1
        assert hosts.json()[0]["host_id"] == "h1"

        detail = c.get("/api/v1/hosts/h1")
        assert detail.status_code == 200

        metrics = c.get("/api/v1/hosts/h1/metrics?range=1h")
        assert metrics.status_code == 200
        points = metrics.json()["series"]["cpu_percent"]["points"]
        assert len(points) == 1
        assert points[0][1] == 42.5


def test_ingest_unknown_token_401(tmp_path):
    """token ไม่รู้จัก + ปิด auto-register → 401."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.auth.allow_registration = False
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "bad"})
        assert r.status_code == 401


def test_ingest_missing_token_401(tmp_path):
    """ไม่มี header token → 401 (เพราะ token ว่าง + ไม่รู้จัก)."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.auth.allow_registration = False
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/v1/ingest", json=_batch())
        assert r.status_code == 401


def test_ingest_oversized_400(tmp_path):
    """batch เกิน max_batch_size → 400."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.ingest.max_batch_size = 1
    with TestClient(create_app(cfg)) as c:
        r = c.post(
            "/api/v1/ingest",
            json=[_batch()[0], _batch()[0]],
            headers={HEADER_TOKEN: "tok"},
        )
        assert r.status_code == 400


def test_metrics_unknown_host_empty(tmp_path):
    """host ที่ไม่มีข้อมูล → series ว่าง."""

    with _client(tmp_path) as c:
        metrics = c.get("/api/v1/hosts/ghost/metrics?range=1h")
        assert metrics.status_code == 200
        assert metrics.json()["series"]["cpu_percent"]["points"] == []


def test_metrics_bad_range_400(tmp_path):
    """range ไม่รองรับ → 400."""

    with _client(tmp_path) as c:
        r = c.get("/api/v1/hosts/h1/metrics?range=99m")
        assert r.status_code == 400


def test_delete_host(tmp_path):
    """DELETE host → ลบแล้ว 404 ต่อไป."""

    with _client(tmp_path) as c:
        c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "tok"})
        assert c.delete("/api/v1/hosts/h1").status_code == 200
        assert c.get("/api/v1/hosts/h1").status_code == 404


def test_status_host_count(tmp_path):
    """/api/status นับ host count."""

    with _client(tmp_path) as c:
        c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "tok"})
        assert c.get("/api/status").json()["host_count"] == 1
