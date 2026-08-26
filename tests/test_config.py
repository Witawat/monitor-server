"""ทดสอบ server/config.py — อ่าน + validate config.toml."""

from __future__ import annotations

import tomllib

import pytest
from pydantic import ValidationError

from server.config import AppConfig, load_config

VALID_TOML = """
[server]
host = "127.0.0.1"
port = 18080

[ingest]
rate_limit_per_min = 100
max_batch_size = 50
offline_timeout_sec = 30

[storage]
retention_raw_days = 7
rollup_intervals = ["1m", "5m", "1h", "1d"]
wal = true

[auth]
allow_registration = false
"""


def _write(tmp_path, text: str):
    """เขียนไฟล์ TOML ลง temp dir แล้วคืนเส้นทาง."""

    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_full(tmp_path):
    """โหลด config ที่ถูกต้องครบทุกส่วนแล้ว validate ผ่าน."""

    cfg = load_config(_write(tmp_path, VALID_TOML))
    assert cfg.server.port == 18080
    assert cfg.ingest.rate_limit_per_min == 100
    assert cfg.storage.rollup_intervals == ["1m", "5m", "1h", "1d"]
    assert cfg.auth.allow_registration is False


def test_load_config_defaults():
    """TOML ว่าง → ใช้ค่า default ของทุกส่วน."""

    raw = tomllib.loads("")
    cfg = AppConfig.model_validate(raw)
    assert cfg.server.port == 18080
    assert cfg.ingest.max_batch_size == 100
    assert cfg.storage.wal is True


def test_port_out_of_range(tmp_path):
    """port เกิน 65535 ต้อง fail validate."""

    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, '[server]\nport = 70000\n'))


def test_bad_bcrypt_hash(tmp_path):
    """admin_pass_hash ที่ไม่ใช่ bcrypt (ไม่ขึ้นต้น $2) ต้อง fail."""

    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, '[webui]\nadmin_pass_hash = "mypassword"\n'))


def test_rollup_wrong_order(tmp_path):
    """rollup_intervals ที่ไม่เรียงจากละเอียดไปหยาบต้อง fail."""

    with pytest.raises(ValidationError):
        load_config(
            _write(
                tmp_path,
                '[storage]\nrollup_intervals = ["1h", "1m"]\n',
            )
        )


def test_file_not_found(tmp_path):
    """ไม่มีไฟล์ config → FileNotFoundError."""

    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")
