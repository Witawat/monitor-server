"""Helper auth ฝั่ง WebUI — bcrypt hash + เซ็น/ตรวจ cookie session."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import bcrypt

_COOKIE_MAX_AGE = 7 * 86400  # หมดอายุ 7 วัน


def hash_password(password: str) -> str:
    """สร้าง bcrypt hash ของรหัสผ่าน (ใช้ gen ใส่ config)."""

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """ตรวจรหัสผ่านกับ bcrypt hash."""

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes | None:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        return None


def sign_session(secret: str, username: str, max_age: int = _COOKIE_MAX_AGE) -> str:
    """เซ็น payload session (username + expiry) กลับเป็น cookie value."""

    payload = {"u": username, "exp": int(time.time()) + max_age}
    encoded = _b64encode(json.dumps(payload).encode("utf-8"))
    sig = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{sig}"


def verify_session(secret: str, cookie: str) -> str | None:
    """ตรวจ + ถอด session; คืน username ถ้าเซ็นถูกและยังไม่หมดอายุ (None ถ้าไม่)."""

    try:
        encoded, sig = cookie.rsplit(".", 1)
    except ValueError:
        return None
    expected = _b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    raw = _b64decode(encoded)
    if raw is None:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return str(payload.get("u", ""))


def _cli_hash() -> None:
    """CLI: `python -m server.webui.auth --hash "รหัสผ่าน"` → พิมพ์ bcrypt hash."""

    import argparse

    parser = argparse.ArgumentParser(prog="server.webui.auth")
    parser.add_argument("--hash", help="รหัสผ่านที่ต้องการสร้าง bcrypt hash")
    args = parser.parse_args()
    if not args.hash:
        raise SystemExit("ใช้: python -m server.webui.auth --hash \"รหัสผ่าน\"")
    print(hash_password(args.hash))


if __name__ == "__main__":
    _cli_hash()
