"""ตัวส่ง notification — webhook (POST JSON) + Telegram."""

from __future__ import annotations

from typing import Any

import httpx

from server.alerting import settings as notifier_settings
from server.config import NotifierConfig
from server.storage.db import Database


class Notifier:
    """ส่งแจ้งเตือนไปยัง webhook/telegram ตามค่าที่ตั้ง (DB > config.toml)."""

    def __init__(self, config: NotifierConfig, db: Database | None = None) -> None:
        """ผูก notifier กับ config; db ให้อ่านค่า merged (เปลี่ยนได้ผ่าน UI ไม่ต้อง restart)."""

        self._config = config
        self._db = db

    async def _resolved(self) -> NotifierConfig:
        """คืนค่า config หลัง merge DB (ถ้ามี db) — ใช้ค่าล่าสุดทุกครั้งที่ส่ง."""

        if self._db is None:
            return self._config
        return await notifier_settings.load_notifiers(self._db, self._config)

    async def send(self, payload: dict[str, Any], channels: list[str] | None = None) -> list[str]:
        """ส่ง payload ไป channel ที่ตั้งค่า (และเปิดอยู่); คืนชื่อ channel ที่ลองส่ง.

        Args:
            payload: ข้อมูล alert ที่จะส่ง.
            channels: เฉพาะ channel ที่ส่ง (เช่น ["webhook"]) — ว่าง/None = ส่งทุก channel ที่ตั้งค่า.
        """

        cfg = await self._resolved()
        sent: list[str] = []
        wh = cfg.webhook or {}
        if (
            (channels is None or "webhook" in channels)
            and wh.get("enabled", True)
            and (wh.get("url") or "").strip()
        ):
            await self._post_webhook(str(wh["url"]), payload)
            sent.append("webhook")
        tg = cfg.telegram or {}
        if (
            (channels is None or "telegram" in channels)
            and tg.get("enabled", True)
            and (tg.get("bot_token") or "").strip()
            and (tg.get("chat_id") or "").strip()
        ):
            await self._post_telegram(str(tg["bot_token"]), str(tg["chat_id"]), payload)
            sent.append("telegram")
        return sent

    async def _post_webhook(self, url: str, payload: dict[str, Any]) -> None:
        """POST JSON ไป webhook (ไม่ raise — แค่ log ไว้เฉยๆ กันพัง ingest)."""

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=payload)
        except (httpx.HTTPError, OSError):
            pass

    async def _post_telegram(self, bot_token: str, chat_id: str, payload: dict[str, Any]) -> None:
        """ส่งข้อความไป Telegram (สร้าง text จาก payload)."""

        text = f"🔔 Alert {payload.get('host_id')} {payload.get('metric')} = {payload.get('value')} (เกิน {payload.get('threshold')})"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
        except (httpx.HTTPError, OSError):
            pass
