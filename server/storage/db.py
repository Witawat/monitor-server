"""Async SQLite access layer — schema, upsert host, insert snapshot, query.

ใช้ aiosqlite ตัวเดียวต่อ Database, เปิด WAL mode, เขียนใน transaction เดียว
กัน lock จาก concurrent request (AGENTS.md / KNOWLEDGE_BASE: SQLite + async).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

import aiosqlite

from shared.metric import Snapshot

# ── mapping metric API -> คอลัมน์/หน่วย ──

METRIC_COLUMNS: dict[str, str] = {
    "cpu_percent": "cpu_percent",
    "load1": "load1",
    "load5": "load5",
    "load15": "load15",
    "memory.total": "mem_total",
    "memory.used": "mem_used",
    "memory.percent": "mem_percent",
    "swap.total": "swap_total",
    "swap.used": "swap_used",
    "uptime": "uptime",
    "procs": "procs",
}

METRIC_UNITS: dict[str, str] = {
    "cpu_percent": "%",
    "memory.percent": "%",
    "load1": "",
    "load5": "",
    "load15": "",
    "memory.total": "bytes",
    "memory.used": "bytes",
    "swap.total": "bytes",
    "swap.used": "bytes",
    "uptime": "sec",
    "procs": "",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hosts (
    host_id   TEXT PRIMARY KEY,
    hostname  TEXT NOT NULL DEFAULT '',
    platform  TEXT NOT NULL DEFAULT '',
    token     TEXT NOT NULL DEFAULT '',
    tags      TEXT NOT NULL DEFAULT '[]',
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hosts_token ON hosts(token);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hosts_token_unique ON hosts(token) WHERE token <> '';

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id     TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    cpu_percent REAL NOT NULL DEFAULT 0,
    load1       REAL NOT NULL DEFAULT 0,
    load5       REAL NOT NULL DEFAULT 0,
    load15      REAL NOT NULL DEFAULT 0,
    mem_total   INTEGER NOT NULL DEFAULT 0,
    mem_used    INTEGER NOT NULL DEFAULT 0,
    mem_percent REAL NOT NULL DEFAULT 0,
    swap_total  INTEGER NOT NULL DEFAULT 0,
    swap_used   INTEGER NOT NULL DEFAULT 0,
    uptime      INTEGER NOT NULL DEFAULT 0,
    procs       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_metrics_host_ts ON metrics(host_id, ts);

CREATE TABLE IF NOT EXISTS disk_samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    mount   TEXT NOT NULL,
    total   INTEGER NOT NULL DEFAULT 0,
    used    INTEGER NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_disk_host_ts ON disk_samples(host_id, ts);

CREATE TABLE IF NOT EXISTS net_samples (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id  TEXT NOT NULL,
    ts       INTEGER NOT NULL,
    iface    TEXT NOT NULL,
    rx_bytes INTEGER NOT NULL DEFAULT 0,
    tx_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_net_host_ts ON net_samples(host_id, ts);

CREATE TABLE IF NOT EXISTS service_samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    name    TEXT NOT NULL,
    up      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_service_host_ts ON service_samples(host_id, ts);

CREATE TABLE IF NOT EXISTS alert_rules (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    host_id   TEXT NOT NULL DEFAULT '',
    metric    TEXT NOT NULL,
    op        TEXT NOT NULL,
    threshold REAL NOT NULL,
    duration  TEXT NOT NULL DEFAULT '5m',
    notify    TEXT NOT NULL DEFAULT '[]',
    enabled   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS alert_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id    INTEGER NOT NULL,
    host_id    TEXT NOT NULL,
    metric     TEXT NOT NULL,
    value      REAL NOT NULL,
    threshold  REAL NOT NULL,
    created_at INTEGER NOT NULL,
    ack        INTEGER NOT NULL DEFAULT 0,
    acked_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_alert_history_host ON alert_history(host_id, created_at);

CREATE TABLE IF NOT EXISTS state_kv (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


class Database:
    """Async access layer สำหรับตาราง hosts/metrics/disk/net ใน SQLite."""

    def __init__(self, path: str | Path) -> None:
        """สร้าง Database ชี้ไฟล์ .db (ยังไม่เปิด connection จนกว่าจะ connect())."""

        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """เปิด connection + เปิด WAL mode + สร้าง schema ถ้ายังไม่มี."""

        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """ย้าย schema เก่า: เพิ่มคอลัมน์ tags ถ้า DB เดิมยังไม่มี."""

        cur = await self._require().execute("PRAGMA table_info(hosts)")
        cols = {row["name"] for row in await cur.fetchall()}
        if "tags" not in cols:
            await self._require().execute(
                "ALTER TABLE hosts ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
            )

    async def close(self) -> None:
        """ปิด connection."""

        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require(self) -> aiosqlite.Connection:
        """คืน connection; fail ถ้ายังไม่ connect."""

        if self._conn is None:
            raise RuntimeError("Database ยังไม่ connect()")
        return self._conn

    # ── host ──

    async def host_by_token(self, token: str) -> dict[str, Any] | None:
        """หาข้อมูล host จาก token (None ถ้าไม่รู้จัก)."""

        cur = await self._require().execute(
            "SELECT host_id, hostname, platform, token FROM hosts WHERE token = ?",
            (token,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def host_exists(self, host_id: str) -> bool:
        """เช็คว่า host_id มีอยู่ในตาราง hosts แล้วหรือยัง."""

        cur = await self._require().execute(
            "SELECT 1 FROM hosts WHERE host_id = ?", (host_id,)
        )
        return await cur.fetchone() is not None

    async def host_has_data(self, host_id: str) -> bool:
        """เช็คว่า host เคยส่ง snapshot (metrics) เข้ามาแล้วหรือยัง."""

        cur = await self._require().execute(
            "SELECT 1 FROM metrics WHERE host_id = ? LIMIT 1", (host_id,)
        )
        return await cur.fetchone() is not None

    # ── generic key-value state ──

    async def kv_get(self, key: str) -> str | None:
        """อ่านค่า state (None ถ้ายังไม่เคยตั้ง)."""

        cur = await self._require().execute(
            "SELECT v FROM state_kv WHERE k = ?", (key,)
        )
        row = await cur.fetchone()
        return str(row["v"]) if row else None

    async def kv_set(self, key: str, value: str) -> None:
        """เขียนค่า state (upsert)."""

        await self._require().execute(
            """
            INSERT INTO state_kv (k, v) VALUES (?, ?)
            ON CONFLICT(k) DO UPDATE SET v = excluded.v
            """,
            (key, value),
        )
        await self._require().commit()

    async def kv_delete(self, key: str) -> None:
        """ลบค่า state."""

        await self._require().execute("DELETE FROM state_kv WHERE k = ?", (key,))
        await self._require().commit()

    async def upsert_host(
        self, host_id: str, hostname: str, platform: str, token: str, now: int | None = None
    ) -> None:
        """สร้าง host ใหม่ หรืออัปเดต last_seen/hostname/platform ของ host เดิม."""

        now = now or int(time.time())
        await self._require().execute(
            """
            INSERT INTO hosts (host_id, hostname, platform, token, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(host_id) DO UPDATE SET
                hostname = excluded.hostname,
                platform = excluded.platform,
                token = excluded.token,
                last_seen = excluded.last_seen
            """,
            (host_id, hostname, platform, token, now, now),
        )
        await self._require().commit()

    # ── snapshot ──

    @staticmethod
    def _metrics_values(snap: Snapshot) -> tuple[object, ...]:
        """คืนค่าการ insert metrics (padding load ให้ครบ 3 ตัวเสมอ)."""

        load = (tuple(snap.load) + (0.0, 0.0, 0.0))[:3]
        return (
            snap.host_id,
            snap.ts,
            snap.cpu_percent,
            *load,
            snap.memory.total,
            snap.memory.used,
            snap.memory.percent,
            snap.swap.total,
            snap.swap.used,
            snap.uptime,
            snap.procs,
        )

    async def insert_snapshot(self, snap: Snapshot) -> None:
        """เขียน snapshot หนึ่งจุดลงตาราง metrics + disk/net แล้ว commit ครั้งเดียว."""

        conn = self._require()
        await conn.execute(
            """
            INSERT INTO metrics (
                host_id, ts, cpu_percent, load1, load5, load15,
                mem_total, mem_used, mem_percent, swap_total, swap_used,
                uptime, procs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._metrics_values(snap),
        )
        for d in snap.disk:
            await conn.execute(
                """
                INSERT INTO disk_samples (host_id, ts, mount, total, used, percent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (snap.host_id, snap.ts, d.mount, d.total, d.used, d.percent),
            )
        for n in snap.net:
            await conn.execute(
                """
                INSERT INTO net_samples (host_id, ts, iface, rx_bytes, tx_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snap.host_id, snap.ts, n.iface, n.rx_bytes, n.tx_bytes),
            )
        for s in snap.services:
            await conn.execute(
                """
                INSERT INTO service_samples (host_id, ts, name, up)
                VALUES (?, ?, ?, ?)
                """,
                (snap.host_id, snap.ts, s.name, 1 if s.up else 0),
            )
        await conn.commit()

    async def insert_batch(self, snaps: list[Snapshot]) -> None:
        """เขียนหลาย snapshot แล้ว commit ครั้งเดียว (atomic ต่อ batch)."""

        conn = self._require()
        for snap in snaps:
            await conn.execute(
                """
                INSERT INTO metrics (
                    host_id, ts, cpu_percent, load1, load5, load15,
                    mem_total, mem_used, mem_percent, swap_total, swap_used,
                    uptime, procs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._metrics_values(snap),
            )
            for d in snap.disk:
                await conn.execute(
                    """
                    INSERT INTO disk_samples (host_id, ts, mount, total, used, percent)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (snap.host_id, snap.ts, d.mount, d.total, d.used, d.percent),
                )
            for n in snap.net:
                await conn.execute(
                    """
                    INSERT INTO net_samples (host_id, ts, iface, rx_bytes, tx_bytes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snap.host_id, snap.ts, n.iface, n.rx_bytes, n.tx_bytes),
                )
            for s in snap.services:
                await conn.execute(
                    """
                    INSERT INTO service_samples (host_id, ts, name, up)
                    VALUES (?, ?, ?, ?)
                    """,
                    (snap.host_id, snap.ts, s.name, 1 if s.up else 0),
                )
        await conn.commit()

    # ── query ──

    async def list_hosts(self, online_only: bool = False, timeout_sec: int = 60) -> list[dict[str, Any]]:
        """คืนรายชื่อ host พร้อม summary ล่าสุด + สถานะ online/offline."""

        cutoff = int(time.time()) - timeout_sec
        conn = self._require()
        rows = await conn.execute_fetchall(
            "SELECT host_id, hostname, platform, tags, first_seen, last_seen FROM hosts ORDER BY hostname"
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            h = dict(r)
            online = h["last_seen"] >= cutoff
            if online_only and not online:
                continue
            h["online"] = online
            h["tags"] = json.loads(h["tags"] or "[]")
            h["summary"] = await self._latest_summary(h["host_id"])
            result.append(h)
        return result

    async def get_host(self, host_id: str, timeout_sec: int = 60) -> dict[str, Any] | None:
        """คืน detail host เดียว + snapshot ล่าสุด (None ถ้าไม่พบ)."""

        cur = await self._require().execute(
            "SELECT host_id, hostname, platform, tags, first_seen, last_seen FROM hosts WHERE host_id = ?",
            (host_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        h = dict(row)
        h["online"] = h["last_seen"] >= (int(time.time()) - timeout_sec)
        h["tags"] = json.loads(h["tags"] or "[]")
        h["summary"] = await self._latest_summary(host_id)
        h["services"] = await self.latest_services(host_id)
        return h

    async def set_host_tags(self, host_id: str, tags: list[str]) -> bool:
        """ตั้ง tags ของ host; คืน True ถ้า host มีอยู่."""

        cur = await self._require().execute(
            "UPDATE hosts SET tags = ? WHERE host_id = ?",
            (json.dumps(tags), host_id),
        )
        await self._require().commit()
        return cur.rowcount > 0

    async def list_all_tags(self) -> list[str]:
        """รวบรวม tags ที่ใช้อยู่ทั้งหมด (ไม่ซ้ำ) สำหรับกรอง fleet."""

        rows = await self._require().execute_fetchall("SELECT tags FROM hosts")
        seen: set[str] = set()
        for r in rows:
            for t in json.loads(r["tags"] or "[]"):
                seen.add(t)
        return sorted(seen)

    async def latest_services(self, host_id: str) -> list[dict[str, Any]]:
        """คืนสถานะ service ล่าสุดของ host (ชุด ts ล่าสุดเท่านั้น)."""

        cur = await self._require().execute(
            """
            SELECT name, up FROM service_samples WHERE host_id = ? AND ts =
                (SELECT MAX(ts) FROM service_samples WHERE host_id = ?)
            ORDER BY name
            """,
            (host_id, host_id),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def _latest_summary(self, host_id: str) -> dict[str, Any]:
        """คืน snapshot ล่าสุดของ host (cpu/mem/disk/uptime) เพื่อการ์ด fleet."""

        conn = self._require()
        cur = await conn.execute(
            """
            SELECT cpu_percent, mem_percent, mem_total, mem_used, uptime
            FROM metrics WHERE host_id = ? ORDER BY ts DESC LIMIT 1
            """,
            (host_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return {"cpu_percent": 0.0, "mem_percent": 0.0, "uptime": 0}
        d = dict(row)
        d["disk_percent"] = await self._latest_disk_percent(host_id)
        d["disk_total"] = await self._latest_disk_total(host_id)
        d["net_rx"], d["net_tx"] = await self._latest_net_rate(host_id)
        return d

    async def _latest_disk_total(self, host_id: str) -> int:
        """คืน total bytes ของ mount แรกใน snapshot ล่าสุด (default 0)."""

        cur = await self._require().execute(
            """
            SELECT total FROM disk_samples WHERE host_id = ?
            ORDER BY ts DESC, id ASC LIMIT 1
            """,
            (host_id,),
        )
        row = await cur.fetchone()
        return int(row["total"]) if row else 0

    async def _latest_net_rate(self, host_id: str) -> tuple[float, float]:
        """คำนวณ net rate (rx/tx bytes/s) จาก 2 จุดล่าสุด (default 0)."""

        rows = list(
            await self._require().execute_fetchall(
                """
                SELECT ts, SUM(rx_bytes) AS rx, SUM(tx_bytes) AS tx
                FROM net_samples WHERE host_id = ?
                GROUP BY ts ORDER BY ts DESC LIMIT 2
                """,
                (host_id,),
            )
        )
        if len(rows) < 2:
            return 0.0, 0.0
        newest, prev = rows[0], rows[1]
        dt = int(newest["ts"]) - int(prev["ts"])
        if dt <= 0:
            return 0.0, 0.0
        rx_rate = max(0, (int(newest["rx"]) - int(prev["rx"]))) / dt
        tx_rate = max(0, (int(newest["tx"]) - int(prev["tx"]))) / dt
        return rx_rate, tx_rate

    async def _latest_disk_percent(self, host_id: str) -> float:
        """คืน disk percent ของ mount แรกใน snapshot ล่าสุด (default 0)."""

        cur = await self._require().execute(
            """
            SELECT percent FROM disk_samples WHERE host_id = ?
            ORDER BY ts DESC, id ASC LIMIT 1
            """,
            (host_id,),
        )
        row = await cur.fetchone()
        return cast(float, row["percent"]) if row else 0.0

    async def get_metrics(
        self, host_id: str, range_sec: int, metric_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """คืน time-series ต่อ metric ภายใน range (bucket เฉลี่ยถ้าช่วงกว้าง)."""

        cols = [METRIC_COLUMNS[m] for m in metric_names if m in METRIC_COLUMNS]
        if not cols:
            return {}
        start_ts = int(time.time()) - range_sec
        conn = self._require()
        rows = await conn.execute_fetchall(
            f"SELECT ts, {', '.join(cols)} FROM metrics "
            "WHERE host_id = ? AND ts >= ? ORDER BY ts",
            (host_id, start_ts),
        )

        bucket = self._pick_bucket(range_sec)
        agg: dict[int, list[list[float]]] = {}
        for r in rows:
            key = r["ts"] // bucket if bucket > 1 else r["ts"]
            agg.setdefault(key, []).append([float(r[c]) for c in cols])

        result: dict[str, dict[str, Any]] = {}
        for idx, m in enumerate(metric_names):
            col = METRIC_COLUMNS.get(m)
            if col is None or col not in cols:
                continue
            if bucket > 1:
                points = [
                    [ts * bucket, self._avg(vals[idx] for vals in group)]
                    for ts, group in sorted(agg.items())
                ]
            else:
                points = [[ts, group[0][idx]] for ts, group in sorted(agg.items())]
            result[m] = {"unit": METRIC_UNITS.get(m, ""), "points": points}
        return result

    async def export_rows(
        self, host_id: str, range_sec: int, metric_names: list[str]
    ) -> list[dict[str, Any]]:
        """คืน raw rows (ts + ค่า metric) สำหรับ export CSV."""

        cols = [METRIC_COLUMNS[m] for m in metric_names if m in METRIC_COLUMNS]
        if not cols:
            return []
        start_ts = int(time.time()) - range_sec
        rows = await self._require().execute_fetchall(
            f"SELECT ts, {', '.join(cols)} FROM metrics "
            "WHERE host_id = ? AND ts >= ? ORDER BY ts",
            (host_id, start_ts),
        )
        return [dict(r) for r in rows]

    @staticmethod
    def _pick_bucket(range_sec: int, target_points: int = 200) -> int:
        """เลือกความกว้าง bucket; 1h ใช้ raw, range ที่กว้างกว่า 2h ค่อย downsample."""

        if range_sec <= 7200:  # 1h-2h ยังแสดงแบบ raw ตาม API.md
            return 1
        return max(1, range_sec // target_points)

    @staticmethod
    def _avg(values: Any) -> float:
        """ค่าเฉลี่ยของ iterable; คืน 0 ถ้าว่าง."""

        vals = list(values)
        return sum(vals) / len(vals) if vals else 0.0

    # ── maintenance ──

    async def delete_host(self, host_id: str) -> bool:
        """ลบ host + metrics + disk/net ทั้งหมด; คืน True ถ้าลบจริง."""

        conn = self._require()
        cur = await conn.execute("SELECT 1 FROM hosts WHERE host_id = ?", (host_id,))
        if await cur.fetchone() is None:
            return False
        await conn.execute("DELETE FROM metrics WHERE host_id = ?", (host_id,))
        await conn.execute("DELETE FROM disk_samples WHERE host_id = ?", (host_id,))
        await conn.execute("DELETE FROM net_samples WHERE host_id = ?", (host_id,))
        await conn.execute("DELETE FROM service_samples WHERE host_id = ?", (host_id,))
        await conn.execute("DELETE FROM alert_history WHERE host_id = ?", (host_id,))
        await conn.execute("DELETE FROM hosts WHERE host_id = ?", (host_id,))
        await conn.commit()
        return True

    # ── token management ──

    async def set_host_token(self, host_id: str, token: str) -> None:
        """สร้าง/อัปเดต host + ตั้ง token (สร้างแถวให้ถ้ายังไม่มี)."""

        now = int(time.time())
        await self._require().execute(
            """
            INSERT INTO hosts (host_id, hostname, platform, token, first_seen, last_seen)
            VALUES (?, '', '', ?, ?, ?)
            ON CONFLICT(host_id) DO UPDATE SET token = excluded.token
            """,
            (host_id, token, now, now),
        )
        await self._require().commit()

    async def list_tokens(self) -> list[dict[str, Any]]:
        """คืนคู่ (host_id, token) ทั้งหมด."""

        rows = await self._require().execute_fetchall(
            "SELECT host_id, token FROM hosts ORDER BY host_id"
        )
        return [dict(r) for r in rows]

    async def get_token(self, host_id: str) -> str | None:
        """คืน token ของ host (None ถ้าไม่มี/ไม่พบ)."""

        cur = await self._require().execute(
            "SELECT token FROM hosts WHERE host_id = ?", (host_id,)
        )
        row = await cur.fetchone()
        return str(row["token"]) if row else None

    async def revoke_token(self, host_id: str) -> bool:
        """ล้าง token ของ host; คืน True ถ้า host มีอยู่."""

        cur = await self._require().execute(
            "UPDATE hosts SET token = '' WHERE host_id = ?", (host_id,)
        )
        await self._require().commit()
        return cur.rowcount > 0

    # ── alert rules ──

    async def list_rules(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """คืนรายการ alert rules (decode notify เป็น list)."""

        sql = "SELECT * FROM alert_rules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        rows = await self._require().execute_fetchall(sql + " ORDER BY id")
        rules = []
        for r in rows:
            d = dict(r)
            try:
                d["notify"] = json.loads(d["notify"])
            except (json.JSONDecodeError, TypeError):
                d["notify"] = []
            rules.append(d)
        return rules

    async def get_rule(self, rule_id: int) -> dict[str, Any] | None:
        """คืน rule เดียว (None ถ้าไม่พบ)."""

        cur = await self._require().execute(
            "SELECT * FROM alert_rules WHERE id = ?", (rule_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["notify"] = json.loads(d["notify"] or "[]")
        return d

    async def create_rule(self, data: dict[str, Any]) -> int:
        """สร้าง rule; คืน id ใหม่."""

        cur = await self._require().execute(
            """
            INSERT INTO alert_rules (name, host_id, metric, op, threshold, duration, notify, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data.get("host_id", ""),
                data["metric"],
                data["op"],
                data["threshold"],
                data.get("duration", "5m"),
                json.dumps(data.get("notify", [])),
                1 if data.get("enabled", True) else 0,
            ),
        )
        await self._require().commit()
        return int(cur.lastrowid or 0)

    async def update_rule(self, rule_id: int, data: dict[str, Any]) -> bool:
        """แก้ rule; คืน True ถ้ามีอยู่."""

        fields = ["name", "host_id", "metric", "op", "threshold", "duration", "enabled"]
        sets = [f"{f} = ?" for f in fields if f in data]
        if "notify" in data:
            sets.append("notify = ?")
        if not sets:
            return False
        params = []
        for f in fields:
            if f in data:
                value = data[f]
                if f == "enabled":
                    value = 1 if value else 0
                elif f == "threshold":
                    value = float(value)
                params.append(value)
        if "notify" in data:
            params.append(json.dumps(data["notify"]))
        params.append(rule_id)
        cur = await self._require().execute(
            f"UPDATE alert_rules SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        await self._require().commit()
        return cur.rowcount > 0

    async def delete_rule(self, rule_id: int) -> bool:
        """ลบ rule; คืน True ถ้ามีอยู่."""

        cur = await self._require().execute(
            "DELETE FROM alert_rules WHERE id = ?", (rule_id,)
        )
        await self._require().commit()
        return cur.rowcount > 0

    async def seed_rules_from_config(self, rules: list[dict[str, Any]]) -> int:
        """เติม rules จาก config ลง DB ถ้ายังไม่มี rule เลย (กัน config หายไป)."""

        if await self._rule_count() > 0:
            return 0
        created = 0
        for rule in rules:
            await self.create_rule(rule)
            created += 1
        return created

    async def _rule_count(self) -> int:
        cur = await self._require().execute("SELECT COUNT(*) AS n FROM alert_rules")
        row = await cur.fetchone()
        return int(row["n"]) if row is not None else 0

    # ── alert history ──

    async def add_history(
        self, rule_id: int, host_id: str, metric: str, value: float, threshold: float, created_at: int | None = None
    ) -> int:
        """บันทึกประวัติ alert trigger; คืน id."""

        created_at = created_at or int(time.time())
        cur = await self._require().execute(
            """
            INSERT INTO alert_history (rule_id, host_id, metric, value, threshold, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rule_id, host_id, metric, value, threshold, created_at),
        )
        await self._require().commit()
        return int(cur.lastrowid or 0)

    async def list_history(
        self, host_id: str | None = None, rule_id: int | None = None, ack: bool | None = None
    ) -> list[dict[str, Any]]:
        """คืนประวัติ alert (filter host/rule/ack) เรียงใหม่ล่าสุดก่อน."""

        sql = "SELECT * FROM alert_history WHERE 1=1"
        params: list[Any] = []
        if host_id:
            sql += " AND host_id = ?"
            params.append(host_id)
        if rule_id is not None:
            sql += " AND rule_id = ?"
            params.append(rule_id)
        if ack is not None:
            sql += " AND ack = ?"
            params.append(1 if ack else 0)
        sql += " ORDER BY created_at DESC, id DESC"
        rows = await self._require().execute_fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    async def ack_history(self, history_id: int) -> bool:
        """ack ประวัติ; คืน True ถ้ามีอยู่."""

        cur = await self._require().execute(
            "UPDATE alert_history SET ack = 1, acked_at = ? WHERE id = ?",
            (int(time.time()), history_id),
        )
        await self._require().commit()
        return cur.rowcount > 0

    async def retention_cleanup(self, keep_days: int) -> int:
        """ลบ raw metrics เก่ากว่า keep_days วัน; คืนจำนวน row ที่ลบ."""

        if keep_days <= 0:
            return 0
        cutoff = int(time.time()) - keep_days * 86400
        conn = self._require()
        cur = await conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
        await conn.execute("DELETE FROM disk_samples WHERE ts < ?", (cutoff,))
        await conn.execute("DELETE FROM net_samples WHERE ts < ?", (cutoff,))
        await conn.execute("DELETE FROM service_samples WHERE ts < ?", (cutoff,))
        await conn.commit()
        return cur.rowcount
