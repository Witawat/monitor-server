"""FastAPI app หลักของ server — mount API + entry `python -m server.main`."""

from __future__ import annotations

import argparse
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server import __version__
from server.alerting import AlertEngine
from server.api.alerts import router as alerts_router
from server.api.auth import router as auth_router
from server.api.deps import SESSION_COOKIE
from server.api.hosts import router as hosts_router
from server.api.ingest import router as ingest_router
from server.api.metrics import router as metrics_router
from server.config import AppConfig, load_config
from server.ingest import IngestService
from server.storage.db import Database
from server.webui.auth import verify_session

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "webui" / "templates"))

# ── app factory ──


def create_app(config: AppConfig | None = None) -> FastAPI:
    """สร้าง FastAPI app พร้อม lifespan (เปิด DB + mount routers + webui)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = config or AppConfig()
        app.state.config = cfg
        app.state.session_secret = cfg.webui.secret_key or secrets.token_hex(32)
        data_dir = Path(cfg.server.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        db = Database(data_dir / "monitor.db")
        await db.connect()
        app.state.db = db
        await db.seed_rules_from_config([r.model_dump() for r in cfg.alerting.rules])
        engine = AlertEngine(db, cfg)
        app.state.alerting = engine
        app.state.ingest = IngestService(db, cfg, engine)
        yield
        await db.close()

    app = FastAPI(title="monitor-server", version=__version__, lifespan=lifespan)

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
        return _TEMPLATES.TemplateResponse(request, template)

    @app.get("/api/health")
    async def health() -> JSONResponse:
        """ล้วงจังหวะเช็คว่า server ยังทำงานปกติ (ใช้กับ LB / monitor)."""

        return JSONResponse({"status": "ok", "version": __version__})

    @app.get("/api/status")
    async def status() -> JSONResponse:
        """คืนสถานะ server + config + จำนวน host (สำหรับ debug/ops)."""

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
            }
        )

    return app


# ── entry ──

def _parse_args() -> argparse.Namespace:
    """แยก argument บรรทัดคำสั่ง (--config)."""

    parser = argparse.ArgumentParser(description="monitor-server")
    parser.add_argument("--config", default="config.toml", help="เส้นทาง config.toml")
    return parser.parse_args()


def main() -> None:
    """รัน server ด้วย uvicorn ตาม config (dev mode)."""

    import uvicorn

    args = _parse_args()
    config = load_config(args.config)
    app = create_app(config)
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
