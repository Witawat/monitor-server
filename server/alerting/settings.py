"""ค่า notifier (webhook/telegram) — merge: DB (state_kv) เหนือกว่า config.toml.

ผู้ใช้ตั้งค่าผ่าน WebUI → เก็บใน DB (`state_kv["notifiers"]`) ไม่ต้อง restart;
config.toml เดิมยังเป็นค่าเริ่มต้น (fallback) ถ้ายังไม่ได้ตั้งผ่าน UI.
"""

from __future__ import annotations

import json
from typing import Any

from server.config import NotifierConfig
from server.storage.db import Database

SETTINGS_KEY = "notifiers"

_WEBHOOK_FIELDS = ("url", "enabled")
_TELEGRAM_FIELDS = ("bot_token", "chat_id", "enabled")


def _channel_fields(channel: str) -> tuple[str, ...]:
    """field ที่รับ/เก็บของแต่ละช่องทาง."""

    return _WEBHOOK_FIELDS if channel == "webhook" else _TELEGRAM_FIELDS


def _as_bool(value: Any) -> bool:
    """แปลงค่าเป็น bool อย่างปลอดภัย (รับ bool/int/str 'true'/'false')."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "on")


async def _read_db(db: Database) -> dict[str, dict[str, Any]]:
    """อ่านค่า notifier จาก DB ({} ถ้ายังไม่เคยตั้ง) + กรองให้เป็น dict ต่อช่อง."""

    raw = await db.kv_get(SETTINGS_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for ch in ("webhook", "telegram"):
        chv = data.get(ch)
        if isinstance(chv, dict):
            cleaned[ch] = chv
    return cleaned


def _default_enabled(channel: str, merged: dict[str, Any]) -> bool:
    """enabled เริ่มต้น: เปิดเมื่อค่าจำเป็นครบ (ยังไม่เคยตั้งค่าผ่าน UI)."""

    if channel == "webhook":
        return bool((merged.get("url") or "").strip())
    return bool((merged.get("bot_token") or "").strip() and (merged.get("chat_id") or "").strip())


async def load_notifiers(db: Database | None, base: NotifierConfig) -> NotifierConfig:
    """merge ค่า notifier: DB (ถ้าตั้งไว้) เหนือกว่า config.toml + resolve enabled.

    Args:
        db: ถ้ามี จะอ่านค่า DB ทับ config; None = ใช้ config ตรง ๆ (test/fallback).
    """

    raw = await _read_db(db) if db else {}
    channels: dict[str, dict[str, Any]] = {}
    for ch, fields in (("webhook", _WEBHOOK_FIELDS), ("telegram", _TELEGRAM_FIELDS)):
        base_ch = dict(base.webhook or {}) if ch == "webhook" else dict(base.telegram or {})
        db_ch = raw.get(ch) or {}
        merged = dict(base_ch)
        for k in fields:
            if k not in db_ch:
                continue
            v = db_ch[k]
            merged[k] = _as_bool(v) if k == "enabled" else v
        if "enabled" not in merged:
            merged["enabled"] = _default_enabled(ch, merged)
        channels[ch] = merged
    return NotifierConfig(webhook=channels["webhook"], telegram=channels["telegram"])


async def merge_notifiers(db: Database, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """merge ค่าใหม่ (จาก UI) ทับค่าเดิมใน DB — ไม่เขียน (ใช้ validate ก่อน save)."""

    current = await _read_db(db)
    for ch, fields in (("webhook", _WEBHOOK_FIELDS), ("telegram", _TELEGRAM_FIELDS)):
        incoming = data.get(ch)
        if not isinstance(incoming, dict):
            continue
        cur = dict(current.get(ch) or {})
        for k in fields:
            if k not in incoming:
                continue
            v = incoming[k]
            cur[k] = _as_bool(v) if k == "enabled" else str(v or "")
        current[ch] = cur
    return current


async def save_merged(db: Database, merged: dict[str, dict[str, Any]]) -> None:
    """เขียนค่า merged ทั้งหมดลง DB."""

    await db.kv_set(SETTINGS_KEY, json.dumps(merged, ensure_ascii=False))


async def effective_notifiers(db: Database, base: NotifierConfig) -> dict[str, dict[str, Any]]:
    """คืนค่า for UI: ค่าจริง + enabled + configured (ค่าจำเป็นครบไหม)."""

    cfg = await load_notifiers(db, base)

    def configured(channel: str, c: dict[str, Any]) -> bool:
        if channel == "webhook":
            return bool((c.get("url") or "").strip())
        return bool((c.get("bot_token") or "").strip() and (c.get("chat_id") or "").strip())

    wh = cfg.webhook or {}
    tg = cfg.telegram or {}
    return {
        "webhook": {
            "url": str(wh.get("url") or ""),
            "enabled": bool(wh.get("enabled")),
            "configured": configured("webhook", wh),
        },
        "telegram": {
            "bot_token": str(tg.get("bot_token") or ""),
            "chat_id": str(tg.get("chat_id") or ""),
            "enabled": bool(tg.get("enabled")),
            "configured": configured("telegram", tg),
        },
    }
