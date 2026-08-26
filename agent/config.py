"""Config ฝั่ง agent — server_url + token + interval จาก CLI arg / env / ไฟล์.

ลำดับความสำคัญ: CLI arg > env (`MONITOR_*`) > ไฟล์ `agent.cfg` (ถ้ามี) > default.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from agent import selfinstall

ENV_PREFIX = "MONITOR_"


@dataclass(frozen=True)
class AgentConfig:
    """การตั้งค่า agent (ไม่ผูกกับไฟล์ — ใช้ arg/env ตาม AGENTS.md)."""

    server_url: str
    token: str
    interval: int = 15
    watch: tuple[str, ...] = ()
    ports: tuple[tuple[int, str], ...] = ()  # ราย (port, name) ที่เฝ้าดูว่าเปิด/ปิด

    def __post_init__(self) -> None:
        """validate ค่า config ตอนสร้าง."""

        if self.interval < 1:
            raise ValueError("interval ต้อง >= 1 วินาที")
        if not self.server_url:
            raise ValueError("ต้องระบุ server_url")


def _env(name: str) -> str:
    """อ่าน env `MONITOR_<NAME>`; คืน '' ถ้าไม่มี."""

    return os.environ.get(ENV_PREFIX + name, "")


def load_config(argv: list[str] | None = None) -> AgentConfig:
    """สร้าง AgentConfig จาก CLI arg > env (`MONITOR_*`) > ไฟล์ `agent.cfg` > default.

    Notes:
        เมื่อไม่ได้ใส่ --server/--token (หรือ env) จะลองอ่านจากไฟล์ agent.cfg
        (ที่ --install เขียนไว้) เพื่อให้รันง่ายโดยไม่ต้องจำ args (AGENTS.md).
    """
    parser = argparse.ArgumentParser(prog="monitor-agent", description="monitor agent")
    parser.add_argument("--config", default="", help="เส้นทางไฟล์ agent.cfg (default ข้าง exe/runtime)")
    parser.add_argument("--install", action="store_true", help="ติดตั้งเป็น service (เขียน agent.cfg + NSSM/systemd)")
    parser.add_argument("--uninstall", action="store_true", help="ลบ service")
    parser.add_argument("--server", default=_env("SERVER_URL") or None, help="URL ของ server เช่น http://127.0.0.1:18080")
    parser.add_argument("--token", default=_env("TOKEN") or None, help="agent token")
    parser.add_argument("--interval", type=int, default=None, help="รอบเก็บข้อมูล (วินาที)")
    parser.add_argument("--watch", default=_env("WATCH") or "", help="service/process ที่เฝ้าดู คั่นด้วย , เช่น nginx,mysql")
    parser.add_argument("--ports", default=_env("PORTS") or "", help="ราย TCP port ที่เฝ้าดู รูป 80:web,443:https (คั่นด้วย ,)")
    args = parser.parse_args(argv)

    # ค่า default ที่ยังว่าง → พยายามอ่านจากไฟล์ agent.cfg (ที่ --install เขียนไว้)
    file_server = file_token = file_interval = file_ports = file_watch = ""
    cfg = selfinstall.read_config(args.config)
    if cfg.has_section("agent"):
        file_server = cfg.get("agent", "server_url", fallback="")
        file_token = cfg.get("agent", "token", fallback="")
        file_interval = cfg.get("agent", "interval", fallback="")
        file_ports = cfg.get("agent", "ports", fallback="")
        file_watch = cfg.get("agent", "watch", fallback="")

    server = args.server or file_server
    token = args.token or file_token
    interval = args.interval if args.interval is not None else (int(file_interval) if file_interval else 15)
    if not server or not token:
        raise SystemExit(
            "ต้องระบุ --server และ --token (หรือ env MONITOR_SERVER_URL/MONITOR_TOKEN) "
            "หรือสร้างไฟล์ agent.cfg ด้วย --install"
        )
    watch = tuple(n.strip() for n in (args.watch or file_watch).split(",") if n.strip())
    ports = _parse_ports(args.ports or file_ports)
    return AgentConfig(
        server_url=server,
        token=token,
        interval=interval,
        watch=watch,
        ports=ports,
    )


def _parse_ports(text: str) -> tuple[tuple[int, str], ...]:
    """แปลงสตริง '80:web,443:https' → ((80,'web'),(443,'https'))."""

    result: list[tuple[int, str]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            port_s, name = part.split(":", 1)
        else:
            port_s, name = part, ""
        try:
            result.append((int(port_s.strip()), name.strip()))
        except ValueError:
            continue  # ข้ามค่าไม่ใช่ตัวเลข
    return tuple(result)
