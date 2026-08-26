# AGENTS.md — monitor-server

## เป้าหมายโปรเจกต์
- ระบบ monitor server ข้ามแพลตฟอร์ม (Linux + Windows) — central server รวบรวม metrics จากหลายเครื่อง แล้วแสดงผ่าน Web UI แบบ dashboard (DigitalOcean / Plesk เป็นแรงบันดาลใจ)
- **Agent (runner)**: client ขนาดเล็กติดตั้งบนเครื่องที่ถูก monitor คอยเก็บ metrics แล้ว **push** ไปยัง server (push model — ไม่ใช่ pull) ให้รวดเร็ว + footprint เล็ก
- ใช้ได้ผ่าน Web UI ครบทุกอย่าง (ไม่เน้น CLI) + เพิ่ม feature ที่มีประโยชน์ (alerting, กราฟย้อนหลัง, dashboard รายเครื่อง)

## สแต็กที่ล็อกไว้
- ภาษา: **Python 3.11+** (ทั้ง server และ agent)
- **Server**: `FastAPI` + `uvicorn` + SQLite (stdlib `sqlite3`/`aiosqlite`) + `Jinja2` + vanilla JS + Chart.js (bundle local) — **ห้ามใช้ npm/node/React** (ล็อกแบบ proxy-server)
- **Agent**: **stdlib Python เท่านั้น** (`urllib`/`json`/`platform`/`socket`/`time`) — `psutil` เป็น optional เท่านั้น (มี fallback stdlib) ห้าม dependency หนัก; โค้ดใน `agent/` ต้องไม่ import server/shared ใหญ่
- shared schema/contract: `shared/` (metric schema + API contract) — ใช้ทั้ง server/agent เพื่อกัน drift; ต้องบางพอให้ agent ใช้ได้
- Config: `toml` (server — stdlib `tomllib` + validate pydantic) + env/arg (agent)
- Lint/type/test: `ruff` + `mypy` + `pytest` (pytest-asyncio)
- Service packaging: **systemd unit (Linux)** + **Windows Service / NSSM (Windows)** สำหรับทั้ง server และ agent

## สถาปัตยกรรมที่ยึด
```
monitor-server/
├── run.py                # entry หลัก server (uvicorn + service wrapper)
├── server/
│   ├── main.py           # FastAPI app (mount webui + api)
│   ├── api/              # routers: ingest, hosts, metrics, alerts, auth, status
│   ├── storage/          # SQLite (time-series per host, retention/rollup)
│   ├── config.py         # pydantic config (toml)
│   ├── ingest.py         # logic รับ push จาก agent (validate + rate limit)
│   ├── alerting/         # ตรวจเงื่อนไข alert + notify (webhook/Telegram)
│   └── webui/            # Jinja2 templates + static (SPA dashboard)
├── agent/
│   ├── agent.py          # collect + push loop (stdlib) — entry หลัก
│   ├── config.py         # server_url + token + interval
│   └── service/          # systemd unit template + Windows service wrapper (NSSM)
├── shared/
│   └── metric.py         # metric schema + ingest contract (ทั้ง 2 ฝั่งใช้ร่วม)
├── docs/                 # เอกสาร (ดูด้านล่าง)
├── tests/                # pytest (server + agent)
└── scripts/              # deploy/service helper (ps1 + sh)
```

## คำสั่งหลัก (ห้ามเดา ใช้ตามนี้)
```powershell
# venv + ติดตั้ง
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest ruff mypy   # + requirements-agent.txt (agent ถ้าแยก)

# รัน server (dev)
python -m server.main --config config.toml      # หรือ python run.py --config config.toml
# เปิด http://127.0.0.1:18080

# รัน agent (dev — ชี้ไป server ตัวเอง)
python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15

# ตรวจก่อนส่งงาน (ต้องผ่านหมดก่อน PR)
ruff check .; mypy server agent shared; pytest -q

# build EXE (server + agent onefile + icon monitor + UPX ล่าสุด)
scripts\build.bat        # ตัวหลัก — รันตรงได้เลย (สร้าง icon + PyInstaller + UPX)
# หรือ powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# ลง dev dep ก่อนครั้งแรก: .venv\Scripts\pip install -r requirements-build.txt
# ผลลัพธ์ใน dist/: monitor-server.exe + monitor-agent.exe

# ทดสอบ exe ที่ build ว่าใช้งานได้จริงครบทุกอย่าง (health/WebUI/API/agent push)
scripts\test_exe.bat     # หรือ: powershell -ExecutionPolicy Bypass -File scripts\test_exe.ps1 -Port 18089
```

