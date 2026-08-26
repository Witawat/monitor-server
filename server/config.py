"""อ่าน + validate config.toml ฝั่ง server (pydantic + stdlib tomllib)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ── model config ──

_OPS = Literal[">", ">=", "<", "<=", "=="]


class ServerConfig(BaseModel):
    """การตั้งค่าส่วน server (host/port/เส้นทางเก็บข้อมูล)."""

    host: str = "127.0.0.1"
    port: int = Field(default=18080, ge=1, le=65535)
    data_dir: str = "data"
    log_dir: str = "logs"


class WebUIConfig(BaseModel):
    """การตั้งค่า WebUI (admin user + bcrypt hash + secret เซ็น cookie)."""

    admin_user: str = "admin"
    admin_pass_hash: str = ""
    secret_key: str = ""
    setup_done: bool = False
    secure_cookie: bool = False  # เปิดเมื่อใช้ HTTPS — cookie มี Secure flag

    @field_validator("admin_pass_hash")
    @classmethod
    def _check_bcrypt(cls, value: str) -> str:
        """ตรวจว่า hash เป็น bcrypt (ขึ้นต้น $2) ถ้าใส่ค่ามาแล้ว."""

        if value and not value.startswith("$2"):
            raise ValueError("admin_pass_hash ต้องเป็น bcrypt hash ($2...) ไม่ใช่ plain text")
        return value


class IngestConfig(BaseModel):
    """การตั้งค่าการรับ push จาก agent (rate limit / batch / offline)."""

    rate_limit_per_min: int = Field(default=1200, ge=0)
    max_batch_size: int = Field(default=100, ge=1)
    offline_timeout_sec: int = Field(default=60, ge=0)


class StorageConfig(BaseModel):
    """การตั้งค่า SQLite store (retention / rollup / WAL)."""

    retention_raw_days: int = Field(default=45, ge=0)
    rollup_intervals: list[str] = Field(
        default_factory=lambda: ["1m", "5m", "1h", "1d"]
    )
    wal: bool = True


class RuleConfig(BaseModel):
    """หนึ่ง alert rule (threshold ต่อ host/metric)."""

    name: str = ""
    host_id: str = ""
    metric: str = ""
    op: _OPS = ">"
    threshold: float = 0.0
    duration: str = "5m"
    notify: list[str] = Field(default_factory=list)


class NotifierConfig(BaseModel):
    """Notifier webhook + telegram (url/token/chat)."""

    webhook: dict[str, Any] = Field(default_factory=dict)
    telegram: dict[str, Any] = Field(default_factory=dict)


class AlertingConfig(BaseModel):
    """การตั้งค่า alerting โดยรวม."""

    enabled: bool = True
    notifiers: NotifierConfig = Field(default_factory=NotifierConfig)
    rules: list[RuleConfig] = Field(default_factory=list)


class AuthConfig(BaseModel):
    """การตั้งค่า auth (auto-register agent + กัน brute-force login)."""

    allow_registration: bool = True
    login_rate_per_min: int = Field(default=5, ge=0)      # สูงสุด/นาที ต่อ IP
    login_global_per_min: int = Field(default=30, ge=0)   # สูงสุด/นาที รวมทุก IP (กัน botnet)
    audit_keep_days: int = Field(default=30, ge=0)        # เก็บประวัติ login (audit log)


class AppConfig(BaseModel):
    """Config ทั้งหมดของ server."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    webui: WebUIConfig = Field(default_factory=WebUIConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @model_validator(mode="after")
    def _check_rollup_order(self) -> AppConfig:
        """ยืนยันว่า rollup_intervals เรียงจากละเอียดไปหยาบ (1m < 5m < 1h < 1d)."""

        order = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            secs = [int(v[:-1]) * order[v[-1]] for v in self.storage.rollup_intervals]
        except (ValueError, KeyError):
            raise ValueError(
                f"rollup_intervals รูปแบบไม่ถูก: {self.storage.rollup_intervals}"
            ) from None
        if secs != sorted(secs):
            raise ValueError("rollup_intervals ต้องเรียงจากละเอียดไปหยาบ (1m,5m,1h,1d)")
        return self


# ── load ──

def load_config(path: str | Path) -> AppConfig:
    """อ่านไฟล์ TOML แล้ว validate กลับเป็น AppConfig.

    Args:
        path: เส้นทางไฟล์ config.toml.

    Returns:
        AppConfig ที่ validate แล้ว.

    Raises:
        FileNotFoundError: ถ้าไฟล์ config ไม่มี.
        tomllib.TOMLDecodeError: ถ้า TOML parse ไม่ได้.
        pydantic.ValidationError: ถ้าค่าผิดกฎ validate.
    """
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)
    return AppConfig.model_validate(raw)
