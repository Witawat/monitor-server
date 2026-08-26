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
from shared.metric import MAX_BATCH_SIZE, snapshot_to_dict

# ── helpers ──

def _default_state_dir() -> Path:
    """ที่เก็บ state (host_id/queue): ข้าง exe ถ้า frozen, ไม่งั้น ~/.monitor-agent.

    Notes:
        เก็บข้าง exe ให้ย้าย/จัดการง่าย (AGENTS.md) — ตรงกับ server exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.home() / ".monitor-agent"


def _flush_queue(queue: PushQueue, url: str, token: str) -> None:
    """ลองส่งข้อมูลค้างใน queue เป็น chunk (ไม่เกิน MAX_BATCH_SIZE ต่อครั้ง)."""

    pending = queue.pending()
    if not pending:
        return
    ok = True
    for i in range(0, len(pending), MAX_BATCH_SIZE):
        chunk = pending[i : i + MAX_BATCH_SIZE]
        if not (200 <= push_batch_status(url, token, chunk) < 300):
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

    while True:
        batch: list[dict[str, Any]] = [snapshot_to_dict(collect.snapshot(host_id, watch=config.watch, ports=list(config.ports)))]
        status = push_batch_status(config.server_url, config.token, batch)
        if status in (401, 403):
            # token/config ผิด — ไม่มีทางหาย อย่า retry ตลอดไป
            raise SystemExit(f"server ตอบ {status} — token ไม่ถูกต้อง ตรวจ config แล้วลองใหม่")
        if 200 <= status < 300:
            fail_streak = 0
            _flush_queue(queue, config.server_url, config.token)
            delay: float = config.interval
        else:
            queue.enqueue(batch)  # กันข้อมูลหายตอน server offline
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
