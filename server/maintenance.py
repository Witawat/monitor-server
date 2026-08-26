"""Background worker ลบข้อมูลเก่าตาม retention (กัน DB โตไม่สิ้นสุด)."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from server.storage.db import Database

_DEFAULT_INTERVAL = 3600  # ตรวจทุก 1 ชม.


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
