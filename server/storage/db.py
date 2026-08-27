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


def _json_to_dict(value: Any) -> dict[str, Any]:
    """พาร์ส JSON เป็น dict; คืน {} ถ้าไม่ใช่ dict (กันค่าขยะ)."""

    try:
        data = json.loads(value) if value else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _json_to_list(value: Any) -> list[dict[str, Any]]:
    """พาร์ส JSON เป็น list; คืน [] ถ้าไม่ใช่ list."""

    try:
        data = json.loads(value) if value else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []

# คอลัมน์ metric ที่เก็บใน rollup (เฉลี่ยต่อ bucket) — ตรงกับตาราง metrics
_ROLLUP_COLUMNS = [
    "cpu_percent",
    "load1",
    "load5",
    "load15",
    "mem_total",
    "mem_used",
    "mem_percent",
    "swap_total",
    "swap_used",
    "uptime",
    "procs",
]

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

CREATE TABLE IF NOT EXISTS port_samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id TEXT NOT NULL,
    ts      INTEGER NOT NULL,
    port    INTEGER NOT NULL,
    name    TEXT NOT NULL DEFAULT '',
    up      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_port_host_ts ON port_samples(host_id, ts);

CREATE TABLE IF NOT EXISTS disk_io_samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id     TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    device      TEXT NOT NULL DEFAULT '',
    read_bytes  INTEGER NOT NULL DEFAULT 0,
    write_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_diskio_host_ts ON disk_io_samples(host_id, ts);

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

