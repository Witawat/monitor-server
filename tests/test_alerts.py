"""ทดสอบ alerting — engine (rule เกิน threshold) + webhook notify + ack."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from server.alerting.engine import AlertEngine, metric_value, parse_duration
from server.alerting.notify import Notifier
from server.config import AppConfig, NotifierConfig
from server.storage.db import Database
from shared.metric import Snapshot


class _WebhookHandler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def log_message(self, *args):  # noqa: ANN002
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.__class__.received.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def webhook_server():
    """fake webhook server ใน thread."""

    _WebhookHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/hook"
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "alert.db")
    await database.connect()
    yield database
    await database.close()


def _snap(host_id: str = "h1", cpu: float = 95.0) -> Snapshot:
    return Snapshot(host_id=host_id, hostname="h1", platform="linux", ts=int(time.time()), cpu_percent=cpu)


def test_parse_duration():
    """แปลง duration string เป็นวินาที."""

    assert parse_duration("5m") == 300
    assert parse_duration("1h") == 3600
    assert parse_duration("90s") == 90
    assert parse_duration("bad") == 0


def test_metric_value():
    """ดึงค่าจาก Snapshot ตามชื่อ metric."""

    assert metric_value(_snap(cpu=77.0), "cpu_percent") == 77.0
    assert metric_value(_snap(), "memory.percent") == 0.0
    assert metric_value(_snap(), "nonexistent") is None


async def test_engine_fires_after_duration(db):
    """ค่าเกิน threshold ครบ duration → fire + บันทึก history."""

    cfg = AppConfig()
    rule_id = await db.create_rule(
        {"name": "CPU สูง", "host_id": "", "metric": "cpu_percent", "op": ">", "threshold": 90.0, "duration": "5m"}
    )
    fired: list[dict] = []

    class FakeNotifier:
        async def send(self, payload):
            fired.append(payload)

    engine = AlertEngine(db, cfg, notifier=FakeNotifier())
    t0 = int(time.time())
    await engine.evaluate([_snap(cpu=95.0)], now=t0)          # arming
    events = await engine.evaluate([_snap(cpu=96.0)], now=t0 + 301)  # เกิน 5m → fire
    assert len(events) == 1
    assert events[0]["metric"] == "cpu_percent"
    assert len(fired) == 1
    history = await db.list_history()
    assert len(history) == 1
    assert history[0]["rule_id"] == rule_id


async def test_engine_no_fire_when_short(db):
    """ค่าเกิน แต่ยังไม่ครบ duration → ยังไม่ fire."""

    cfg = AppConfig()
    await db.create_rule(
        {"name": "CPU", "host_id": "", "metric": "cpu_percent", "op": ">", "threshold": 90.0, "duration": "5m"}
    )
    engine = AlertEngine(db, cfg, notifier=None)
    t0 = int(time.time())
    events = await engine.evaluate([_snap(cpu=99.0)], now=t0)  # แค่จุดเดียว < 5m
    assert events == []
    assert await db.list_history() == []


async def test_engine_resets_when_normal(db):
    """ค่ากลับปกติ → reset ไม่ fire ซ้ำ."""

    cfg = AppConfig()
    await db.create_rule(
        {"name": "CPU", "host_id": "", "metric": "cpu_percent", "op": ">", "threshold": 90.0, "duration": "1s"}
    )
    engine = AlertEngine(db, cfg, notifier=None)
    t0 = int(time.time())
    await engine.evaluate([_snap(cpu=95.0)], now=t0)
    await engine.evaluate([_snap(cpu=10.0)], now=t0 + 5)   # กลับปกติ → reset
    events = await engine.evaluate([_snap(cpu=95.0)], now=t0 + 10)  # arming ใหม่
    assert events == []


async def test_notifier_webhook(webhook_server):
    """Notifier ส่ง webhook (mock HTTP server รับ payload)."""

    cfg = NotifierConfig(webhook={"url": webhook_server})
    n = Notifier(cfg)
    sent = await n.send({"host_id": "h1", "metric": "cpu_percent", "value": 95.0, "threshold": 90.0})
    assert "webhook" in sent
    assert len(_WebhookHandler.received) == 1
    assert _WebhookHandler.received[0]["metric"] == "cpu_percent"


async def test_ack_history(db):
    """ack ประวัติทำงาน."""

    hid = await db.add_history(1, "h1", "cpu_percent", 95.0, 90.0)
    assert await db.ack_history(hid) is True
    hist = await db.list_history()
    assert hist[0]["ack"] == 1
