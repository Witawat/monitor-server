"""ทดสอบ server/main.py — skeleton API /api/health + /api/status."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from server import __version__
from server.config import AppConfig
from server.main import create_app
from server.webui.auth import hash_password, sign_session


@contextmanager
def _authed_client():
    """TestClient (data_dir=temp) พร้อม session cookie."""

    cfg = AppConfig()
    cfg.server.data_dir = str(Path(tempfile.mkdtemp()))
    cfg.webui.admin_pass_hash = hash_password("secretpw")
    app = create_app(cfg)
    with TestClient(app) as client:
        client.cookies.set("session", sign_session(client.app.state.session_secret, "admin"))
        yield client


def test_health_ok():
    """GET /api/health → 200 + status ok + version."""

    with _authed_client() as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_status_fields():
    """GET /api/status → 200 + มี server/ingest fields."""

    with _authed_client() as client:
        resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["server"]["port"] == 18080
    assert "rate_limit_per_min" in body["ingest"]
    assert body["ingest"]["max_batch_size"] == 100


def test_status_requires_auth():
    """GET /api/status ไม่มี session → 401."""

    cfg = AppConfig()
    cfg.server.data_dir = str(Path(tempfile.mkdtemp()))
    cfg.webui.admin_pass_hash = hash_password("secretpw")
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/status").status_code == 401


def test_unknown_api_404():
    """เส้นทาง API ที่ไม่มี → 404."""

    with _authed_client() as client:
        resp = client.get("/api/v1/nope")
    assert resp.status_code == 404


def test_runtime_dir_resolution(monkeypatch, tmp_path):
    """exe (frozen) ใช้ config/data/logs ข้าง exe — แก้จัดการง่าย."""

    import sys

    fake_exe = tmp_path / "monitor-server.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    from server.main import _resolve_config_path, _resolve_dir, _runtime_dir

    assert _runtime_dir() == tmp_path

    cfg = tmp_path / "config.toml"
    cfg.write_text("", encoding="utf-8")
    # path ที่ไม่มีจริง → fallback เจอ config ข้าง exe
    assert _resolve_config_path(str(tmp_path / "nope.toml")) == str(cfg)

    assert _resolve_dir("data") == tmp_path / "data"         # relative → ข้าง exe
    abs_abs = tmp_path / "elsewhere"
    assert _resolve_dir(str(abs_abs)) == abs_abs             # absolute คงเดิม
