"""ตรรกะรับ push จาก agent — validate batch + rate limit + upsert host.

หัวใจของฝั่งรับ: เช็ค token → rate limit → validate schema → เขียนลง DB.
"""

from __future__ import annotations

import time
from typing import Any

from server.alerting.engine import AlertEngine
from server.config import AppConfig
from server.storage.db import Database
from shared.metric import Snapshot, snapshot_from_dict

# ── errors ──


class IngestError(Exception):
    """Base error ของ ingest พร้อม HTTP status."""

    status_code: int = 400


class InvalidBatch(IngestError):
    """Batch ผิดกฎ (schema ไม่ตรง / เกินขนาด)."""

    status_code = 400


class UnauthorizedToken(IngestError):
    """Token ไม่รู้จักและปิด auto-register."""

    status_code = 401


class RateLimited(IngestError):
    """ยิงเกิน rate limit."""

    status_code = 429


# ── rate limiter ──

class RateLimiter:
    """Sliding-window rate limiter ต่อ key (เช่น client IP) ต่อนาที."""

    def __init__(self) -> None:
        """สร้าง limiter (limit อ่านจาก config ตอนเรียก allow)."""

        self._window = 60
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit_per_min: int) -> bool:
        """บันทึก request; คืน True ถ้ายังไม่เกิน limit_per_min."""

        now = time.monotonic()
        recent = [t for t in self._hits.get(key, []) if now - t < self._window]
        if not recent:
            self._hits.pop(key, None)  # กันค้าง key ที่หมดอายุ (L1)
        if limit_per_min <= 0 or len(recent) >= limit_per_min:
            if recent:
                self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True


# ── service ──

class IngestService:
    """รับ batch จาก agent: validate, rate limit, upsert host, เขียน metrics."""

    def __init__(self, db: Database, config: AppConfig, alert_engine: AlertEngine | None = None) -> None:
        """ผูก service เข้ากับ DB + config (รวม rate limiter ต่อ IP + alert engine)."""

        self._db = db
        self._config = config
        self._alert_engine = alert_engine
        self._limiter = RateLimiter()

    async def process_batch(self, token: str, client_ip: str, raw: list[dict[str, Any]]) -> tuple[int, str, dict[str, Any]]:
        """ประมวลผล batch หนึ่ง; คืน (received, host_id, remote_config).

        Raises:
            RateLimited: ถ้ายิงเกิน rate limit.
            UnauthorizedToken: ถ้า token ไม่รู้จัก + ปิด auto-register.
            InvalidBatch: ถ้า batch ว่าง / เกิน max_batch_size / host_id/platform ว่าง.
        """
        if not self._limiter.allow(client_ip, self._config.ingest.rate_limit_per_min):
            raise RateLimited()

        if len(raw) > self._config.ingest.max_batch_size:
            raise InvalidBatch(
                f"batch เกิน max_batch_size={self._config.ingest.max_batch_size}"
            )
        if not raw:
            raise InvalidBatch("batch ว่าง")

        if not token:
            # token ว่าง = ไม่ระบุตัวตน — ไม่อนุญาตให้ auto-register (กันยึด identity
            # ของ host ที่ revoke แล้ว ซึ่งถูกตั้ง token='')
            raise UnauthorizedToken("ต้องระบุ X-Agent-Token")

        host = await self._db.host_by_token(token)
        if host is None:
            if not self._config.auth.allow_registration:
                raise UnauthorizedToken("token ไม่รู้จัก")
            host_id = self._auto_host_id(raw)
            if await self._db.host_exists(host_id):
                # กันแย่งชิง identity: host_id มีอยู่แล้วแต่ token ต่าง → ไม่ adopt
                raise InvalidBatch("host_id มีอยู่แล้ว — ใช้ token เดิมของ host นี้")
            hostname = str(raw[0].get("hostname", ""))
            platform = str(raw[0].get("platform", ""))
        else:
            host_id = host["host_id"]
            # agent ส่ง hostname/platform สดมาเสมอ — ใช้ค่านี้ต่อเมื่อไม่ว่าง
            # (กันกรณี host ถูกสร้างด้วย token ก่อน first push → hostname ว่างค้าง)
            hostname = str(raw[0].get("hostname") or host["hostname"])
            platform = str(raw[0].get("platform") or host["platform"])

        snaps: list[Snapshot] = []
        for item in raw:
            snap = snapshot_from_dict(item)
            if not snap.host_id or not snap.platform:
                raise InvalidBatch("snapshot ขาด host_id/platform")
            snap.host_id = host_id  # บังคับให้ตรง token ที่ auth
            snap.hostname = hostname
            snap.platform = platform
            snaps.append(snap)

        await self._db.insert_batch(snaps)
        await self._db.upsert_host(host_id, hostname, platform, token)
        if self._alert_engine is not None:
            await self._alert_engine.evaluate(snaps)
        remote_cfg = await self._db.get_desired_config_by_token(token)
        return len(snaps), host_id, remote_cfg

    @staticmethod
    def _auto_host_id(raw: list[dict[str, Any]]) -> str:
        """ดึง host_id จาก snapshot แรกเพื่อ auto-register host ใหม่."""

        host_id = str(raw[0].get("host_id", ""))
        if not host_id:
            raise InvalidBatch("auto-register ต้องมี host_id ใน snapshot แรก")
        return host_id