## ฟีเจอร์หลัก (เช็กลิสต์)
- [x] Fleet dashboard: รายการ host + การ์ดสถานะ (CPU/RAM/Disk/Net/Uptime) + ออนไลน์/ออฟไลน์
- [x] กราฟย้อนหลัง per metric (time-series SQLite + rollup เก็บ 1m/5m/1h/1d)
- [x] Agent push: batch + retry + backoff + queue เมื่อ offline (เก็บในเครื่องแล้วส่งทีหลัง)
- [x] Alerting: เงื่อนไข threshold ต่อ host/metric + history + notify (webhook/Telegram/email) + host-down
- [x] WebUI: login admin, per-host dashboard, fleet overview, ตั้งค่า alert/agent token
- [x] Auth/security: API token ต่อ host (X-Agent-Token), rate limit ingest + login, CSP headers

## Build EXE (บันทึก)
- **`scripts/build.bat`** — ตัวหลัก build ทั้ง 2 exe (PyInstaller onefile) + สร้าง icon + บีบด้วย UPX ล่าสุด ผ่าน cmd ตรง (ไม่ต้อง powershell) — ดาวน์โหลด UPX อัตโนมัติครั้งแรก
- **`scripts/build.ps1`** — ทางเลือก PowerShell (ทำงานเหมือนกัน)
- **icon**: `scripts/make_icon.py` (Pillow) วาดหน้าจอ monitor + เส้น pulse → `build/monitor.ico` (16–256) ใช้กับทั้ง 2 exe
- **UPX**: ดาวน์โหลดล่าสุด → `scripts/tools/upx/upx.exe` (build tool — gitignore)
- **server** ต้อง `--add-data server\webui;server/webui` (ให้ WebUI/templates/static ทำงานใน exe); **agent** รวม `shared/` อัตโนมัติ
- dep build: `requirements-build.txt` (pillow, pyinstaller) — รายละเอียดเต็มดู `docs/BUILD.md`
- ผลลัพธ์: `dist/monitor-server.exe` (~22.8MB) + `dist/monitor-agent.exe` (~7.1MB)
- **ไฟล์อยู่ข้าง exe**: `config.toml` + `data/` + `logs/` ถูก resolve ไว้ข้างตัว exe (frozen) — ครั้งแรกที่รันถ้ายังไม่มี config จะสร้าง default + พิมพ์รหัสผ่าน admin (`admin / <random>`) แล้วจัดการต่อได้ทันที
- **service**: server exe รองรับ `--service install|start|stop|remove` (NSSM ชี้ตัว exe เอง, config/data อยู่ข้าง exe); agent exe ใช้ `scripts\install-agent.ps1` (detect exe) · Linux ใช้ systemd unit ใน `scripts/systemd` + `agent/service`

## ทดสอบ EXE (หลัง build — ต้องผ่านก่อนปิดงาน)
- **`scripts/test_exe.bat`** / **`scripts/test_exe.ps1`** — ทดสอบ exe จริงแบบ end-to-end:
  - server exe: `/api/health`, หน้า login + login.js (CSP), static chart bundle, login/cookie, `/me`, SPA
  - API: ingest → hosts, tags, metrics (range=6h rollup), alerts CRUD, export CSV
  - agent exe: push จริง → host ขึ้น (host_count เพิ่ม)
- ใช้ config/data_dir ชั่วคราวแยก (พอร์ต 18089 กันชน dev) + ล้างอัตโนมัติ; **13 checks** ต้องผ่านทั้งหมด

