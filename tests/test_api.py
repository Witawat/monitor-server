"""ทดสอบ API เฟส 1 แบบ end-to-end ผ่าน TestClient (DB temp จริง)."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from server.config import AppConfig
from server.main import create_app
from server.streaming import SSEHub
from server.webui.auth import hash_password, sign_session
from shared.metric import HEADER_TOKEN


class _FakeWebhookHandler(BaseHTTPRequestHandler):
    """fake webhook รับ POST สำหรับทดสอบ endpoint /test."""

    received: list[bytes] = []

    def log_message(self, *args):  # noqa: ANN002
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.__class__.received.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def webhook_server():
    """fake webhook server ใน thread."""

    _FakeWebhookHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _FakeWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/hook"
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=2)


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


def test_remote_config_roundtrip(tmp_path):
    """ตั้ง remote config ต่อ host แล้วอ่านกลับ + ingest คืน config ให้ agent."""

    with _client(tmp_path) as c:
        c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "tok"})

        # ตั้ง config ผ่าน admin
        r = c.put("/api/v1/hosts/h1/config", json={"interval": 10, "watch": "nginx,mysql", "ports": "80:web", "max_batch": 50})
        assert r.status_code == 200

        # อ่านกลับ
        got = c.get("/api/v1/hosts/h1/config").json()
        assert got["interval"] == 10
        assert got["watch"] == "nginx,mysql"
        assert got["ports"] == "80:web"

        # agent push (token "tok") → response คืน config ให้ pull/apply
        push = c.post("/api/v1/ingest", json=_batch(), headers={HEADER_TOKEN: "tok"})
        assert push.json()["config"]["interval"] == 10

        # เปลี่ยน hostname ผ่าน config ด้วย
        assert c.put("/api/v1/hosts/h1/config", json={"hostname": "web-prod"}).status_code == 200
        assert c.get("/api/v1/hosts/h1").json()["hostname"] == "web-prod"


def test_notifier_settings_roundtrip(tmp_path):
    """ตั้งค่า webhook/telegram ผ่าน API แล้วอ่านกลับ."""

    with _client(tmp_path) as c:
        r = c.put(
            "/api/v1/settings/notifiers",
            json={"webhook": {"url": "https://h.example/x", "enabled": True}},
        )
        assert r.status_code == 200
        got = r.json()
        assert got["webhook"]["url"] == "https://h.example/x"
        assert got["webhook"]["configured"] is True
        assert got["webhook"]["enabled"] is True

        r2 = c.put(
            "/api/v1/settings/notifiers",
            json={"telegram": {"bot_token": "1:AAA", "chat_id": "-100", "enabled": True}},
        )
        assert r2.status_code == 200
        assert r2.json()["telegram"]["configured"] is True


def test_notifier_settings_enabled_requires_values(tmp_path):
    """เปิดช่องทางแต่ค่าจำเป็นไม่ครบ → 400 + ไม่บันทึก."""

    with _client(tmp_path) as c:
        assert c.put("/api/v1/settings/notifiers", json={"webhook": {"url": "", "enabled": True}}).status_code == 400
        assert c.put(
            "/api/v1/settings/notifiers",
            json={"telegram": {"bot_token": "", "chat_id": "", "enabled": True}},
        ).status_code == 400
        got = c.get("/api/v1/settings/notifiers").json()
        assert got["webhook"]["configured"] is False
        assert got["telegram"]["configured"] is False


def test_notifier_settings_disable_keeps_values(tmp_path):
    """ปิด enabled → ค่าที่ตั้งยังอยู่ (แค่ปิดช่องทาง)."""

    with _client(tmp_path) as c:
        c.put("/api/v1/settings/notifiers", json={"webhook": {"url": "https://h.example/x", "enabled": True}})
        r = c.put("/api/v1/settings/notifiers", json={"webhook": {"enabled": False}})
        assert r.json()["webhook"]["enabled"] is False
        assert r.json()["webhook"]["url"] == "https://h.example/x"


def test_notifier_webhook_test_endpoint(webhook_server, tmp_path):
    """POST /test ไป fake webhook → ok + มี payload ถูกส่ง."""

    with _client(tmp_path) as c:
        r = c.post("/api/v1/settings/notifiers/webhook/test", json={"url": webhook_server})
        assert r.json()["ok"] is True
        assert len(_FakeWebhookHandler.received) == 1
        assert b"test" in _FakeWebhookHandler.received[0]


def test_notifier_webhook_test_requires_url(tmp_path):
    """/test ไม่มี url → 400."""

    with _client(tmp_path) as c:
        assert c.post("/api/v1/settings/notifiers/webhook/test", json={"url": ""}).status_code == 400


def test_telegram_scan_chatid(tmp_path, monkeypatch):
    """ดึง chat_id อัตโนมัติจาก getUpdates (mock httpx.AsyncClient)."""

    captured: dict = {}

    class _FakeResp:
        status_code = 200
        text = "{}"
        headers = {"content-type": "application/json"}

        def json(self):
            return {"result": [{"message": {"chat": {"id": -100123456789}}}]}

    class _FakeAC:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):  # noqa: ANN002
            return False

        async def get(self, url, **kw):
            captured["url"] = url
            captured["params"] = kw.get("params")
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAC)
    with _client(tmp_path) as c:
        r = c.post("/api/v1/settings/notifiers/telegram/chatid", json={"bot_token": "1:AAA"})
        body = r.json()
        assert body["ok"] is True
        assert body["chat_id"] == "-100123456789"
        assert "getUpdates" in captured["url"]
        assert captured["params"]["offset"] == -1


def test_notifier_enabled_string_false(tmp_path):
    """enabled ส่งเป็น string 'false' → ต้องปิดจริง (กัน truthy บั๊ก)."""

    with _client(tmp_path) as c:
        c.put(
            "/api/v1/settings/notifiers",
            json={"webhook": {"url": "https://h.example/x", "enabled": "false"}},
        )
        got = c.get("/api/v1/settings/notifiers").json()
        assert got["webhook"]["enabled"] is False


def test_telegram_test_network_error(tmp_path, monkeypatch):
    """test telegram: server ไร้เน็ต/เชื่อมต่อไม่ได้ → คืน ok:false (ไม่ 500)."""

    class _FakeAC:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):  # noqa: ANN002
            return False

        async def get(self, url, **kw):
            raise httpx.ConnectError("boom")

        async def post(self, *a, **k):  # noqa: ANN002, ANN003
            raise AssertionError("ไม่ควรเรียก post เมื่อ getMe พัง")

    monkeypatch.setattr("httpx.AsyncClient", _FakeAC)
    with _client(tmp_path) as c:
        r = c.post(
            "/api/v1/settings/notifiers/telegram/test",
            json={"bot_token": "1:AAA", "chat_id": "-100"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False


def test_telegram_scan_chatid_nonjson(tmp_path, monkeypatch):
    """chatid: response 200 แต่ body ไม่ใช่ JSON → คืน ok:false (ไม่ 500)."""

    class _BadResp:
        status_code = 200
        text = "<html>bad gateway</html>"
        headers = {"content-type": "text/html"}

        def json(self):
            raise ValueError("no json")

    class _FakeAC:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):  # noqa: ANN002
            return False

        async def get(self, url, **kw):
            return _BadResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAC)
    with _client(tmp_path) as c:
        r = c.post("/api/v1/settings/notifiers/telegram/chatid", json={"bot_token": "1:AAA"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


def test_login_rate_limit(tmp_path):
    """login เกินอัตรา (5/นาที/IP) → 429 + audit บันทึกทุกความพยายาม."""

    with _client(tmp_path, authed=False) as c:
        for _ in range(5):
            r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
            assert r.status_code == 401
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429

    with _client(tmp_path, authed=True) as c:
        audit = c.get("/api/v1/auth/audit").json()
        assert len(audit) == 6  # 5 ล้มเหลว + 1 ถูกจำกัด
        assert sum(1 for a in audit if a["action"] == "login.fail") == 5
        assert sum(1 for a in audit if a["action"] == "login.blocked") == 1


def test_login_success_audit(tmp_path):
    """login ถูกต้อง → audit บันทึก login.ok + เข้าสู่ระบบได้."""

    with _client(tmp_path, authed=False) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"})
        assert r.status_code == 200

    with _client(tmp_path, authed=True) as c:
        audit = c.get("/api/v1/auth/audit").json()
        assert any(a["action"] == "login.ok" and a["ok"] == 1 for a in audit)


def test_change_password_flow(tmp_path):
    """เปลี่ยนรหัสผ่าน: ตรวจรหัสเก่า → ตั้งใหม่ → login ใหม่ได้, เก่าใช้ไม่ได้."""

    with _client(tmp_path, authed=False) as c:
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"}).status_code == 200

    with _client(tmp_path, authed=True) as c:
        r = c.post(
            "/api/v1/auth/password",
            json={"old_password": "secretpw", "new_password": "newpass123", "confirm_password": "newpass123"},
        )
        assert r.status_code == 200

    with _client(tmp_path, authed=False) as c:
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"}).status_code == 401
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "newpass123"}).status_code == 200


def test_change_password_too_short(tmp_path):
    """รหัสใหม่สั้นเกิน 8 → 400; ยืนยันไม่ตรง → 400."""

    with _client(tmp_path, authed=True) as c:
        assert c.post(
            "/api/v1/auth/password",
            json={"old_password": "x", "new_password": "abc", "confirm_password": "abc"},
        ).status_code == 400
    with _client(tmp_path, authed=False) as c:
        # login เก่ายังใช้ได้ (ยังไม่เปลี่ยน)
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "secretpw"}).status_code == 200


def test_setup_auto_fill(tmp_path):
    """/setup คืน creds ครั้งแรก แล้วหายหลัง login สำเร็จ."""

    cfg = AppConfig()
    cfg.server.data_dir = str(tmp_path)
    cfg.webui.admin_pass_hash = hash_password("adminpw")
    client = TestClient(create_app(cfg, setup_credentials=("admin", "setupsecret")))
    client.__enter__()
    try:
        assert client.get("/api/v1/auth/setup").json() == {"user": "admin", "pass": "setupsecret"}
        assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "adminpw"}).status_code == 200
        assert client.get("/api/v1/auth/setup").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_alert_badge_endpoint(tmp_path):
    """/api/v1/alerts/badge คืนจำนวน unacked (admin เท่านั้น)."""

    with _client(tmp_path, authed=True) as c:
        db = c.app.state.db
        c.portal.call(db.add_history, 1, "h1", "cpu_percent", 95.0, 90.0)
        c.portal.call(db.add_history, 2, "h2", "cpu_percent", 96.0, 90.0)
        assert c.get("/api/v1/alerts/badge").json() == {"unacked": 2}
    with _client(tmp_path, authed=False) as c:
        assert c.get("/api/v1/alerts/badge").status_code == 401


def test_stream_requires_auth(tmp_path):
    """/api/v1/stream ต้อง login ก่อน (SSE)."""

    with _client(tmp_path, authed=False) as c:
        assert c.get("/api/v1/stream").status_code == 401


def test_sse_hub_broadcast():
    """SSEHub broadcast/event/unsubscribe ทำงานถูกต้อง (กัน leak)."""

    async def run():
        hub = SSEHub()
        # subscriber รับ event ตามลำดับ
        q = hub.subscribe()
        hub.broadcast("hosts")
        hub.broadcast("alerts")
        assert await q.get() == "hosts"
        assert await q.get() == "alerts"
        assert hub.subscriber_count() == 1
        # unsubscribe ลด count (กัน connection leak)
        hub.unsubscribe(q)
        assert hub.subscriber_count() == 0

    asyncio.run(run())
