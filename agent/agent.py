"""Entry หลักของ agent — loop collect → push → retry/backoff/queue.

รันผ่าน: `python -m agent.agent --server <URL> --token <TOKEN> --interval 15`
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agent import collect
from agent.config import AgentConfig, load_config
from agent.push import Backoff, PushQueue, push_batch
from shared.metric import snapshot_to_dict

# ── helpers ──

def _flush_queue(queue: PushQueue, url: str, token: str) -> None:
    """ลองส่งข้อมูลค้างใน queue ทั้งหมด; สำเร็จแล้วล้าง."""

    if queue.count() == 0:
        return
    if push_batch(url, token, queue.pending()):
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
        batch: list[dict[str, Any]] = [snapshot_to_dict(collect.snapshot(host_id))]
        if push_batch(config.server_url, config.token, batch):
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
