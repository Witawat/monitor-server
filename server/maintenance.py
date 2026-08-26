"""Background worker ลบข้อมูลเก่า + rollup (กัน DB โตไม่สิ้นสุด + query เร็ว)."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from server.storage.db import Database

_DEFAULT_INTERVAL = 3600  # ตรวจทุก 1 ชม.


def _interval_seconds(name: str) -> int:
    """แปลงชื่อ interval เช่น '5m'/'1h' เป็นวินาที (0 ถ้าไม่รู้จัก)."""

    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(name) < 2 or name[-1] not in mult:
        return 0
    try:
        return int(name[:-1]) * mult[name[-1]]
    except ValueError:
        return 0


class RetentionWorker:
    """วนลบ raw metrics เก่ากว่า keep_days ทุก interval."""

    def __init__(self, db: Database, keep_days: int, interval: float = _DEFAULT_INTERVAL) -> None:
        """สร้าง worker (ยังไม่เริ่มจนกว่าจะ start())."""

        self._db = db
        self._keep_days = keep_days
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """เริ่ม background task."""

        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """หยุด background task."""

        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        """วนลูปลบข้อมูลเก่าทุก interval."""

        while True:
            await self._db.retention_cleanup(self._keep_days)
            await asyncio.sleep(self._interval)


class RollupWorker:
    """รวม raw metrics เป็น bucket ในตาราง rollup (ตาม rollup_intervals)."""

    def __init__(self, db: Database, intervals: list[str], interval: float = 60.0) -> None:
        """สร้าง worker (ยังไม่เริ่มจนกว่าจะ start())."""

        self._db = db
        self._intervals = intervals
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """เริ่ม background task."""

        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """หยุด background task."""

        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_once(self, now: int | None = None) -> int:
        """rollup หนึ่งรอบทุก interval; คืนจำนวน bucket รวมที่เขียน."""

        total = 0
        for name in self._intervals:
            sec = _interval_seconds(name)
            if sec > 0:
                total += await self._db.aggregate_rollup(sec, name, now=now)
        return total

    async def _run(self) -> None:
        """วน rollup ทุก interval."""

        while True:
            await self.run_once()
            await asyncio.sleep(self._interval)
