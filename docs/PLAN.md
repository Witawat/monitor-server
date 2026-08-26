# PLAN.md — แผนลงมือเขียนโค้ด 5 เฟส

> ลำดับทำจริง — ทำทีละเฟส, จบเฟสต้องผ่านเช็กลิสต์ก่อนไปต่อ.
> อ้างอิง: `AGENTS.md` (กฎ), `KNOWLEDGE_BASE.md` (ความรู้), `CODING_GUIDE.md` (สไตล์), `WEBUI_DESIGN.md` (ดีไซน์).
> **สถานะ: ครบทั้ง 5 เฟส (0–5) + งานเสริมครบแล้ว — ระบบสมบูรณ์ใช้งานได้.**

## ภาพรวม

| เฟส | เป้าหมาย | สถานะ |
|-----|----------|-------|
| 0 | Scaffold + config + shared schema | ✅ |
| 1 | Server core: ingest + storage (SQLite) + API hosts/metrics | ✅ |
| 2 | Agent: collect + push + retry/backoff + queue | ✅ |
| 3 | WebUI: fleet + per-host dashboard + Chart.js | ✅ |
| 4 | Alerting + notify + history | ✅ |
| 5 | Build + Service (systemd/NSSM) + QA | ✅ |
| งานเสริม | tags, service watch, export CSV, host-down notify, rate-limit login + CSP | ✅ |

**ลำดับตรวจทุกเฟส:** `ruff check .` → `mypy --disable-error-code=unused-ignore server agent shared` → `pytest -q`

---

## เฟส 0 — Scaffold + Config + Shared
- `pyproject.toml` / `requirements.txt` (fastapi, uvicorn, jinja2, pydantic, aiosqlite, bcrypt, python-multipart, httpx)
- `config.example.toml` + `server/config.py` (pydantic validate + tomllib parse)
- `shared/metric.py` — schema + contract (บางพอให้ agent ใช้)
- `run.py` + `server/main.py` (FastAPI skeleton, `/api/status`, `/api/health`)
- `.gitignore`, `docs/` (สร้างแล้ว)
- tests: `test_config.py`, `test_api_status.py`

**เช็กลิสต์:**
- [x] `python -m server.main --config config.toml` รันได้, `GET /api/health` → ok
- [x] `pytest -q` ผ่าน

---

## เฟส 1 — Server Core (ingest + storage + API)
- `server/ingest.py` — validate batch + rate limit + upsert host
- `server/storage/` — aiosqlite (WAL), migrations, retention, rollup
- `server/api/` — ingest, hosts, metrics routers
- `server/api/auth.py` — token gen/validate (X-Agent-Token), login admin
- tests: `test_ingest.py` (mock), `test_storage.py`, `test_api.py`

**เช็กลิสต์:**
- [x] `POST /api/v1/ingest` รับ batch → เก็บลง SQLite, host ขึ้น
- [x] `GET /api/v1/hosts` + `GET /hosts/{id}/metrics?range=1h` คืน series
- [x] token ผิด → 401, flood → 429
- [x] `pytest -q` ผ่าน

---

## เฟส 2 — Agent (collect + push)
- `agent/agent.py` — collect (stdlib) + push loop + retry/backoff + queue
- `agent/config.py` — server_url + token + interval (arg/env)
- `shared/metric.py` ใช้ร่วม
- tests: `test_push.py`, `test_retry_backoff.py` (fake HTTP), `test_collect.py`

**เช็กลิสต์:**
- [x] agent collect CPU/RAM/Disk/Net/Uptime (stdlib) ถูก
- [x] push batch ไป fake server ได้; offline → queue + backoff + ส่งทีหลัง
- [x] `pytest -q` ผ่าน (ห้ามยิง server จริง)

---

