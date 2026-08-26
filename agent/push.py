"""ส่ง batch ไป server (urllib stdlib) + retry/backoff + queue เมื่อ offline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from shared.metric import HEADER_TOKEN, INGEST_PATH

_TIMEOUT_SEC = 10


class PushQueue:
    """Persistent queue ของ snapshot ที่ยังส่งไม่ได้ (กันข้อมูลหายตอน offline)."""

    def __init__(self, path: str | Path) -> None:
        """สร้าง queue ชี้ไฟล์ JSON สำหรับเก็บข้อมูลค้าง."""

        self._path = Path(path)

    def enqueue(self, items: list[dict[str, Any]]) -> None:
        """ต่อท้ายรายการเข้า queue (สร้างไฟล์ถ้ายังไม่มี)."""

        current = self._read()
        current.extend(items)
        self._write(current)

    def pending(self) -> list[dict[str, Any]]:
        """คืนรายการทั้งหมดที่ค้างอยู่ (ไม่ลบ)."""

        return self._read()

    def clear(self) -> None:
        """ล้าง queue ทั้งหมด."""

        self._write([])

    def count(self) -> int:
        """จำนวนรายการที่ค้าง."""

        return len(self._read())

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items), encoding="utf-8")
        tmp.replace(self._path)


class Backoff:
    """Exponential backoff — delay = base * factor**attempt, capped ที่ max."""

    def __init__(self, base: float = 2.0, factor: float = 2.0, max_delay: float = 300.0) -> None:
        """กำหนดพารามิเตอร์ backoff."""

        self._base = base
        self._factor = factor
        self._max = max_delay

    def delay(self, attempt: int) -> float:
        """คืนระยะรอ (วินาที) สำหรับ attempt ที่กำหนด (attempt เริ่มที่ 0)."""

        return min(self._base * (self._factor ** attempt), self._max)


def push_batch_status(
    url: str, token: str, batch: list[dict[str, Any]], timeout: float = _TIMEOUT_SEC
) -> tuple[int, dict[str, Any]]:
    """POST batch ไป server; คืน (HTTP status, remote_config).

    Notes:
        remote_config ว่างถ้า server ยังไม่ตั้งค่า config ระยะไกล (หรือ network error
        คืน (0, {})). ฝั่ง agent ใช้ config นี้ปรับ interval/watch/ports โดยไม่ restart.
    """

    data = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + INGEST_PATH,
        data=data,
        headers={"Content-Type": "application/json", HEADER_TOKEN: token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            cfg: dict[str, Any] = {}
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    cfg = parsed.get("config") or {}
            except (json.JSONDecodeError, ValueError):
                pass
            return int(resp.status), cfg
    except urllib.error.HTTPError as exc:
        # อ่าน body ด้วย (เผื่อ 4xx มี message) — คืน config ว่าง
        err_cfg: dict[str, Any] = {}
        try:
            body = exc.read().decode("utf-8", "replace")
            err_cfg = {"_error": body} if body else {}
        except Exception:  # noqa: BLE001
            err_cfg = {}
        return int(exc.code), err_cfg
    except OSError:
        return 0, {}  # offline / connection refused / timeout


def push_batch(url: str, token: str, batch: list[dict[str, Any]], timeout: float = _TIMEOUT_SEC) -> bool:
    """POST batch ไป server; คืน True ถ้าได้รับ 2xx."""

    status, _ = push_batch_status(url, token, batch, timeout)
    return 200 <= status < 300
