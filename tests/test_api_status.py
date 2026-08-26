"""ทดสอบ server/main.py — skeleton API /api/health + /api/status."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server import __version__
from server.config import AppConfig
from server.main import create_app


def _client() -> TestClient:
    """สร้าง TestClient จาก config default."""

    app = create_app(AppConfig())
    return TestClient(app)


def test_health_ok():
    """GET /api/health → 200 + status ok + version."""

    with _client() as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_status_fields():
    """GET /api/status → 200 + มี server/ingest fields."""

    with _client() as client:
        resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["server"]["port"] == 18080
    assert "rate_limit_per_min" in body["ingest"]
    assert body["ingest"]["max_batch_size"] == 100


def test_unknown_api_404():
    """เส้นทาง API ที่ไม่มี → 404."""

    with _client() as client:
        resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