CREATE TABLE IF NOT EXISTS login_attempts (
    ip TEXT NOT NULL,
    ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ts ON login_attempts(ts);

CREATE TABLE IF NOT EXISTS audit_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    action TEXT NOT NULL,
    ip     TEXT,
    detail TEXT,
    ok     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


class Database:
    """Async access layer สำหรับตาราง hosts/metrics/disk/net ใน SQLite."""

    def __init__(self, path: str | Path, rollup_intervals: list[str] | None = None) -> None:
        """สร้าง Database ชี้ไฟล์ .db (ยังไม่เปิด connection จนกว่าจะ connect())."""

        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._rollup_intervals = rollup_intervals or []

    async def connect(self) -> None:
        """เปิด connection + เปิด WAL mode + สร้าง schema ถ้ายังไม่มี."""

        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_SCHEMA)
        await self._migrate()
        await self._ensure_rollup_tables()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """ย้าย schema เก่า: เพิ่มคอลัมน์ tags / desired_config ถ้า DB เดิมยังไม่มี."""

        cur = await self._require().execute("PRAGMA table_info(hosts)")
        cols = {row["name"] for row in await cur.fetchall()}
        if "tags" not in cols:
            await self._require().execute(
                "ALTER TABLE hosts ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
            )
        if "desired_config" not in cols:
            await self._require().execute(
                "ALTER TABLE hosts ADD COLUMN desired_config TEXT NOT NULL DEFAULT '{}'"
            )
        # columns เพิ่ม (Chunk B) — ตรวจ/เพิ่มเฉพาะที่ขาด
        mcur = await self._require().execute("PRAGMA table_info(metrics)")
        metric_cols = [r["name"] for r in await mcur.fetchall()]
        metric_adds = {
            "cpu_cores": "INTEGER NOT NULL DEFAULT 0",
            "host_info": "TEXT NOT NULL DEFAULT '{}'",
            "top_process": "TEXT NOT NULL DEFAULT '[]'",
            "nic_status": "TEXT NOT NULL DEFAULT '[]'",
            "process_detail": "TEXT NOT NULL DEFAULT '[]'",
        }
        for col, decl in metric_adds.items():
            if col not in metric_cols:
                await self._require().execute(f"ALTER TABLE metrics ADD COLUMN {col} {decl}")
        if set(metric_adds) - set(metric_cols):
            await self._require().commit()

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

    async def get_desired_config(self, host_id: str) -> dict[str, Any]:
        """คืน remote config ที่ตั้งผ่าน UI ต่อ host (ว่าง = ยังไม่ตั้ง)."""

        cur = await self._require().execute(
            "SELECT desired_config FROM hosts WHERE host_id = ?", (host_id,)
        )
        row = await cur.fetchone()
        if row is None or not row["desired_config"]:
            return {}
        try:
            data = json.loads(row["desired_config"])
            return cast(dict[str, Any], data)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def set_desired_config(self, host_id: str, config: dict[str, Any]) -> None:
        """บันทึก remote config ต่อ host (upsert desired_config)."""

        await self._require().execute(
            "UPDATE hosts SET desired_config = ? WHERE host_id = ?",
            (json.dumps(config), host_id),
        )
        await self._require().commit()

    async def get_desired_config_by_token(self, token: str) -> dict[str, Any]:
        """อ่าน remote config ตาม token (agent ใช้ pull ทั้งคอนฟิกตอน push)."""

        cur = await self._require().execute(
            "SELECT desired_config FROM hosts WHERE token = ?", (token,)
        )
        row = await cur.fetchone()
        if row is None or not row["desired_config"]:
            return {}
        try:
            data = json.loads(row["desired_config"])
            return cast(dict[str, Any], data)
        except (json.JSONDecodeError, TypeError):
            return {}

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

    # ── login rate limit + audit log (กัน brute-force, persist ข้าม restart) ──

    async def record_login_attempt(self, ip: str) -> None:
        """บันทึกความพยายาม login (ใช้คำนวณ rate limit ต่อ IP + รวมทุก IP)."""

        await self._require().execute(
            "INSERT INTO login_attempts (ip, ts) VALUES (?, ?)", (ip, time.time())
        )
        await self._require().commit()

    async def count_login_attempts(self, ip: str, since: float) -> int:
        """นับความพยายาม login ของ IP หนึ่ง ภายใน window (sliding)."""

        cur = await self._require().execute(
            "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND ts >= ?", (ip, since)
        )
        row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def count_login_attempts_all(self, since: float) -> int:
        """นับความพยายาม login รวมทุก IP (กัน botnet ที่กระจายหลาย IP)."""

        cur = await self._require().execute(
            "SELECT COUNT(*) AS n FROM login_attempts WHERE ts >= ?", (since,)
        )
        row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def prune_login_attempts(self, before: float) -> None:
        """ลบ record login ที่เก่ากว่า window (กันตารางโต)."""

        await self._require().execute("DELETE FROM login_attempts WHERE ts < ?", (before,))
        await self._require().commit()

    async def add_audit(self, action: str, ip: str | None = None, detail: str | None = None, ok: bool = False) -> None:
        """บันทึกเหตุการณ์ (login สำเร็จ/ล้มเหลว/ถูกจำกัด) ลง audit log."""

        await self._require().execute(
            "INSERT INTO audit_log (ts, action, ip, detail, ok) VALUES (?, ?, ?, ?, ?)",
            (time.time(), action, ip, detail, 1 if ok else 0),
        )
        await self._require().commit()

    async def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        """คืน audit log ล่าสุด (ใหม่ก่อน)."""

        cur = await self._require().execute(
            "SELECT id, ts, action, ip, detail, ok FROM audit_log ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def prune_audit(self, before: float) -> None:
        """ลบ audit log ที่เก่ากว่า retention (audit_keep_days)."""

        await self._require().execute("DELETE FROM audit_log WHERE ts < ?", (before,))
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
            snap.cpu_cores,
            json.dumps(
                {
                    "os_name": snap.host_info.os_name,
                    "os_version": snap.host_info.os_version,
                    "arch": snap.host_info.arch,
                    "kernel": snap.host_info.kernel,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                [
                    {"pid": p.pid, "name": p.name, "cpu_percent": p.cpu_percent, "mem_percent": p.mem_percent}
                    for p in snap.top_process
                ],
                ensure_ascii=False,
            ),
            json.dumps(
                [{"iface": n.iface, "up": n.up, "ip": n.ip, "mac": n.mac} for n in snap.nic_status],
                ensure_ascii=False,
            ),
            json.dumps(
                [
                    {"name": p.name, "pid": p.pid, "cpu_percent": p.cpu_percent, "mem_percent": p.mem_percent}
                    for p in snap.process_detail
                ],
                ensure_ascii=False,
            ),
        )

    async def insert_snapshot(self, snap: Snapshot) -> None:
        """เขียน snapshot หนึ่งจุดลงตาราง metrics + disk/net แล้ว commit ครั้งเดียว."""

        conn = self._require()
        await conn.execute(
            """
            INSERT INTO metrics (
                host_id, ts, cpu_percent, load1, load5, load15,
                mem_total, mem_used, mem_percent, swap_total, swap_used,
                uptime, procs, cpu_cores, host_info, top_process, nic_status, process_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        for p in snap.ports:
            await conn.execute(
                """
                INSERT INTO port_samples (host_id, ts, port, name, up)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snap.host_id, snap.ts, p.port, p.name, 1 if p.up else 0),
            )
        for dio in snap.disk_io:
            await conn.execute(
                """
                INSERT INTO disk_io_samples (host_id, ts, device, read_bytes, write_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snap.host_id, snap.ts, dio.device, dio.read_bytes, dio.write_bytes),
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
                    uptime, procs, cpu_cores, host_info, top_process, nic_status, process_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            for p in snap.ports:
                await conn.execute(
                    """
                    INSERT INTO port_samples (host_id, ts, port, name, up)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snap.host_id, snap.ts, p.port, p.name, 1 if p.up else 0),
                )
            for dio in snap.disk_io:
                await conn.execute(
                    """
                    INSERT INTO disk_io_samples (host_id, ts, device, read_bytes, write_bytes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snap.host_id, snap.ts, dio.device, dio.read_bytes, dio.write_bytes),
                )
        await conn.commit()

    # ── query ──

    async def list_hosts(self, online_only: bool = False, timeout_sec: int = 60) -> list[dict[str, Any]]:
        """คืนรายชื่อ host พร้อม summary ล่าสุด + สถานะ online/offline."""

        cutoff = int(time.time()) - timeout_sec
        conn = self._require()
        rows = await conn.execute_fetchall(
            "SELECT host_id, hostname, platform, tags, desired_config, first_seen, last_seen FROM hosts ORDER BY hostname"
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            h = dict(r)
            online = h["last_seen"] >= cutoff
            if online_only and not online:
                continue
            h["online"] = online
            h["tags"] = json.loads(h["tags"] or "[]")
            h["desired_config"] = json.loads(h["desired_config"] or "{}")
            h["summary"] = await self._latest_summary(h["host_id"])
            result.append(h)
        return result

    async def get_host(self, host_id: str, timeout_sec: int = 60) -> dict[str, Any] | None:
        """คืน detail host เดียว + snapshot ล่าสุด (None ถ้าไม่พบ)."""

        cur = await self._require().execute(
            "SELECT host_id, hostname, platform, tags, desired_config, first_seen, last_seen FROM hosts WHERE host_id = ?",
            (host_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        h = dict(row)
        h["online"] = h["last_seen"] >= (int(time.time()) - timeout_sec)
        h["tags"] = json.loads(h["tags"] or "[]")
        h["desired_config"] = json.loads(h["desired_config"] or "{}")
        h["summary"] = await self._latest_summary(host_id)
        h["services"] = await self.latest_services(host_id)
        h["ports"] = await self.latest_ports(host_id)
        return h

    async def set_host_tags(self, host_id: str, tags: list[str]) -> bool:
        """ตั้ง tags ของ host; คืน True ถ้า host มีอยู่."""

        cur = await self._require().execute(
            "UPDATE hosts SET tags = ? WHERE host_id = ?",
            (json.dumps(tags), host_id),
        )
        await self._require().commit()
        return cur.rowcount > 0

    async def set_host_name(self, host_id: str, hostname: str) -> bool:
        """แก้ชื่อ hostname ที่แสดงใน UI; คืน True ถ้า host มีอยู่."""

        cur = await self._require().execute(
            "UPDATE hosts SET hostname = ? WHERE host_id = ?",
            (hostname, host_id),
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

    async def latest_ports(self, host_id: str) -> list[dict[str, Any]]:
        """คืนสถานะ port ล่าสุดของ host (ชุด ts ล่าสุดเท่านั้น)."""

        cur = await self._require().execute(
            """
            SELECT port, name, up FROM port_samples WHERE host_id = ? AND ts =
                (SELECT MAX(ts) FROM port_samples WHERE host_id = ?)
            ORDER BY port
            """,
            (host_id, host_id),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def _latest_summary(self, host_id: str) -> dict[str, Any]:
        """คืน snapshot ล่าสุดของ host (cpu/mem/disk/uptime) เพื่อการ์ด fleet."""

        conn = self._require()
        cur = await conn.execute(
            """
            SELECT cpu_percent, mem_percent, mem_total, mem_used, uptime,
                   cpu_cores, host_info, top_process, nic_status, process_detail
            FROM metrics WHERE host_id = ? ORDER BY ts DESC LIMIT 1
            """,
            (host_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return {"cpu_percent": 0.0, "mem_percent": 0.0, "uptime": 0}
        d = dict(row)
        d["host_info"] = _json_to_dict(d.get("host_info"))
        d["top_process"] = _json_to_list(d.get("top_process"))
        d["nic_status"] = _json_to_list(d.get("nic_status"))
        d["process_detail"] = _json_to_list(d.get("process_detail"))
        d["disk_percent"] = await self._latest_disk_percent(host_id)
        d["disk_total"] = await self._latest_disk_total(host_id)
        d["net_rx"], d["net_tx"] = await self._latest_net_rate(host_id)
        d["disk_io_rate"] = await self._latest_disk_io_rate(host_id)
        d["trend"] = await self._recent_cpu_trend(host_id)
        d["services_down"] = await self._recent_services_down(host_id)
        return d

    async def _recent_services_down(self, host_id: str) -> list[str]:
        """คืนรายชื่อ service ที่หยุดใน snapshot ล่าสุด (สำหรับเตือนในการ์ด Fleet)."""

        rows = list(
            await self._require().execute_fetchall(
                "SELECT name FROM service_samples WHERE host_id = ? AND up = 0 "
                "AND ts = (SELECT MAX(ts) FROM service_samples WHERE host_id = ?) ORDER BY name",
                (host_id, host_id),
            )
        )
        return [str(r["name"]) for r in rows]

    async def _recent_cpu_trend(self, host_id: str, limit: int = 24) -> list[float]:
        """คืน cpu_percent ย้อนหลัง ~24 จุด ใช้ทำ sparkline ในการ์ด Fleet (ไม่ดัน payload ใหญ่)."""

        rows = list(
            await self._require().execute_fetchall(
                "SELECT cpu_percent FROM metrics WHERE host_id = ? ORDER BY ts DESC LIMIT ?",
                (host_id, limit),
            )
        )
        return [float(r["cpu_percent"]) for r in reversed(rows)]

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

    async def _latest_disk_io_rate(self, host_id: str) -> dict[str, float]:
        """คำนวณ disk I/O rate (read/write bytes/s) จาก 2 จุดล่าสุด (default 0)."""

        rows = list(
            await self._require().execute_fetchall(
                """
                SELECT ts, SUM(read_bytes) AS rd, SUM(write_bytes) AS wr
                FROM disk_io_samples WHERE host_id = ?
                GROUP BY ts ORDER BY ts DESC LIMIT 2
                """,
                (host_id,),
            )
        )
        if len(rows) < 2:
            return {"read_bps": 0.0, "write_bps": 0.0}
        newest, prev = rows[0], rows[1]
        dt = int(newest["ts"]) - int(prev["ts"])
        if dt <= 0:
            return {"read_bps": 0.0, "write_bps": 0.0}
        read_rate = max(0, (int(newest["rd"]) - int(prev["rd"]))) / dt
        write_rate = max(0, (int(newest["wr"]) - int(prev["wr"]))) / dt
        return {"read_bps": read_rate, "write_bps": write_rate}

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
        """คืน time-series ต่อ metric ภายใน range (rollup สำหรับช่วงกว้าง)."""

        cols = [METRIC_COLUMNS[m] for m in metric_names if m in METRIC_COLUMNS]
        if not cols:
            return {}
        start_ts = int(time.time()) - range_sec
        conn = self._require()

        # range ที่กว้าง → ลองอ่านจาก rollup table ก่อน (ถ้ายังไม่มี ค่อย fallback raw)
        if range_sec > 7200:
            chosen = self._choose_rollup(range_sec)
            if chosen is not None:
                name, sec = chosen
                rolled = await self.get_rolled_series(host_id, sec, name, start_ts, metric_names)
                if rolled:
                    return rolled

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

    def _choose_rollup(self, range_sec: int, target_points: int = 96) -> tuple[str, int] | None:
        """เลือก interval rollup ที่เหมาะกับ range (ละเอียดสุดที่จุดไม่เกิน target)."""

        candidates: list[tuple[str, int]] = []
        for name in self._rollup_intervals:
            sec = self._interval_seconds(name)
            if sec and sec < range_sec:
                candidates.append((name, sec))
        if not candidates:
            return None
        for name, sec in candidates:
            if range_sec // sec <= target_points:
                return name, sec
        return candidates[-1]  # ถ้าละเอียดเกินไปทุกตัว ใช้ตัวหยาบสุด

    @staticmethod
    def _interval_seconds(name: str) -> int:
        """แปลงชื่อ interval เช่น '5m'/'1h' เป็นวินาที (0 ถ้าไม่รู้จัก)."""

        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if len(name) < 2 or name[-1] not in mult:
            return 0
        try:
            return int(name[:-1]) * mult[name[-1]]
        except ValueError:
            return 0

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

    # ── rollup ──

    @staticmethod
    def _safe_interval(name: str) -> str:
        """ทำชื่อ interval ให้ปลอดภัยสำหรับเป็นชื่อตาราง."""

        import re

        return re.sub(r"[^a-z0-9]", "_", name)

    async def _ensure_rollup_tables(self) -> None:
        """สร้างตาราง rollup ต่อ interval + ตาราง rollup_state."""

        conn = self._require()
        for name in self._rollup_intervals:
            table = f"rollup_{self._safe_interval(name)}"
            cols = ", ".join(f"{c} REAL NOT NULL DEFAULT 0" for c in _ROLLUP_COLUMNS)
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    bucket INTEGER NOT NULL,
                    host_id TEXT NOT NULL,
                    {cols},
                    PRIMARY KEY (bucket, host_id)
                )
                """
            )
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_host ON {table}(host_id, bucket)"
            )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rollup_state (
                interval TEXT NOT NULL,
                host_id   TEXT NOT NULL,
                last_bucket INTEGER NOT NULL,
                PRIMARY KEY (interval, host_id)
            )
            """
        )

    async def _rollup_last_bucket(self, interval_name: str, host_id: str) -> int:
        """คืน bucket ล่าสุดที่ rollup ไปแล้วของ host (0 ถ้ายังไม่เคย)."""

        cur = await self._require().execute(
            "SELECT last_bucket FROM rollup_state WHERE interval = ? AND host_id = ?",
            (interval_name, host_id),
        )
        row = await cur.fetchone()
        return int(row["last_bucket"]) if row else 0

    async def _set_rollup_last_bucket(self, interval_name: str, host_id: str, bucket: int) -> None:
        """บันทึก bucket ล่าสุดที่ rollup ไปแล้ว."""

        await self._require().execute(
            """
            INSERT INTO rollup_state (interval, host_id, last_bucket) VALUES (?, ?, ?)
            ON CONFLICT(interval, host_id) DO UPDATE SET last_bucket = excluded.last_bucket
            """,
            (interval_name, host_id, bucket),
        )
        await self._require().commit()

    async def aggregate_rollup(self, interval_sec: int, interval_name: str, now: int | None = None) -> int:
        """รวม raw metrics เป็น bucket ในตาราง rollup; คืนจำนวน bucket ที่เขียน.

        Notes:
            ประมวลผลเฉพาะ bucket ที่ปิดสมบูรณ์ (จบก่อน now-interval_sec) และยัง
            ไม่เคย rollup — ใช้ rollup_state กันทำงานซ้ำทุกครั้ง.
        """
        if not self._rollup_intervals or interval_name not in self._rollup_intervals:
            return 0
        now = now or int(time.time())
        table = f"rollup_{self._safe_interval(interval_name)}"
        conn = self._require()
        hosts = await conn.execute_fetchall("SELECT host_id FROM hosts")
        cols = ", ".join(f"AVG({c}) AS {c}" for c in _ROLLUP_COLUMNS)
        total = 0
        for h in hosts:
            host_id = str(h["host_id"])
            last = await self._rollup_last_bucket(interval_name, host_id)
            # last เป็น bucket ขอบบนที่ rollup ไปแล้ว (floor(ts/interval)*interval) —
            # เริ่มที่ last (ไม่ +interval) กันตกขอบ 1 จุดตรงจุดตัด bucket ใหม่
            start_ts = last if last else 0
            end_ts = ((now - interval_sec) // interval_sec) * interval_sec + interval_sec
            if start_ts > end_ts:
                continue
            rows = list(
                await conn.execute_fetchall(
                    f"""
                    SELECT (ts / ?) * ? AS bucket, {cols}
                    FROM metrics WHERE host_id = ? AND ts > ? AND ts <= ?
                    GROUP BY bucket ORDER BY bucket
                    """,
                    (interval_sec, interval_sec, host_id, start_ts, end_ts),
                )
            )
            if not rows:
                continue
            max_bucket = int(rows[0]["bucket"])
            for r in rows:
                bucket = int(r["bucket"])
                vals = [float(r[col] if r[col] is not None else 0) for col in _ROLLUP_COLUMNS]
                placeholders = ", ".join(["?"] * (len(_ROLLUP_COLUMNS) + 2))
                await conn.execute(
                    f"INSERT OR REPLACE INTO {table} (bucket, host_id, {', '.join(_ROLLUP_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    (bucket, host_id, *vals),
                )
                max_bucket = max(max_bucket, bucket)
            total += len(rows)
            await self._set_rollup_last_bucket(interval_name, host_id, max_bucket)
        await conn.commit()
        return total

    async def get_rolled_series(
        self, host_id: str, interval_sec: int, interval_name: str, start_ts: int, metric_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """คืน series จากตาราง rollup (ว่างถ้ายังไม่มีข้อมูล rollup)."""

        table = f"rollup_{self._safe_interval(interval_name)}"
        cols = [METRIC_COLUMNS[m] for m in metric_names if m in METRIC_COLUMNS]
        if not cols:
            return {}
        rows = await self._require().execute_fetchall(
            f"SELECT bucket, {', '.join(cols)} FROM {table} "
            "WHERE host_id = ? AND bucket >= ? ORDER BY bucket",
            (host_id, start_ts),
        )
        if not rows:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for m in metric_names:
            col = METRIC_COLUMNS.get(m)
            if col is None or col not in cols:
                continue
            result[m] = {
                "unit": METRIC_UNITS.get(m, ""),
                "points": [[int(r["bucket"]), float(r[col])] for r in rows],
            }
        return result

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
        await conn.execute("DELETE FROM port_samples WHERE host_id = ?", (host_id,))
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
        """เติม rules เริ่มต้นจาก config ลง DB ครั้งเดียว (กัน seed ซ้ำ).

        Notes:
            ใช้ flag `rules_seeded` ใน state_kv ตัดสินใจ — ไม่ใช่แค่นับกฎ
            (กันกรณีผู้ใช้ลบกฎหมดแล้ว restart → กฎ default เด้งกลับมา).
            - มี flag แล้ว → ไม่เติมอีก (เคารพการลบของผู้ใช้)
            - ยังไม่มี flag แต่มีกฎอยู่แล้ว (install เก่า) → ตั้ง flag ไม่ทับกฎเดิม
            - ยังไม่มี flag + ไม่มีกฎ → เติมกฎจาก config + ตั้ง flag
        """

        if await self.kv_get("rules_seeded") is not None:
            return 0
        if await self._rule_count() > 0:
            # install เดิม — มีกฎอยู่แล้ว (ไม่ได้มาจากการ seed ครั้งนี้) → ไม่ทับ แค่ตั้ง flag
            await self.kv_set("rules_seeded", "1")
            return 0
        created = 0
        for rule in rules:
            await self.create_rule(rule)
            created += 1
        await self.kv_set("rules_seeded", "1")
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

    async def count_unacked_history(self) -> int:
        """นับ alert ที่ยังไม่ ack (ใช้แสดง badge บน menu)."""

        cur = await self._require().execute("SELECT COUNT(*) AS n FROM alert_history WHERE ack = 0")
        row = await cur.fetchone()
        return int(row["n"]) if row is not None else 0

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
        await conn.execute("DELETE FROM port_samples WHERE ts < ?", (cutoff,))
        await conn.commit()
        return cur.rowcount
