"""ทดสอบ agent retry/backoff + queue — offline แล้วค่อยส่งเมื่อกลับมา."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent.agent import _flush_queue
from agent.push import PushQueue, push_batch


class _Handler(BaseHTTPRequestHandler):
    received: list = []
    status = 200

    def log_message(self, *args):  # noqa: ANN002
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.__class__.received.append(self.path)
        self.send_response(self.__class__.status)
        self.end_headers()
        self.wfile.write(b"{}")


def test_offline_queues_then_flush_on_reconnect(tmp_path):
    """push ไป server ไม่ออนไลน์ → เก็บ queue; กลับมา online → flush ส่งทั้งหมด."""

    # offline ช่วงแรก: push ไปพอร์ตที่ไม่มี server
    url_offline = "http://127.0.0.1:1"
    q = PushQueue(tmp_path / "queue.json")
    assert push_batch(url_offline, "tok", [{"host_id": "h1"}]) is False
    q.enqueue([{"host_id": "h1"}, {"host_id": "h1"}])
    assert q.count() == 2

    # เปิด fake server จำลองว่า server กลับมา
    _Handler.received = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url_online = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _flush_queue(q, url_online, "tok", 100)
        assert q.count() == 0  # ส่งสำเร็จ → ล้าง queue
        assert len(_Handler.received) == 1  # ส่ง 1 ครั้ง (ทั้ง batch)
    finally:
        server.shutdown()
        thread.join(timeout=2)
