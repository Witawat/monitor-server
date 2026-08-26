"""ทดสอบ agent/push.py — PushQueue + push_batch ผ่าน fake HTTP server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent.push import Backoff, PushQueue, push_batch


class _Handler(BaseHTTPRequestHandler):
    """Fake server — รับ POST บันทึก body/header แล้วคืน 200."""

    received: list[dict] = []
    status = 200

    def log_message(self, *args):  # noqa: ANN002 - เงียบ log
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"[]")
        self.__class__.received.append(
            {"path": self.path, "token": self.headers.get("X-Agent-Token"), "body": body}
        )
        self.send_response(self.__class__.status)
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def fake_server():
    """สตาร์ท fake HTTP server ใน thread แล้วคืน (base_url, stop)."""

    _Handler.received = []
    _Handler.status = 200
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}", lambda: server.shutdown()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_push_batch_success(fake_server):
    """ส่ง batch สำเร็จ → True + server ได้รับ token/body ถูก."""

    url, _ = fake_server
    ok = push_batch(url, "tok123", [{"host_id": "h1", "cpu_percent": 10.0}])
    assert ok is True
    rec = _Handler.received[-1]
    assert rec["token"] == "tok123"
    assert rec["body"][0]["host_id"] == "h1"
    assert rec["path"].endswith("/api/v1/ingest")


def test_push_batch_offline():
    """server ไม่ออนไลน์ → คืน False (ไม่ raise)."""

    assert push_batch("http://127.0.0.1:1", "tok", [{"a": 1}]) is False


def test_push_batch_http_error(fake_server):
    """server คืน 500 → คืน False."""

    _Handler.status = 500
    url, _ = fake_server
    assert push_batch(url, "tok", [{"a": 1}]) is False


def test_queue_persistence(tmp_path):
    """PushQueue เก็บ/อ่านข้อมูลข้าม instance (ไฟล์ JSON)."""

    path = tmp_path / "q.json"
    q = PushQueue(path)
    q.enqueue([{"a": 1}, {"a": 2}])
    assert q.count() == 2
    q2 = PushQueue(path)
    assert q2.pending() == [{"a": 1}, {"a": 2}]
    q2.clear()
    assert q2.count() == 0


def test_backoff_delay():
    """delay เพิ่มแบบทวีคูณ + capped."""

    b = Backoff(base=2, factor=2, max_delay=10)
    assert b.delay(0) == 2.0
    assert b.delay(1) == 4.0
    assert b.delay(2) == 8.0
    assert b.delay(3) == 10.0  # capped


def test_agent_state_dir_next_to_exe(monkeypatch, tmp_path):
    """agent exe (frozen) เก็บ state (host_id/queue) ข้าง exe."""

    import sys

    fake_exe = tmp_path / "monitor-agent.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    from agent.agent import _default_state_dir

    assert _default_state_dir() == tmp_path
