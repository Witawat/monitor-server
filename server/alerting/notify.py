"""ตัวส่ง notification — webhook (POST JSON) + Telegram."""

from __future__ import annotations

from typing import Any

import httpx

from server.config import NotifierConfig


class Notifier:
    """ส่งแจ้งเตือนไปยัง webhook/telegram ตามที่ config ตั้งไว้."""

    def __init__(self, config: NotifierConfig) -> None:
        """ผูก notifier กับ config (webhook url + telegram bot/chat)."""

        self._config = config

    async def send(self, payload: dict[str, Any], channels: list[str] | None = None) -> list[str]:
        """ส่ง payload ไป channel ที่ตั้งค่า; คืนชื่อ channel ที่ลองส่ง.

        Args:
            payload: ข้อมูล alert ที่จะส่ง.
            channels: เฉพาะ channel ที่ส่ง (เช่น ["webhook"]) — ว่าง/None = ส่งทุก channel ที่ตั้งค่า.
        """

        sent: list[str] = []
        webhook_url = (self._config.webhook or {}).get("url", "")
        if (channels is None or "webhook" in channels) and webhook_url:
            await self._post_webhook(webhook_url, payload)
            sent.append("webhook")
        bot_token = (self._config.telegram or {}).get("bot_token", "")
        chat_id = (self._config.telegram or {}).get("chat_id", "")
        if (channels is None or "telegram" in channels) and bot_token and chat_id:
            await self._post_telegram(bot_token, chat_id, payload)
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
