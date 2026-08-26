"""ทดสอบ WebUI + auth — login, session, static, SPA shell."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.config import AppConfig
from server.main import create_app
from server.webui.auth import hash_password


def _client(tmp_path, password: str = "secretpw"):
    """สร้าง TestClient พร้อม admin hash จาก config."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.webui.admin_pass_hash = hash_password(password)
    return TestClient(create_app(cfg))


def test_index_redirects_to_login_when_unauth(tmp_path):
    """ยังไม่ login → GET / คืนหน้า login."""

    with _client(tmp_path) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert 'id="loginForm"' in r.text


def test_login_wrong_password_401(tmp_path):
    """password ผิด → 401."""

    with _client(tmp_path) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401


def test_login_success_sets_cookie(tmp_path):
    """login ถูก → cookie session + GET / คืน SPA shell."""

    with _client(tmp_path) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})
        assert r.status_code == 200
        assert "session" in c.cookies
        home = c.get("/")
        assert home.status_code == 200
        assert 'id="view-fleet"' in home.text  # include parts ทำงาน
        # version จาก __version__ ไม่ใช่ hardcode (regression กัน UI โชว์ v0.1.0)
        from server import __version__
        assert f"v{__version__}" in home.text


def test_api_requires_auth(tmp_path):
    """hosts API ไม่มี session → 401."""

    with _client(tmp_path) as c:
        assert c.get("/api/v1/hosts").status_code == 401


def test_logout_clears_session(tmp_path):
    """logout → กลับไป 401 ที่ API."""

    with _client(tmp_path) as c:
        c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})
        c.post("/api/v1/auth/logout")
        assert c.get("/api/v1/hosts").status_code == 401


def test_static_chart_bundle_served(tmp_path):
    """Chart.js local bundle เสิร์ฟที่ /static."""

    with _client(tmp_path) as c:
        r = c.get("/static/js/chart.umd.min.js")
        assert r.status_code == 200
        assert "Chart" in r.text


def test_token_generate_and_revoke(tmp_path):
    """gen token + revoke ผ่าน API."""

    with _client(tmp_path) as c:
        c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})
        gen = c.post("/api/v1/auth/tokens", json={"host_id": "db-02"})
        assert gen.status_code == 200
        token = gen.json()["token"]
        assert len(token) == 36
        assert c.get("/api/v1/auth/tokens").json()[0]["host_id"] == "db-02"
        assert c.delete("/api/v1/auth/tokens/db-02").status_code == 200


def test_alerts_crud_and_ack(tmp_path):
    """alerts API: create rule → list → fire history → ack."""

    from server.storage.db import Database

    with _client(tmp_path) as c:
        c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})
        rule = c.post(
            "/api/v1/alerts",
            json={"name": "CPU สูง", "host_id": "", "metric": "cpu_percent", "op": ">", "threshold": 90.0},
        )
        assert rule.status_code == 201
        rule_id = rule.json()["id"]

        # ใส่ประวัติตรง ๆ (จำลองว่า engine fire แล้ว)
        db: Database = c.app.state.db
        import asyncio

        history_id = asyncio.run(
            db.add_history(rule_id, "h1", "cpu_percent", 95.0, 90.0)
        )
        hist = c.get("/api/v1/alerts/history")
        assert hist.status_code == 200
        assert any(h["id"] == history_id for h in hist.json())

        assert c.post(f"/api/v1/alerts/history/{history_id}/ack").status_code == 200
        acked = c.get("/api/v1/alerts/history?ack=true").json()
        assert any(h["id"] == history_id and h["ack"] == 1 for h in acked)


def test_guide_page(tmp_path):
    """GET /guide คืนหน้าแนะนำ (.ex ไม่เปิด .md 404 ใน exe ตัวเดียว)."""

    with _client(tmp_path) as c:
        r = c.get("/guide")
        assert r.status_code == 200
        assert "วิธีติดตั้ง agent" in r.text
        # /docs/{name} ที่เคย 404 → ไม่ใช่หน้าเลย; /guide เป็นตัวแทนที่แนะนำ
        assert 'href="/#/fleet"' in r.text
