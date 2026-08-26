"""Entry หลักของ agent — loop collect → push → retry/backoff/queue.

รันผ่าน: `python -m agent.agent --server <URL> --token <TOKEN> --interval 15`
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from agent import collect, selfinstall
from agent.config import AgentConfig, load_config
from agent.push import Backoff, PushQueue, push_batch_status
from shared.metric import snapshot_to_dict

# ── helpers ──

def _default_state_dir() -> Path:
    """ที่เก็บ state (host_id/queue): ข้าง exe ถ้า frozen, ไม่งั้น ~/.monitor-agent.

    Notes:
        เก็บข้าง exe ให้ย้าย/จัดการง่าย (AGENTS.md) — ตรงกับ server exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.home() / ".monitor-agent"


def _flush_queue(queue: PushQueue, url: str, token: str, batch_size: int) -> None:
    """ลองส่งข้อมูลค้างใน queue เป็น chunk (ไม่เกิน batch_size ต่อครั้ง)."""

    pending = queue.pending()
    if not pending:
        return
    ok = True
    for i in range(0, len(pending), batch_size):
        chunk = pending[i : i + batch_size]
        status, _ = push_batch_status(url, token, chunk)
        if not (200 <= status < 300):
            ok = False
            break
    if ok:
        queue.clear()


def run(config: AgentConfig, state_dir: str | Path = "") -> None:
    """วนลูปเก็บ + push ตาม interval; ถ้า offline เก็บเข้า queue + backoff.

    Args:
        config: การตั้งค่า agent (server_url/token/interval).
        state_dir: ไดเรกทอรีเก็บ state (host_id + queue); default ข้าง exe หรือ ~/.monitor-agent.
    """
    base = Path(state_dir) if state_dir else _default_state_dir()
    host_id = collect.host_id(base / "host_id")
    queue = PushQueue(base / "queue.json")
    backoff = Backoff()
    fail_streak = 0

    # ค่าที่แก้ได้จาก remote (server ตั้งผ่าน WebUI) — เก็บเป็น mutable ตัวแปร, ไม่ใช่ config (frozen)
    interval = config.interval
    watch = config.watch
    ports = config.ports
    max_batch = config.max_batch

    def apply_remote(remote: dict[str, Any]) -> None:
        """อัปเดตค่า config จาก remote ที่ server ตั้ง (ไม่ restart)."""

        nonlocal interval, watch, ports, max_batch
        if "interval" in remote:
            try:
                v = int(remote["interval"])
                if v >= 1:
                    interval = v
            except (ValueError, TypeError):
                pass
        if "watch" in remote:
            watch = tuple(n.strip() for n in str(remote["watch"]).split(",") if n.strip())
        if "ports" in remote:
            import agent.config as _cfg

            ports = _cfg._parse_ports(str(remote["ports"]))
        if "max_batch" in remote:
            try:
                v = int(remote["max_batch"])
                if v >= 1:
                    max_batch = v
            except (ValueError, TypeError):
                pass

    while True:
        try:
            snap = collect.snapshot(host_id, watch=watch, ports=list(ports))
            batch: list[dict[str, Any]] = [snapshot_to_dict(snap)]
            status, remote = push_batch_status(config.server_url, config.token, batch)
        except Exception as exc:  # noqa: BLE001 - ไม่ให้ loop ตายเพราะ provider/network พลาดชั่วคราว
            # collect/push ยกเว้น (อ่าน /proc พลาด, psutil พลาด, json พัง) → ข้ามรอบนี้ + backoff
            print(f"[agent] collect/push พลาด: {exc!r}"
                  f" — retry ใน {interval}s")
            fail_streak += 1
            time.sleep(backoff.delay(fail_streak))
            continue

        if status in (401, 403):
            # token/config ผิด — ไม่มีทางหาย อย่า retry ตลอดไป
            raise SystemExit(f"server ตอบ {status} — token ไม่ถูกต้อง ตรวจ config แล้วลองใหม่")
        if 200 <= status < 300:
            fail_streak = 0
            apply_remote(remote)   # ใช้ค่าล่าสุดที่ server ตั้ง (ถ้ามี)
            _flush_queue(queue, config.server_url, config.token, max_batch)
            delay: float = interval
        elif status == 0 or status >= 500 or status == 429:
            # offline / server พลาดชั่วคราว (5xx) / rate-limited → เก็บ queue + backoff
            queue.enqueue(batch)
            fail_streak += 1
            delay = backoff.delay(fail_streak)
        else:
            # 4xx (400/404/...) = client ผิด (URL/body/schema) — อย่าเก็บ queue วนซ้ำ
            # โยนทิ้ง batch นี้ แล้วหน่วงสั้น ๆ และแจ้ง
            print(f"[agent] server ตอบ {status} — batch ถูกละทิ้ง (ไม่ retry)")
            fail_streak += 1
            delay = backoff.delay(fail_streak)
        time.sleep(delay)


def main(argv: list[str] | None = None) -> None:
    """Entry — self-install หรือ รัน loop ตาม config (arg/env/ไฟล์).

    Usage:
        `python -m agent.agent --install --server <URL> --token <T> [--interval 15] [--ports ...] [--watch ...]`
            → เขียน agent.cfg + สร้าง service ให้เอง (Windows NSSM / Linux systemd)
        `python -m agent.agent --uninstall` → ลบ service
        `python -m agent.agent` → รัน loop อ่าน config จาก arg/env/ไฟล์
    """

    import sys

    argv_list = list(sys.argv[1:] if argv is None else argv)

    # ถ้าเป็น subcommand install/uninstall → จัดการเอง (ไม่ให้ load_config require server/token)
    if "--install" in argv_list or "--uninstall" in argv_list:
        import argparse

        parser = argparse.ArgumentParser(prog="monitor-agent", description="monitor agent")
        parser.add_argument("--install", action="store_true", help="ติดตั้งเป็น service (เขียน agent.cfg + NSSM/systemd)")
        parser.add_argument("--uninstall", action="store_true", help="ลบ service")
        parser.add_argument("--config", default="", help="เส้นทางไฟล์ agent.cfg")
        parser.add_argument("--server", default="", help="URL ของ server")
        parser.add_argument("--token", default="", help="agent token")
        parser.add_argument("--interval", type=int, default=15, help="รอบเก็บ (วินาที)")
        parser.add_argument("--ports", default="", help="ราย TCP port เช่น 80:web,443:https")
        parser.add_argument("--watch", default="", help="service ที่เฝ้า เช่น nginx,mysql")
        args = parser.parse_args(argv_list)
        if args.uninstall:
            selfinstall.uninstall()
            return
        if not args.server or not args.token:
            parser.error("--install ต้องระบุ --server และ --token")
        cfg_payload: dict[str, str] = {
            "server_url": args.server,
            "token": args.token,
            "interval": str(args.interval),
            "ports": args.ports,
            "watch": args.watch,
        }
        if args.config:
            cfg_payload["config"] = args.config
        selfinstall.install(cfg_payload)
        return
    # โหมดรันปกติ — load_config() อ่าน argv/env/ไฟล์ เอง
    run(load_config(argv_list))


if __name__ == "__main__":
    main()
