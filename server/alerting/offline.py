"""Monitor host หมดอายุ (offline) — ส่ง notification เมื่อ host หายไปนานเกิน."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from server.alerting.notify import Notifier
from server.config import AppConfig
from server.storage.db import Database
from server.streaming import EVENT_ALERTS

_RULE_ID_OFFLINE = 0  # synthetic rule — ไม่มีใน alert_rules


def _fired_key(host_id: str) -> str:
    """key ใน state_kv สำหรับบอกว่า host นี้เคย fire offline ไปแล้ว."""

    return f"offline_fired:{host_id}"


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
        self._hub: Any = None   # SSE hub — broadcast alert ใหม่ (set หลังสร้าง app)
        self._task: asyncio.Task[None] | None = None

    def set_hub(self, hub: Any) -> None:
        """ผูก SSE hub เพื่อ broadcast เมื่อ fire alert (กัน badge ไม่สด)."""

        self._hub = hub

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
            key = _fired_key(h["host_id"])
            if h["online"]:
                if await self._db.kv_get(key) is not None:
                    await self._db.kv_delete(key)  # กลับมา online → reset
                continue
            if not await self._db.host_has_data(h["host_id"]):
                continue  # ยังไม่เคยส่งข้อมูล — ไม่ถือว่า "หาย"
            if await self._db.kv_get(key) is not None:
                continue  # ยิงไปแล้ว — ไม่ยิงซ้ำจนกว่าจะกลับมา
            await self._db.kv_set(key, str(now))
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
            if self._hub is not None:
                self._hub.broadcast(EVENT_ALERTS)   # host-down fire → badge/ประวัติสด
        return fired
