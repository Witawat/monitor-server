"""FastAPI app หลักของ server — mount API + entry `python -m server.main`."""

from __future__ import annotations

import argparse
import secrets
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server import __version__
from server.alerting import AlertEngine
from server.alerting.offline import HostDownMonitor
from server.api.alerts import router as alerts_router
from server.api.auth import router as auth_router
from server.api.deps import SESSION_COOKIE, require_admin
from server.api.hosts import router as hosts_router
from server.api.ingest import router as ingest_router
from server.api.metrics import router as metrics_router
from server.config import AppConfig, load_config
from server.ingest import IngestService, RateLimiter
from server.maintenance import RetentionWorker, RollupWorker
from server.storage.db import Database
from server.webui.auth import hash_password, verify_session

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "webui" / "templates"))


def _runtime_dir() -> Path:
    """ไดเรกทอรีฐานรันไทม์: ข้าง exe ถ้า frozen, ไม่งั้นรากโปรเจกต์ (dev).

    Notes:
        ให้ config/data/logs อยู่ข้าง exe เดียวกัน ง่ายต่อการจัดการ (AGENTS.md).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _BASE_DIR.parent


def _resolve_config_path(configured: str) -> str:
    """หาคอนฟิก: ใช้ path ที่ระบุ หรือ fallback ไปที่ข้าง exe/รากโปรเจกต์."""

    candidates = [configured, str(_runtime_dir() / "config.toml")]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return configured


def _ensure_config(path: str) -> str:
    """ถ้า exe (frozen) ยังไม่มี config ให้สร้าง default ข้าง exe + รหัสผ่าน admin ใหม่.

    Returns:
        เส้นทาง config ที่จะใช้ (สร้างแล้ว ถ้าเป็น frozen ครั้งแรก).
    """
    if Path(path).is_file():
        return path
    if not getattr(sys, "frozen", False):
        return path  # dev ปล่อยให้ error ระบุเอง
    pw = secrets.token_urlsafe(12)
    cfg_path = _runtime_dir() / "config.toml"
    cfg_path.write_text(
        "# config.toml (สรางอัตโนมัติโดย exe ครั้งแรก - แกไขได)\n"
        '[server]\nhost = "127.0.0.1"\nport = 18080\n'
        'data_dir = "data"\nlog_dir = "logs"\n\n'
        '[webui]\nadmin_user = "admin"\n'
        f'admin_pass_hash = "{hash_password(pw)}"\n'
        f'secret_key = "{secrets.token_hex(32)}"\n'
        'secure_cookie = false\nsetup_done = true\n\n'
        '[ingest]\nrate_limit_per_min = 1200\nmax_batch_size = 100\noffline_timeout_sec = 60\n\n'
        '[storage]\nretention_raw_days = 45\nrollup_intervals = ["1m","5m","1h","1d"]\nwal = true\n\n'
        "[alerting]\nenabled = true\n\n[alerting.notifiers.webhook]\nurl = \"\"\n\n"
        '[alerting.notifiers.telegram]\nbot_token = ""\nchat_id = ""\n\n'
        "[auth]\nallow_registration = true\n",
        encoding="utf-8",
    )
    print(f"[monitor-server] สร้าง config.toml แล้ว: {cfg_path}")
    print(f"[monitor-server] เข้าสู่ระบบครั้งแรก: admin / {pw}")
    return str(cfg_path)


def _resolve_dir(value: str) -> Path:
    """แปลง data_dir/log_dir เป็น absolute; relative = ข้าง runtime dir."""

    p = Path(value)
    if not p.is_absolute():
        p = _runtime_dir() / p
    return p


def _resolve_secret(configured: str, data_dir: Path) -> str:
    """คืน secret_key ให้คงที่ข้าม restart: ถ้า config ว่าง ใช้/สร้างจาก state.json."""

    if configured:
        return configured
    state_path = data_dir / "state.json"
    if state_path.exists():
        try:
            import json

            return str(json.loads(state_path.read_text(encoding="utf-8")).get("session_secret", ""))
        except (ValueError, OSError):
            pass
    secret = secrets.token_hex(32)
    import json
    from contextlib import suppress

    with suppress(OSError):
        state_path.write_text(json.dumps({"session_secret": secret}), encoding="utf-8")
    return secret
# ── app factory ──


def create_app(config: AppConfig | None = None) -> FastAPI:
    """สร้าง FastAPI app พร้อม lifespan (เปิด DB + mount routers + webui)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = config or AppConfig()
        app.state.config = cfg
        data_dir = _resolve_dir(cfg.server.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        app.state.session_secret = _resolve_secret(cfg.webui.secret_key, data_dir)
        app.state.login_limiter = RateLimiter()
        db = Database(data_dir / "monitor.db", rollup_intervals=cfg.storage.rollup_intervals)
        await db.connect()
        app.state.db = db
        await db.seed_rules_from_config([r.model_dump() for r in cfg.alerting.rules])
        engine = AlertEngine(db, cfg)
        app.state.alerting = engine
        app.state.ingest = IngestService(db, cfg, engine)
        offline = HostDownMonitor(db, cfg)
        app.state.offline = offline
        offline.start()
        retention = RetentionWorker(db, cfg.storage.retention_raw_days)
        app.state.retention = retention
        retention.start()
        rollup = RollupWorker(db, cfg.storage.rollup_intervals)
        app.state.rollup = rollup
        rollup.start()
        yield
        await rollup.stop()
        await retention.stop()
        await offline.stop()
        await db.close()

    app = FastAPI(title="monitor-server", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """เพิ่ม security headers (CSP + อื่นๆ) ทุก response."""

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(ingest_router)
    app.include_router(hosts_router)
    app.include_router(metrics_router)
    app.include_router(auth_router)
    app.include_router(alerts_router)

    static_dir = _BASE_DIR / "webui" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        """serve SPA shell; ถ้ายังไม่ login → หน้า login."""

        cookie = request.cookies.get(SESSION_COOKIE)
        authed = bool(
            cookie
            and verify_session(request.app.state.session_secret, cookie)
        )
        template = "base.html" if authed else "login.html"
        return _TEMPLATES.TemplateResponse(request, template, {"version": __version__})

    @app.get("/api/health")
    async def health() -> JSONResponse:
        """ล้วงจังหวะเช็คว่า server ยังทำงานปกติ (ใช้กับ LB / monitor)."""

        return JSONResponse({"status": "ok", "version": __version__})

    @app.get("/guide", include_in_schema=False)
    @app.get("/guide/{name}", include_in_schema=False)
    async def docs_page(request: Request, name: str = "") -> HTMLResponse:
        """serve หน้าเอกสารแนะนำ — exe ตัวเดียวไม่มีไฟล์ .md, ชี้ให้ดูวิธีติดตั้งจาก WebUI.

        Notes:
            กันลิงก์ `docs/DEPLOYMENT.md` ที่เคยแชร์ไว้กลายเป็น 404 ว่างเปล่า —
            คืนหน้าสั้น ๆ ชี้ไปที่หน้า Fleet/ตั้งค่าแทน (ไม่มี .md บน exe ตัวเดียว).
            ใช้ path `/guide` (ไม่ใช่ `/docs` ซึ่งเป็น Swagger UI โดย default).
        """
        return HTMLResponse(
            "<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<title>เอกสาร — Monitor</title></head><body style=\"font-family:system-ui;padding:24px\">"
            "<h1>เอกสาร Monitor</h1>"
            "<p>เวอร์ชันนี้ (exe ตัวเดียว) ไม่ได้ bundle ไฟล์ <code>.md</code> — ดูวิธีติดตั้ง agent และคู่มือได้จากหน้า WebUI:</p>"
            "<ul><li><a href=\"/#/fleet\">วิธีติดตั้ง agent (ปุ่ม \"ดูวิธีติดตั้ง agent\")</a></li>"
            "<li><a href=\"/#/settings\">ตั้งค่า → Agent Token</a></li></ul>"
            "<p>สคริปต์/คู่มือแบบ source: ดูใน repo <code>docs/</code> (บน GitHub).</p>"
            "</body></html>"
        )

    @app.get("/api/status")
    async def status(
        _: Annotated[str, Depends(require_admin)]
    ) -> JSONResponse:
        """คืนสถานะ server + config + จำนวน host (ต้อง login)."""

        cfg = app.state.config
        db: Database = app.state.db
        hosts = await db.list_hosts()
        return JSONResponse(
            {
                "version": __version__,
                "host_count": len(hosts),
                "server": {
                    "host": cfg.server.host,
                    "port": cfg.server.port,
                    "data_dir": cfg.server.data_dir,
                    "log_dir": cfg.server.log_dir,
                },
                "ingest": {
                    "rate_limit_per_min": cfg.ingest.rate_limit_per_min,
                    "max_batch_size": cfg.ingest.max_batch_size,
                    "offline_timeout_sec": cfg.ingest.offline_timeout_sec,
                },
                "storage": {
                    "retention_raw_days": cfg.storage.retention_raw_days,
                    "rollup_intervals": cfg.storage.rollup_intervals,
                },
            }
        )

    return app


# ── entry ──

def _parse_args() -> argparse.Namespace:
    """แยก argument บรรทัดคำสั่ง (--config).

    Notes:
        default ของ --config เป็น "" (ว่าง) — ไม่ระบุ = อ่าน config.toml ข้าง exe (frozen)
        หรือรากโปรเจกต์ (dev) อัตโนมัติ ไม่ต้องสั่ง --config.
    """

    parser = argparse.ArgumentParser(description="monitor-server")
    parser.add_argument("--config", default="", help="เส้นทาง config.toml (ว่าง = ข้าง exe/runtime อัตโนมัติ)")
    parser.add_argument("--no-browser", action="store_true", help="ไม่เปิด WebUI ใน browser อัตโนมัติ")
    return parser.parse_args()


def _open_browser(host: str, port: int, delay: float = 1.5) -> None:
    """เปิด WebUI ใน browser หลัง server เริ่มรับ (ไม่ block loop)."""

    import threading
    import time
    import webbrowser

    url = f"http://{host}:{port}/"
    if host in ("0.0.0.0", "::"):
        url = f"http://127.0.0.1:{port}/"

    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    """รัน server ด้วย uvicorn ตาม config (dev mode / exe)."""

    import uvicorn

    args = _parse_args()
    cfg_path = _ensure_config(_resolve_config_path(args.config))
    config = load_config(cfg_path)
    app = create_app(config)
    if not args.no_browser:
        _open_browser(config.server.host, config.server.port)
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