## เฟส 3 — WebUI (fleet + dashboard)
- `server/webui/` — base.html SPA + parts/*.html + static (Chart.js local) — ทำตาม `WEBUI_DESIGN.md` (tokens/wireframe/format/behavior)
- `static/js/` — `app.js` + `dashboard.js` + `alerts.js` + `scale.js` (zoom) + `format.js` (ตัวเลข/หน่วย) + `i18n.js` (ภาษาไทย)
- fleet-view (HostCard + online/offline) + host-view (KPI + MetricChart + range) + alerts-view + settings-view
- login + HttpOnly cookie + token management page + hash routing (`#/host/<id>`)
- tests: `test_webui.py` + ตรวจ responsive ด้วย Playwright

**เช็กลิสต์:**
- [x] fleet แสดง host + การ์ดสถานะ, เลือก host → กราฟขึ้น (hash routing + back กลับถูก)
- [x] format ตัวเลข/หน่วย ใช้ `format.js` ร่วมกัน (ไม่มีแต่ละหน้าเขียนเอง)
- [x] UI scale `zoom` + responsive 360/768/1280 (Playwright) ไม่ overflow
- [x] `pytest -q` ผ่าน

---

## เฟส 4 — Alerting + Notify
- `server/alerting/` — ประเมิน rules หลัง ingest + history
- notifiers: webhook / Telegram (webhook พื้นฐานก่อน)
- `server/api/alerts.py` + alerts-view ใน WebUI + ack
- tests: `test_alerts.py` (mock)

**เช็กลิสต์:**
- [x] rule CPU>90 นาน 5m → ลง history + ส่ง webhook (mock)
- [x] ack ทำงาน, history ดูได้
- [x] `pytest -q` ผ่าน

---

## เฟส 5 — Build + Service + QA
- `run.py` service wrapper (install/start/stop/remove) + systemd unit + NSSM scripts
- agent packaging (`docs/BUILD.md` — ทาง A/B/C)
- `scripts/install-server.*` / `install-agent.*`
- QA: ruff/mypy/pytest ผ่านหมด + e2e integration (agent→server จริง)

**เช็กลิสต์:**
- [x] server + agent รันเป็น service ทั้ง 2 OS (systemd unit + NSSM wrapper/script)
- [x] agent offline → กลับมา push ส่งข้อมูลค้าง (fake HTTP test)
- [x] ตรวจ stack หลง (npm/node) + ล้าง `data/`/`logs/` ก่อน commit

---

## งานเสริม (หลังเฟส 5, "แนะนำเพิ่ม")
- [x] grouping/tag host (env/location) + filter fleet
- [x] process/service watch (agent เช็ค up/down)
- [x] export CSV ต่อ metric
- [x] uptime/availability + notification เมื่อ host หาย
- [x] rate-limit login + CSP/security headers WebUI

---

## เฟส 6 — QA / Bug-fix + Build EXE (icon + UPX)

### เป้าหมาย
- ล้าง bug ที่พบในการ audit (HIGH+MED+LOW คุ้มค่า) + ตรวจ layout WebUI ไม่เพี้ยน (Playwright 360/768/1280)
- Build `monitor-server.exe` + `monitor-agent.exe` (PyInstaller onefile) พร้อม icon "monitor + pulse" + บีบด้วย UPX ล่าสุด

### Bug ที่พบ & แก้
| ระดับ | ปัญหา | แก้ |
|-------|-------|-----|
| HIGH | H1 หน้า login พัง (CSP บล็อก inline script) | ย้ายไป `static/js/login.js` |
| HIGH | H2 auto-register แย่งชิง token host เดิม | host_id มีอยู่แล้ว → 409 ไม่อัปเดต token |
| HIGH | H3 stored XSS (host_id/hostname) | `escapeHtml()` ใน format.js |
| MED | M1 retention dead code + ไม่ลบ service/history | background task + ลบครบ |
| MED | M3 delete_host orphan service/history | ลบครบทุกตาราง |
| MED | M4 agent queue > max_batch ติดตาย | chunk flush |
| MED | M5 offline monitor re-fire + fire host ยังไม่เคย online | ข้าม host ไร้ข้อมูล + persist fired |
| MED | M6 session secret สุ่มใหม่ทุก boot | เก็บ state.json |
| MED | M7 /api/status ไม่มี auth | ใส่ require_admin |
| MED | M8 chart instance leak | destroy ก่อนวาดใหม่ |
| MED | M9 fleet/net/disk แสดงผิด (summary ขาด field) | เพิ่ม net/disk ใน summary |
| MED | M10 header injection host_id (export) | sanitize filename |
| LOW | L1/L3/L5/L6/L7/L8 + chart x-axis แสดง epoch | ทำครบ |

### Build EXE
- icon: `scripts/make_icon.py` (Pillow) → `build/monitor.ico` (16–256)
- UPX: ดาวน์โหลดล่าสุด → `scripts/tools/upx/upx.exe` (`--upx-dir`)
- PyInstaller: server (`--add-data server\webui`) + agent (`--icon`, onefile)
- ตรวจ exe รันได้ + WebUI/login ใช้ได้ + size/อัตราบีบ
- ไฟล์ runtime อยู่ข้าง exe: `config.toml`/`data`/`logs` resolve ข้าง exe; ครั้งแรก auto-create config + พิมพ์ admin pw
- service: server exe `--service install|start|stop|remove` (NSSM) · agent `install-agent.ps1` · Linux systemd unit
- ทดสอบ exe end-to-end: `scripts/test_exe.ps1` (health/WebUI/login/static + API ingest/hosts/tags/metrics/alerts CRUD/export CSV + agent exe push) — 13 checks

**เช็กลิสต์:**
- [x] login + ทุก view ใช้งานได้, layout 360/768/1280 ไม่ overflow ไม่เพี้ยน (Playwright)
- [x] `pytest -q` ผ่าน (รวม regression ครอบ bug)
- [x] `dist/monitor-server.exe` + `dist/monitor-agent.exe` รันได้, agent → server push ได้, UPX บีบแล้ว
- [x] `scripts/test_exe.ps1` ทดสอบ exe ครบ 13 checks ผ่าน


---

## เฟส 7 — งานที่เหลือ (rollup + alert rule UI + minor)

### ทำแล้ว
- [x] Rollup tables (1m/5m/1h/1d) — `aggregate_rollup` + RollupWorker (background) + `get_metrics` อ่านจาก rollup สำหรับ range กว้าง (6h/1d/7d/30d/45d), fallback raw ถ้ายังไม่มี
- [x] Alert rule CRUD UI — ฟอร์มสร้าง/แก้/ลบกฎในหน้า Alerts (เชื่อม `/api/v1/alerts` POST/PUT/DELETE)
- [x] L2 cookie Secure flag (`webui.secure_cookie`, เปิดเมื่อ HTTPS)
- [x] L4 disk % ใช้ `f_bavail` (เหมือน df)
- [x] BUILD.md เพิ่มส่วน build exe (build.ps1 + icon + UPX) + bump version 0.2.0 + CHANGELOG
- [x] Host realtime auto-refresh (poll ทุก 5s / range กว้าง 1 นาที) + Fleet poll 10s
- [x] CI (ruff+mypy+pytest py3.11/3.12) + release auto (tag `v*` → build exe + release) + README badges
- [ ] (optional ยังไม่ทำ) dark theme, SSE realtime (ย้ายจาก poll), mini-map sparkline, popup แจ้งเตือน