## กฎการทดสอบ (สำคัญ)
- เทส server: `pytest -q` — ingest ต้องเทสด้วย mock (ไม่พึ่ง server จริง)
- เทส agent: ต้องเทส push/retry/backoff ด้วย fake HTTP server (`http.server`/`httpx MockTransport`) — **ห้ามยิง server จริง**
- ก่อนเทส/รัน ให้ kill process ค้าง: `Get-Process python | Stop-Process` + เช็คพอร์ต 18080 ว่าง
- ล้าง `data/*.db` + `logs/` ก่อนเทสครั้งใหญ่ (กันข้อมูลเก่าปน)
- เทสแบบ end-to-end (agent → server จริง) แยกเป็น integration — ไม่อยู่ใน `pytest -q` ปกติ

## กฎการเขียน Comment / Docstring (ไทย · PEP 257 + PEP 8)
- **ภาษา: ไทย** (convention โปรเจกต์) — ใช้ศัพท์เทคนิคภาษาอังกฤษเท่าที่จำเป็น
- **ทุก public function/class/method ต้องมี docstring** (สรุป 1 บรรทัด) — private (ขึ้นต้น `_`) ไม่บังคับ
- รูปแบบ docstring: สรุปสั้น + เพิ่ม `Args:`/`Returns:`/`Raises:`/`Notes:` เฉพาะเมื่อจำเป็น
- **inline comment ตาม PEP 8**: เว้น **2 ช่อง** ก่อน `#` + 1 ช่องหลัง `#` — เขียนแบบ "why/จุดประสงค์" ไม่ใช่เล่าโค้ดซ้ำ (ห้าม `x += 1  # เพิ่ม x`)
- comment ทั้งบรรทัดเริ่มด้วย `# ` · ห้าม comment ที่ obvious (โค้ดอ่านรู้เรื่อง = ไม่ต้อง comment)
- section divider ใช้ `# ── ชื่อ ──` — คงรูปแบบสม่ำเสมอ
- รายละเอียดเต็มดู **`docs/CODING_GUIDE.md`** (รูปแบบ code + คำอธิบาย + ตัวอย่าง metric schema)

## กฎ WebUI
- WebUI เป็น single-page (SPA) — `templates/base.html` + `templates/parts/*.html` (ใช้ `{% include %}`) — JS สลับ view
- JS แยกโมดูลใน `static/js/` (`app`/`dashboard`/`alerts` + `scale`/`format`/`i18n`) — format ตัวเลข/หน่วยรวมใน `format.js` (ห้ามแต่ละหน้าเขียนเอง) · UI scale ทั้งกรอบด้วย `zoom` + `scale.js`
- dashboard realtime: เลือก host → poll `/api/v1/hosts/{id}/metrics?range=1h` (หรือ SSE ถ้าจะ push) + Chart.js
- API อยู่ใต้ `/api/*` — ห้ามชน static · Auth หน้า WebUI (admin user/pass, bcrypt, HttpOnly cookie)
- กฎ UI ยึด `docs/WEBUI_DESIGN.md` — responsive 360/768/1280, `font-size: clamp`, Chart.js bundle local (ไม่ใช้ CDN)

## ข้อแนะนำเพิ่มเติม (จากโจทย์ "แนะนำเพิ่มได้")
- alerting + notify (webhook/Telegram/email) + alert history + ack
- กราฟย้อนหลังแบบ rollup (1m/5m/1h/1d) + export CSV
- ติดตาม service/process บน host (agent เช็ค up/down)
- grouping/tag host (env=prod, location=th) + filter dashboard
- uptime/availability + offline detection + notification เมื่อ host หาย
- API token per host + revoke; audit log การเข้า WebUI
- (แนะนำ) rate-limit login + CSP/security headers WebUI

## สิ่งที่ห้ามทำ
- ห้ามใช้ `npm`/`node`/`React` บน WebUI — ล็อกเป็น Jinja2 + vanilla JS แล้ว
- ห้ามให้ agent import dependency หนัก (pandas/numpy/psutil บังคับ) — ต้อง stdlib ก่อน
- ห้าม commit `data/*.db`, `logs/`, `config.toml`, `.env`, `*.pem`, `*.key`
- ห้าม hardcode path ด้วย `/` — ใช้ `pathlib`/`os.path` (ข้ามแพลตฟอร์ม)
- ห้ามเทส agent ด้วยการยิง server จริง (ใช้ fake HTTP)
