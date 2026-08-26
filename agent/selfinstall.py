"""Self-install ของ agent — เขียน config + สร้าง/ลบ service เอง (Windows NSSM / Linux systemd).

ใช้เมื่อรัน `python -m agent.agent --install` (หรือ exe) — ตั้ง config ในไฟล์ `agent.cfg`
ข้างตัว + สร้าง service ให้ agent เอง ไม่ต้องรัน install script แยก (AGENTS.md: ติดตั้งง่าย).
"""

from __future__ import annotations

import configparser
import os
import platform
import subprocess
import sys
from pathlib import Path

# ── config file ──

DEFAULT_CONFIG_NAME = "agent.cfg"


def _runtime_dir() -> Path:
    """ไดเรกทอรีที่เก็บ agent.cfg: ข้าง exe ถ้า frozen, ไม่งั้นรากโปรเจกต์ (dev)."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def config_path(custom: str = "") -> Path:
    """เส้นทาง config: custom ถ้าระบุ, ไม่งั้นข้าง runtime dir."""

    p = Path(custom) if custom else _runtime_dir() / DEFAULT_CONFIG_NAME
    return p if p.is_absolute() else _runtime_dir() / str(p)


def read_config(path: str = "") -> configparser.ConfigParser:
    """อ่าน agent.cfg (กลับ ConfigParser ว่างถ้าไม่มีไฟล์)."""

    cfg = configparser.ConfigParser()
    cfg.read(config_path(path), encoding="utf-8")
    return cfg


def write_config(path: str, server_url: str, token: str, interval: int, ports: str, watch: str) -> Path:
    """เขียน agent.cfg (server/token/interval/ports/watch) — ทำ dir ให้ถ้ายังไม่มี."""

    cfg = configparser.ConfigParser()
    cfg["agent"] = {
        "server_url": server_url,
        "token": token,
        "interval": str(interval),
        "ports": ports,
        "watch": watch,
    }
    dest = config_path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # เขียนไฟล์ด้วย utf-8 (ไม่ใส่ BOM — configparser อ่านได้)
    with dest.open("w", encoding="utf-8") as fh:
        cfg.write(fh)
    return dest


# ── service helpers ──

def _service_name() -> str:
    """ชื่อ service (Linux ใช้ same)."""

    return "monitor-agent"


def _nssm_cmd() -> str:
    """หา nssm (ต้องลงก่อน) — raise พร้อมคำแนะนำ ถ้าไม่มี."""

    if os.name != "nt":
        raise RuntimeError("NSSM ใช้บน Windows เท่านั้น")
    import shutil

    nssm = shutil.which("nssm")
    if not nssm:
        raise RuntimeError("ไม่พบ nssm ใน PATH — ลงจาก https://nssm.cc ก่อน แล้วลองใหม่")
    return nssm


def _install_windows(config: dict[str, str]) -> None:
    """ติดตั้ง service Windows ผ่าน NSSM (agent exe หรือ python -m agent.agent)."""

    cfg_arg = config.get("config", "")
    # เขียน config ก่อน install (agent อ่านจากไฟล์ตอน service รัน)
    write_config(
        cfg_arg,
        config.get("server_url", ""),
        config.get("token", ""),
        int(config.get("interval", "15")),
        config.get("ports", ""),
        config.get("watch", ""),
    )
    nssm = _nssm_cmd()
    if getattr(sys, "frozen", False):
        program = sys.executable
        args = ["--config", str(config_path(cfg_arg))]
    else:
        program = sys.executable
        args = ["-m", "agent.agent", "--config", str(config_path(cfg_arg))]
    subprocess.run([nssm, "install", _service_name(), program, *args], check=False)
    subprocess.run([nssm, "set", _service_name(), "AppDirectory", str(_runtime_dir())], check=False)
    subprocess.run([nssm, "start", _service_name()], check=False)
    print(f"ติดตั้ง service '{_service_name()}' แล้ว (config: {config_path(cfg_arg)})")


def uninstall_windows() -> None:
    """ลบ service Windows (NSSM)."""

    nssm = _nssm_cmd()
    subprocess.run([nssm, "stop", _service_name()], check=False)
    subprocess.run([nssm, "remove", _service_name(), "confirm"], check=False)
    print(f"ลบ service '{_service_name()}' แล้ว")


def install_linux(config: dict[str, str]) -> None:
    """สร้าง systemd unit สำหรับ agent (ใน /etc/systemd/system)."""

    unit = config_path().parent / "monitor-agent.service"
    content = _systemd_unit(config)
    unit.write_text(content, encoding="utf-8")
    subprocess.run(["sudo", "cp", str(unit), f"/etc/systemd/system/{_service_name()}.service"], check=False)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", _service_name()], check=False)
    print(f"ติดตั้ง systemd '{_service_name()}' แล้ว (config: {config_path()})")


def uninstall_linux() -> None:
    """หยุด + ลบ systemd unit."""

    subprocess.run(["systemctl", "stop", _service_name()], check=False)
    subprocess.run(["systemctl", "disable", _service_name()], check=False)
    subprocess.run(["rm", "-f", f"/etc/systemd/system/{_service_name()}.service"], check=False)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    print(f"ลบ service '{_service_name()}' แล้ว")


def _systemd_unit(config: dict[str, str]) -> str:
    """สร้างเนื้อหา .service สำหรับ agent (อ่าน config จากไฟล์ agent.cfg)."""

    cfg_path = config_path()
    exe = sys.executable if getattr(sys, "frozen", False) else "/usr/bin/python3"
    if getattr(sys, "frozen", False):
        cmd = f"{exe} --config {cfg_path}"
    else:
        cmd = f"{exe} -m agent.agent --config {cfg_path}"
    return (
        "[Unit]\n"
        "Description=Monitor Agent\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={cmd}\n"
        f"WorkingDirectory={_runtime_dir()}\n"
        "Restart=always\n"
        "RestartSec=5\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def install(config: dict[str, str]) -> None:
    """ติดตั้ง service ตามแพลตฟอร์ม (Windows NSSM / Linux systemd).

    Args:
        config: dict ประกอบด้วย server_url/token/interval/ports/watch (+ config เส้นทาง agent.cfg).
    """

    if platform.system() == "Windows" or os.name == "nt":
        _install_windows(config)
    else:
        install_linux(config)


def uninstall() -> None:
    """ลบ service ตามแพลตฟอร์ม."""

    if platform.system() == "Windows" or os.name == "nt":
        uninstall_windows()
    else:
        uninstall_linux()
