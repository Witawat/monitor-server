"""Entry หลักของ agent — loop collect → push → retry/backoff/queue.

รันผ่าน: `python -m agent.agent --server <URL> --token <TOKEN> --interval 15`
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agent import collect
from agent.config import AgentConfig, load_config
from agent.push import Backoff, PushQueue, push_batch_status
from shared.metric import MAX_BATCH_SIZE, snapshot_to_dict

# ── helpers ──

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
        state_dir: ไดเรกทอรีเก็บ state (host_id + queue); default คือ ~/.monitor-agent.
    """
    base = Path(state_dir) if state_dir else Path.home() / ".monitor-agent"
    host_id = collect.host_id(base / "host_id")
    queue = PushQueue(base / "queue.json")
    backoff = Backoff()
    fail_streak = 0

    while True:
        batch: list[dict[str, Any]] = [snapshot_to_dict(collect.snapshot(host_id, watch=config.watch))]
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


def main() -> None:
    """Entry — อ่าน config จาก arg/env แล้วรัน loop."""

    run(load_config())


if __name__ == "__main__":
    main()
