"""SSE event hub — push event ไป client ที่ subscribe (กัน poll ถี่)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

# ชนิด event ที่ broadcast ได้ (ตรงกับที่ client ฟัง)
EVENT_HOSTS = "hosts"       # fleet/host data เปลี่ยน (มี snapshot ใหม่ / host เปลี่ยน)
EVENT_ALERTS = "alerts"     # alert history/rules เปลี่ยน (badge + ประวัติ)


class SSEHub:
    """event bus อย่างง่าย: เก็บ queue ต่อ subscriber แล้ว broadcast event ให้ทุกตัว.

    Notes:
        - ใช้ asyncio.Queue (ไม่พึ่ง third-party) — subscriber แต่ละรายมี queue ของตัวเอง
        - ถ้า queue เต็ม (client ช้า/ค้าง) จะ drop event เก่า กันหน่วยความจำโตไม่จำกัด
        - ผูกกับ loop เดียวกับ app (lifespan) — เรียก broadcast จาก async task เดียวกัน
    """

    def __init__(self, max_queued: int = 20) -> None:
        self._subs: set[asyncio.Queue[str]] = set()
        self._max_queued = max_queued

    def subscribe(self) -> asyncio.Queue[str]:
        """สร้าง queue ใหม่สำหรับ subscriber รายหนึ่ง; คืน queue เพื่อ await event."""

        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._max_queued)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        """ถอด subscriber (กัน connection leak เมื่อ client disconnect)."""

        self._subs.discard(q)

    def broadcast(self, event: str) -> None:
        """ส่ง event ให้ทุก subscriber; drop ถ้า queue เต็ม (กันค้าง)."""

        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # ลบของเก่า 1 ตัวก่อน กัน subscriber ช้าไม่ได้รับ event ใหม่
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    def subscriber_count(self) -> int:
        """จำนวน subscriber ที่กำลังฟังอยู่ (ใช้ debug/ทดสอบ)."""

        return len(self._subs)

    async def events(self, timeout: float = 15.0) -> AsyncIterator[str]:
        """วนอ่าน event จาก queue subscriber ใหม่; คืน heartbeat ทุก timeout วินาที.

        Args:
            timeout: เวลารอสูงสุดก่อนส่ง heartbeat กัน proxy/load balancer ตัด connection.
        """

        q = self.subscribe()
        try:
            while True:
                try:
                    yield await asyncio.wait_for(q.get(), timeout=timeout)
                except TimeoutError:
                    yield "__heartbeat__"
        finally:
            self.unsubscribe(q)
