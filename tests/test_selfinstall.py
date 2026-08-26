"""ทดสอบ agent/selfinstall.py — เขียน/อ่าน agent.cfg + load_config จากไฟล์."""

from __future__ import annotations

import sys

import pytest

from agent import selfinstall
from agent.config import load_config


def test_write_and_read_config(tmp_path, monkeypatch):
    """write_config → read_config คืนค่าเดิม."""

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(selfinstall, "_runtime_dir", lambda: tmp_path)
    cfg_path = selfinstall.write_config("", "http://srv:18080", "tok", 20, "80:web,443:https", "nginx")
    assert cfg_path.exists()

    cfg = selfinstall.read_config("")
    assert cfg.get("agent", "server_url") == "http://srv:18080"
    assert cfg.get("agent", "token") == "tok"
    assert cfg.get("agent", "interval") == "20"
    assert cfg.get("agent", "ports") == "80:web,443:https"
    assert cfg.get("agent", "watch") == "nginx"


def test_load_config_from_file(tmp_path, monkeypatch):
    """load_config อ่านค่า server/token/interval จากไฟล์agent.cfg เมื่อไม่มี arg/env."""

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(selfinstall, "_runtime_dir", lambda: tmp_path)
    selfinstall.write_config("", "http://srv:18080", "tok", 30, "", "")

    cfg = load_config(["--config", str(tmp_path / "agent.cfg")])
    assert cfg.server_url == "http://srv:18080"
    assert cfg.token == "tok"
    assert cfg.interval == 30


def test_load_config_needs_server_or_token(tmp_path, monkeypatch):
    """ยังไม่มี server/token จาก arg/env/ไฟล์ → fail ด้วย SystemExit."""

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(selfinstall, "_runtime_dir", lambda: tmp_path)
    with pytest.raises(SystemExit):
        load_config(["--config", str(tmp_path / "nope.cfg")])
