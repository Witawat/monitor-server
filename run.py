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


def _is_frozen() -> bool:
    """เช็คว่ากำลังรันเป็น exe (PyInstaller) หรือไม่."""

    return bool(getattr(sys, "frozen", False))


def _runtime_dir() -> Path:
    """ไดเรกทอรีฐาน: ข้าง exe ถ้า frozen, ไม่งั้นรากโปรเจกต์ (dev)."""

    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resolved_config(configured: str) -> str:
    """หาคอนฟิก: path ที่ระบุ หรือข้าง exe/รากโปรเจกต์."""

    candidates = [configured, str(_runtime_dir() / "config.toml")]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return configured


def _service_cmd(action: str, config_path: str) -> None:
    """จัดการ service ฝั่ง Windows ผ่าน NSSM (systemd ใช้ scripts/systemd).

    Notes:
        - source (python -m server.main) หรือ exe (frozen) ชี้ไปที่ตัวมันเอง
        - config/data/logs อยู่ข้าง exe ทำให้ service จัดการง่าย
    """
    cfg = load_config(_resolved_config(config_path))
    abs_cfg = str(_runtime_dir() / "config.toml")
    if _is_frozen():
        program = sys.executable  # ตัว exe เอง
        cmd_args = ["--config", abs_cfg]
    else:
        program = sys.executable
        cmd_args = ["-m", "server.main", "--config", abs_cfg]
    nssm = "nssm"

    if action == "install":
        subprocess.run([nssm, "install", _SERVICE_NAME, program, *cmd_args], check=False)
        # ตั้ง working dir = ข้าง exe (ให้ data/logs ตรงกับ runtime dir)
        subprocess.run([nssm, "set", _SERVICE_NAME, "AppDirectory", str(_runtime_dir())], check=False)
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
    parser.add_argument("--config", default="", help="เส้นทาง config.toml (ว่าง = ข้าง exe/runtime อัตโนมัติ)")
    parser.add_argument(
        "--service",
        choices=["install", "start", "stop", "remove"],
        default=None,
        help="จัดการ Windows service ผ่าน NSSM",
    )
    parser.add_argument("--no-browser", action="store_true", help="ไม่เปิด WebUI ใน browser อัตโนมัติ")
    args = parser.parse_args()

    if args.service:
        _service_cmd(args.service, _resolved_config(args.config))
        return

    from server.main import main as run_server

    run_server()


if __name__ == "__main__":
    main()
