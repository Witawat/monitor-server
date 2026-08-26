"""Root entry ของ server — รัน + service wrapper (NSSM/systemd).

ใช้งาน:
- `python run.py --config config.toml` — รัน server (dev)
- `python run.py --config config.toml --service install|start|stop|remove` — จัดการ service
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from server.config import load_config

_SERVICE_NAME = "MonitorServer"


def _python() -> str:
    """คืนเส้นทาง python ปัจจุบันที่ใช้รัน wrapper."""

    return sys.executable


def _service_cmd(action: str, config_path: str) -> None:
    """จัดการ service ฝั่ง Windows ผ่าน NSSM (systemd ใช้ scripts/systemd)."""

    cfg = load_config(config_path)
    abs_cfg = str(Path(config_path).resolve())
    base = f"-m server.main --config {abs_cfg}"
    nssm = "nssm"

    if action == "install":
        subprocess.run(
            [nssm, "install", _SERVICE_NAME, _python(), base],
            check=False,
        )
        # ตั้ง working dir = รากโปรเจกต์ (ให้ path data/logs ตรง)
        root = str(Path(__file__).resolve().parent)
        subprocess.run([nssm, "set", _SERVICE_NAME, "AppDirectory", root], check=False)
        print(f"ติดตั้ง service '{_SERVICE_NAME}' แล้ว (พอร์ต {cfg.server.port})")
    elif action == "start":
        subprocess.run([nssm, "start", _SERVICE_NAME], check=False)
    elif action == "stop":
        subprocess.run([nssm, "stop", _SERVICE_NAME], check=False)
    elif action == "remove":
        subprocess.run([nssm, "remove", _SERVICE_NAME, "confirm"], check=False)
    else:
        raise SystemExit(f"--service รับแค่ install|start|stop|remove (ได้ {action})")


def main() -> None:
    """แยก --service กับโหมดรันปกติ."""

    parser = argparse.ArgumentParser(description="monitor-server")
    parser.add_argument("--config", default="config.toml", help="เส้นทาง config.toml")
    parser.add_argument(
        "--service",
        choices=["install", "start", "stop", "remove"],
        default=None,
        help="จัดการ Windows service ผ่าน NSSM",
    )
    args = parser.parse_args()

    if args.service:
        _service_cmd(args.service, args.config)
        return

    from server.main import main as run_server

    run_server()


if __name__ == "__main__":
    main()
