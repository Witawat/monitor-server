"""Monitor host หมดอายุ (offline) — ส่ง notification เมื่อ host หายไปนานเกิน."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from server.alerting.notify import Notifier
from server.config import AppConfig
from server.storage.db import Database

_RULE_ID_OFFLINE = 0  # synthetic rule — ไม่มีใน alert_rules


class HostDownMonitor:
    """ตรวจ host ที่ offline เกิน timeout แล้วบันทึกประวัติ + แจ้งเตือน."""

    def __init__(
        self, db: Database, config: AppConfig, notifier: Notifier | None = None, check_interval: float = 30.0
    ) -> None:
        """สร้าง monitor (loop ตรวจทุก check_interval วินาที)."""

        self._db = db
        self._config = config
        self._notifier = notifier or Notifier(config.alerting.notifiers)
        self._check_interval = check_interval
        self._fired: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """เริ่ม background task (เรียกใน lifespan)."""

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
        """วนลูปตรวจ offline ทุก interval."""

        while True:
            await self.check()
            await asyncio.sleep(self._check_interval)

    async def check(self, now: int | None = None) -> list[dict[str, Any]]:
        """ตรวจ host ครั้งเดียว; คืนเหตุการณ์ offline ที่ fire (ใหม่)."""

        if not self._config.alerting.enabled:
            return []
        now = now or int(time.time())
        hosts = await self._db.list_hosts(timeout_sec=self._config.ingest.offline_timeout_sec)
        fired: list[dict[str, Any]] = []
        for h in hosts:
            if h["online"]:
                self._fired.discard(h["host_id"])  # กลับมา online → reset
                continue
            if h["host_id"] in self._fired:
                continue  # ยิงไปแล้ว — ไม่ยิงซ้ำจนกว่าจะกลับมา
            self._fired.add(h["host_id"])
            history_id = await self._db.add_history(
                _RULE_ID_OFFLINE, h["host_id"], "host_down", 0.0, 0.0, now
            )
            payload = {
                "id": history_id,
                "rule_id": _RULE_ID_OFFLINE,
                "name": "Host ออฟไลน์",
                "host_id": h["host_id"],
                "metric": "host_down",
                "value": 0.0,
                "threshold": 0.0,
                "op": "",
                "created_at": now,
            }
            await self._notifier.send(payload)
            fired.append(payload)
        return fired
