# PLAN.md — แผนลงมือเขียนโค้ด 5 เฟส

> ลำดับทำจริง — ทำทีละเฟส, จบเฟสต้องผ่านเช็กลิสต์ก่อนไปต่อ.
> อ้างอิง: `AGENTS.md` (กฎ), `KNOWLEDGE_BASE.md` (ความรู้), `CODING_GUIDE.md` (สไตล์), `WEBUI_DESIGN.md` (ดีไซน์).
> **สถานะ: ยังไม่เริ่มเขียนโค้ด — อยู่ช่วงวางแผน/ออกแบบ.**

## ภาพรวม

| เฟส | เป้าหมาย | สถานะ |
|-----|----------|-------|
| 0 | Scaffold + config + shared schema | ⬜ |
| 1 | Server core: ingest + storage (SQLite) + API hosts/metrics | ⬜ |
| 2 | Agent: collect + push + retry/backoff + queue | ⬜ |
| 3 | WebUI: fleet + per-host dashboard + Chart.js | ⬜ |
| 4 | Alerting + notify + history | ⬜ |
| 5 | Build + Service (systemd/NSSM) + QA | ⬜ |

**ลำดับตรวจทุกเฟส:** `ruff check .` → `mypy server agent shared` → `pytest -q`

---

## เฟส 0 — Scaffold + Config + Shared
- `pyproject.toml` / `requirements.txt` (fastapi, uvicorn, jinja2, pydantic, aiosqlite, bcrypt, python-multipart, httpx)
- `config.example.toml` + `server/config.py` (pydantic validate + tomllib parse)
- `shared/metric.py` — schema + contract (บางพอให้ agent ใช้)
- `run.py` + `server/main.py` (FastAPI skeleton, `/api/status`, `/api/health`)
- `.gitignore`, `docs/` (สร้างแล้ว)
- tests: `test_config.py`, `test_api_status.py`

**เช็กลิสต์:**
- [ ] `python -m server.main --config config.toml` รันได้, `GET /api/health` → ok
- [ ] `pytest -q` ผ่าน

---

## เฟส 1 — Server Core (ingest + storage + API)
- `server/ingest.py` — validate batch + rate limit + upsert host
- `server/storage/` — aiosqlite (WAL), migrations, retention, rollup
- `server/api/` — ingest, hosts, metrics routers
- `server/api/auth.py` — token gen/validate (X-Agent-Token), login admin
- tests: `test_ingest.py` (mock), `test_storage.py`, `test_api.py`

**เช็กลิสต์:**
- [ ] `POST /api/v1/ingest` รับ batch → เก็บลง SQLite, host ขึ้น
- [ ] `GET /api/v1/hosts` + `GET /hosts/{id}/metrics?range=1h` คืน series
- [ ] token ผิด → 401, flood → 429
- [ ] `pytest -q` ผ่าน

---

## เฟส 2 — Agent (collect + push)
- `agent/agent.py` — collect (stdlib) + push loop + retry/backoff + queue
- `agent/config.py` — server_url + token + interval (arg/env)
- `shared/metric.py` ใช้ร่วม
- tests: `test_push.py`, `test_retry_backoff.py` (fake HTTP), `test_collect.py`

**เช็กลิสต์:**
- [ ] agent collect CPU/RAM/Disk/Net/Uptime (stdlib) ถูก
- [ ] push batch ไป fake server ได้; offline → queue + backoff + ส่งทีหลัง
- [ ] `pytest -q` ผ่าน (ห้ามยิง server จริง)

---

## เฟส 3 — WebUI (fleet + dashboard)
- `server/webui/` — base.html SPA + parts/*.html + static (Chart.js local) — ทำตาม `WEBUI_DESIGN.md` (tokens/wireframe/format/behavior)
- `static/js/` — `app.js` + `dashboard.js` + `alerts.js` + `scale.js` (zoom) + `format.js` (ตัวเลข/หน่วย) + `i18n.js` (ภาษาไทย)
- fleet-view (HostCard + online/offline) + host-view (KPI + MetricChart + range) + alerts-view + settings-view
- login + HttpOnly cookie + token management page + hash routing (`#/host/<id>`)
- tests: `test_webui.py` + ตรวจ responsive ด้วย Playwright

**เช็กลิสต์:**
- [ ] fleet แสดง host + การ์ดสถานะ, เลือก host → กราฟขึ้น (hash routing + back กลับถูก)
- [ ] format ตัวเลข/หน่วย ใช้ `format.js` ร่วมกัน (ไม่มีแต่ละหน้าเขียนเอง)
- [ ] UI scale `zoom` + responsive 360/768/1280 (Playwright) ไม่ overflow
- [ ] `pytest -q` ผ่าน

---

## เฟส 4 — Alerting + Notify
- `server/alerting/` — ประเมิน rules หลัง ingest + history
- notifiers: webhook / Telegram (webhook พื้นฐานก่อน)
- `server/api/alerts.py` + alerts-view ใน WebUI + ack
- tests: `test_alerts.py` (mock)

**เช็กลิสต์:**
- [ ] rule CPU>90 นาน 5m → ลง history + ส่ง webhook (mock)
- [ ] ack ทำงาน, history ดูได้
- [ ] `pytest -q` ผ่าน

---

## เฟส 5 — Build + Service + QA
- `run.py` service wrapper (install/start/stop/remove) + systemd unit + NSSM scripts
- agent packaging (`docs/BUILD.md` — ทาง A/B/C)
- `scripts/install-server.*` / `install-agent.*`
- QA: ruff/mypy/pytest ผ่านหมด + e2e integration (agent→server จริง)

**เช็กลิสต์:**
- [ ] server + agent รันเป็น service ทั้ง 2 OS
- [ ] agent offline → กลับมา push ส่งข้อมูลค้าง
- [ ] ตรวจ stack หลง (npm/node) + ล้าง `data/`/`logs/` ก่อน commit

---

## งานเสริม (หลังเฟส 5, "แนะนำเพิ่ม")
- [ ] grouping/tag host (env/location) + filter fleet
- [ ] process/service watch (agent เช็ค up/down)
- [ ] export CSV ต่อ metric
- [ ] uptime/availability + notification เมื่อ host หาย
- [ ] rate-limit login + CSP/security headers WebUI
