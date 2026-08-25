# KNOWLEDGE_BASE.md — ความรู้ก่อนเขียนโค้ด

## 1. บริบท
ระบบ monitor server แบบ central + agent push (ดู `PRODUCT.md`) — server รวบรวม metrics จากหลายเครื่อง, แสดงผ่าน Web UI dashboard แบบ DigitalOcean/Plesk, agent เป็น client stdlib เล็กบนเครื่องที่ถูก monitor.

## 2. ทำไมเลือก stack นี้
- **FastAPI + uvicorn**: async รองรับ agent หลายเครื่อง push พร้อมกันได้ดี, มี OpenAPI auto (/docs)
- **SQLite**: ไม่ต้องตั้ง DB แยก, ไฟล์เดียวพกพา — เหมาะกับ time-series ต่อ host ระดับนาที (ถ้า scale ใหญ่ค่อย migrate)
- **Agent stdlib-only**: เก็บขนาดเล็ก, ไม่ติด dependency บนเครื่อง target (Linux/Windows), ติดตั้งง่าย
- **push model**: ไม่ต้อง expose port บนเครื่อง monitor (ผ่าน NAT), server เป็นตัวเปิดรับฝั่งเดียว

## 3. สถาปัตยกรรมรันไทม์
- `server/` = central: FastAPI app (`server/main.py`) mount `/api` + `/` (webui static)
- `agent/` = ฝั่ง monitor: loop `collect → batch → POST /api/v1/ingest` ทุก interval
- `shared/metric.py` = schema เดียวกันทั้ง 2 ฝั่ง (กัน drift)
- SQLite `data/monitor.db` — ตาราง hosts + metrics (time-series) + alert rules/history
- ดู `docs/ARCHITECTURE.md`

## 4. โมดูลหลัก
| โมดูล | หน้าที่ |
|-------|--------|
| `server/ingest.py` | รับ batch จาก agent: validate schema, rate limit, upsert host, เขียน metrics |
| `server/api/` | routers: ingest, hosts, metrics, alerts, auth, status |
| `server/storage/` | SQLite access layer (async), retention + rollup |
| `server/alerting/` | ประเมิน threshold + ส่ง notify (webhook/Telegram) |
| `server/webui/` | Jinja2 SPA + static (Chart.js local) |
| `agent/agent.py` | collect (stdlib) + push loop + retry/backoff + queue |
| `shared/metric.py` | pydantic model ของ metric snapshot + endpoint contract |

## 5. Config
- server: `config.toml` (TOML + pydantic validate) — `docs/CONFIG.md`
- agent: CLI args + env (`--server`, `--token`, `--interval`) — `agent/config.py`
- token ต่อ host: gen จาก WebUI → ใส่ใน config agent

## 6. API
- ดู `docs/API.md` — key: `POST /api/v1/ingest` (agent), `GET /api/v1/hosts`, `GET /api/v1/hosts/{id}/metrics`, `GET/POST /api/v1/alerts`, `POST /api/v1/auth/login`

## 7. กับดักที่ต้องรู้
- **Agent ห้าม import server/shared ใหญ่** — `shared/metric.py` ต้องบาง (stdlib + pydantic ไม่พึ่ง fastapi) หรือ agent ใช้ dict schema ตรง
- **time-series ใน SQLite**: เก็บเป็น timestamp integer/ISO + อย่าลบ row เก่าทิ้งทุก push (rollup + retention แทน)
- **network rate ต้องคำนวณจาก counter ต่าง** — agent ส่ง cumulative bytes, server เก็บ delta (ไม่ส่ง rate ตรงๆ กัน drift)
- **ข้ามแพลตฟอร์ม**: ใช้ `pathlib`/`os.path` เสมอ ห้าม `/` hardcode; psutil มีใน Windows/Linux แต่ fallback stdlib ต้องมี
- **SQLite + async**: ใช้ aiosqlite หรือ wrapper เดียวกัน; ระวัง lock ตอนเขียนพร้อมกันหลาย request (WAL mode)

## 8. ความปลอดภัย
- `X-Agent-Token` ต่อ host — server validate; rate limit ingest (กัน flood)
- login WebUI: admin user/pass bcrypt + HttpOnly cookie
- (แนะนำ) rate-limit login + CSP headers
- ไม่ commit `config.toml`/`.env`/`*.pem`/`*.key`/`data/*.db`/`logs/`

## 9. เทส
- server: `pytest -q` — ingest เทสด้วย mock (ไม่พึ่ง server จริง)
- agent: เทส push/retry/backoff ด้วย fake HTTP server (`http.server` / `httpx MockTransport`) — ห้ามยิง server จริง
- e2e (agent→server จริง) แยก integration — ไม่ใน `pytest -q`
- ล้าง `data/*.db` + `logs/` ก่อนเทสใหญ่; kill process ค้างก่อนรัน

## 10. Roadmap
- ดู `docs/PLAN.md` — 5 เฟส: 0 Scaffold → 1 Server core (ingest+storage+API) → 2 Agent → 3 WebUI → 4 Alerting → 5 Build/Service + QA
