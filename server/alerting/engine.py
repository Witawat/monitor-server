"""ประเมิน alert rules หลัง ingest — ตรวจจับค่าเกิน threshold ต่อเนื่อง."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from server.alerting.notify import Notifier
from server.config import AppConfig
from server.storage.db import Database
from shared.metric import Snapshot

# metric name -> ฟังก์ชันดึงค่าจาก Snapshot
_METRIC_GETTERS: dict[str, Callable[[Snapshot], float | None]] = {
    "cpu_percent": lambda s: s.cpu_percent,
    "memory.percent": lambda s: s.memory.percent,
    "memory.used": lambda s: float(s.memory.used),
    "memory.total": lambda s: float(s.memory.total),
    "swap.used": lambda s: float(s.swap.used),
    "swap.total": lambda s: float(s.swap.total),
    "load1": lambda s: s.load[0] if len(s.load) > 0 else None,
    "load5": lambda s: s.load[1] if len(s.load) > 1 else None,
    "load15": lambda s: s.load[2] if len(s.load) > 2 else None,
    "disk.percent": lambda s: s.disk[0].percent if s.disk else None,
    "uptime": lambda s: float(s.uptime),
    "procs": lambda s: float(s.procs),
}

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}

_DUR_RE = re.compile(r"^(\d+)([smhd])$")
_DUR_MULT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str) -> int:
    """แปลง duration เช่น '5m'/'1h' เป็นวินาที (default 0 ถ้า parse ไม่ได้)."""

    m = _DUR_RE.match(value.strip())
    if not m:
        return 0
    return int(m.group(1)) * _DUR_MULT[m.group(2)]


def metric_value(snap: Snapshot, metric: str) -> float | None:
    """ดึงค่าของ metric จาก Snapshot (None ถ้า metric ไม่รู้จัก/ไม่มีข้อมูล)."""

    getter = _METRIC_GETTERS.get(metric)
    return getter(snap) if getter else None


class AlertEngine:
    """ตรวจ alert rules ต่อเนื่อง — trigger เมื่อค่าเกิน threshold ครบ duration."""

    def __init__(self, db: Database, config: AppConfig, notifier: Notifier | None = None) -> None:
        """ผูก engine กับ DB + config + notifier (ทดแทนได้ในเทสต์)."""

        self._db = db
        self._config = config
        self._notifier = notifier or Notifier(config.alerting.notifiers)
        self._state: dict[tuple[int, str], tuple[str, int]] = {}

    async def evaluate(self, snapshots: list[Snapshot], now: int | None = None) -> list[dict[str, Any]]:
        """ประเมิน rules กับ snapshot ที่เพิ่งมา; คืนเหตุการณ์ alert ที่ fire.

        ตรรกะ: ค่าเกินเงื่อนไข → จับเวลา (arming); ครบ duration → fire ครั้งเดียว
        แล้ว reset เมื่อค่ากลับปกติ (edge-triggered, ไม่ยิงซ้ำทุก snapshot).
        """
        if not self._config.alerting.enabled:
            return []
        now = now or int(time.time())
        rules = await self._db.list_rules(enabled_only=True)
        events: list[dict[str, Any]] = []
        for rule in rules:
            duration = parse_duration(rule["duration"])
            if duration <= 0:
                continue  # duration ผิด/0 → ข้าม rule (กัน fire ทันที) (L5)
            for snap in snapshots:
                if rule["host_id"] and rule["host_id"] != snap.host_id:
                    continue
                value = metric_value(snap, rule["metric"])
                if value is None:
                    continue
                ok = _OPS[rule["op"]](value, rule["threshold"])
                key = (int(rule["id"]), snap.host_id)
                state = self._state.get(key)
                if not ok:
                    self._state.pop(key, None)
                    continue
                if state is None:
                    self._state[key] = ("arming", now)
                elif state[0] == "arming" and (now - state[1]) >= duration:
                    self._state[key] = ("fired", now)
                    history_id = await self._db.add_history(
                        int(rule["id"]), snap.host_id, rule["metric"], value, rule["threshold"], now
                    )
                    payload = {
                        "id": history_id,
                        "rule_id": int(rule["id"]),
                        "name": rule["name"],
                        "host_id": snap.host_id,
                        "metric": rule["metric"],
                        "value": value,
                        "threshold": rule["threshold"],
                        "op": rule["op"],
                        "created_at": now,
                    }
                    await self._notifier.send(payload)
                    events.append(payload)
        return events
