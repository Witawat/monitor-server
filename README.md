[![CI](https://github.com/Witawat/monitor-server/actions/workflows/ci.yml/badge.svg)](https://github.com/Witawat/monitor-server/actions/workflows/ci.yml)
[![Release](https://github.com/Witawat/monitor-server/actions/workflows/release.yml/badge.svg)](https://github.com/Witawat/monitor-server/actions/workflows/release.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![version](https://img.shields.io/badge/version-0.2.0-blue.svg)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

# monitor-server — ข้ามแพลตฟอร์ม Server Monitoring + WebUI

ระบบ monitor server ข้ามแพลตฟอร์ม (Linux + Windows) ที่มี **central server** รวบรวม metrics จากหลายเครื่อง แล้วแสดงผ่าน **Web UI แบบ dashboard** (แรงบันดาลใจจาก DigitalOcean / Plesk) โดยมี **agent ขนาดเล็ก** ติดตั้งบนแต่ละเครื่องที่ถูก monitor คอยเก็บ metrics แล้ว **push** มาที่ server แบบรวดเร็ว

> 💡 เมื่อรัน server แล้ว **เปิด WebUI ใน browser อัตโนมัติ** — ใช้ `--no-browser` เพื่อปิด

> สแต็ก + กฎถูกล็อกใน `AGENTS.md` — ห้ามเปลี่ยนสถาปัตยกรรม push model หรือ stack โดยไม่ตกลงก่อน

## สถาปัตยกรรมโดยย่อ

```
┌─────────────┐   HTTP POST (JSON batch)   ┌──────────────────┐   Web UI
│  agent (N)  │ ─────────────────────────► │  monitor-server  │ ◄───── Browser
│  stdlib py  │   /api/v1/ingest           │  FastAPI + SQLite│        :18080
└─────────────┘   X-Agent-Token            └──────────────────┘
     small client on each monitored host      central collector
```

- **Agent**: สคริปต์ Python stdlib ขนาดเล็ก เก็บ CPU/RAM/Disk/Net/Uptime แล้ว push เป็น batch พร้อม retry + backoff เมื่อ offline
- **Server**: FastAPI รับ push → เขียน SQLite (time-series) → แสดง dashboard + กราฟย้อนหลัง + alerting
- **ข้ามแพลตฟอร์ม**: agent/server รันได้ทั้ง Linux และ Windows; deploy เป็น service (systemd / NSSM)

## ฟีเจอร์หลัก (ใช้งานได้แล้ว)

| หมวด | รายละเอียด |
|------|------------|
| Fleet dashboard | รายการ host + การ์ดสถานะ (OS icon + CPU/RAM/Disk/Net/Uptime) + ออนไลน์/ออฟไลน์ + สถิติรวม + กรอง/search/tag |
| Per-host dashboard | เลือก host → กราฟย้อนหลัง per metric (rollup 1m/5m/1h/1d) + KPI + service watch + chart flow 1h–45d (ดูย้อนหลัง 45 วัน) |
| Agent | push model, batch + retry + backoff + queue offline, stdlib-only |
| Alerting | เงื่อนไข threshold ต่อ host/metric + history + ack + notify (webhook/Telegram) + host-down |
| Auth/Security | API token ต่อ host (`X-Agent-Token`), rate limit ingest + login, CSP/security headers |
| เสริม | grouping/tag host, uptime/offline detection, process/service watch, export CSV, alert rule CRUD UI |

## โครงสร้าง

```
monitor-server/
├── run.py                # entry หลัก server (uvicorn + service wrapper)
├── server/               # FastAPI: api/, storage/, alerting/, webui/
├── agent/                # collector + push loop (stdlib) + service/
├── shared/               # metric.py — schema + ingest contract (2 ฝั่งใช้ร่วม)
├── tests/                # pytest (server + agent)
├── scripts/              # deploy/service helper (ps1 + sh)
└── docs/                 # เอกสารออกแบบทั้งหมด
```

## ติดตั้ง (dev)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest ruff mypy
```

## รัน (production ใช้ exe — dev ใช้ python)

```powershell
# ── PRODUCTION: ใช้ exe ที่ build (dist\) — ไฟล์ config/data/logs อยู่ข้าง exe ──

# server (ไม่ต้อง --config — อ่าน config.toml ข้าง exe อัตโนมัติ; ไม่มีก็สร้างให้)
.\dist\monitor-server.exe        # เปิด http://127.0.0.1:18080

# agent: ติดตั้งเป็น service อัตโนมัติ (เขียน agent.cfg ข้าง exe + NSSM/systemd)
.\dist\monitor-agent.exe --install --server http://127.0.0.1:18080 --token <TOKEN> --interval 15 [--ports 80:web,443:https] [--watch nginx,mysql]
# รัน agent ตรง ๆ (foreground)
.\dist\monitor-agent.exe --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
# ลบ service
.\dist\monitor-agent.exe --uninstall
```

> ⚠️ **คนได้แค่ `dist\monitor-agent.exe` (ไม่มี python) ใช้คำสั่งข้างบนได้เลย** — ไม่ต้อง `python -m agent.agent`.

```powershell
# ── DEV: ใช้ python (รากโปรเจกต์) — ไฟล์ data/logs อยู่รากโปรเจกต์ ──

# server (dev)
python -m server.main --config config.toml            # เปิด http://127.0.0.1:18080
# หรือ python run.py --config config.toml

# agent (dev — ชี้ไป server ตัวเอง, token จาก WebUI)
python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
```

> 💡 **production ใช้ exe ด้านบน** — ตัว `--config config.toml` ที่เห็นในโหมด dev ไม่จำเป็นสำหรับ exe (exe อ่าน config ข้างตัวเองอัตโนมัติ)

## Build EXE (server + agent)

```powershell
# ลง dev dep ครั้งแรก
.venv\Scripts\pip install -r requirements-build.txt

# build (สร้าง icon monitor+pulse + PyInstaller + บีบด้วย UPX ล่าสุด)
scripts\build.bat                 # ตัวหลัก — cmd ตรง
# หรือ: powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

- ผลลัพธ์ใน `dist/`: `monitor-server.exe` + `monitor-agent.exe` (onefile, มี icon, UPX แล้ว)
- icon: `scripts/make_icon.py` → `build/monitor.ico` (16–256) · UPX: `scripts/tools/upx/upx.exe` (ดาวน์โหลดอัตโนมัติครั้งแรก)
- **ไฟล์อยู่ข้าง exe**: รัน exe จากที่ไหนก็ได้ — `config.toml`/`data/`/`logs/` จะถูกสร้าง/ใช้ข้างตัว exe; ครั้งแรกถ้ายังไม่มี config จะสร้าง default + พิมพ์รหัสผ่าน admin
- **service**: `monitor-server.exe --service install|start|stop|remove` (NSSM) · agent `--install` สร้าง service เอง (NSSM/systemd) หรือ `scripts\install-agent.ps1` · Linux ใช้ systemd unit
- ดูรายละเอียดเต็ม: `docs/BUILD.md`

## ทดสอบ EXE ที่ build

```powershell
scripts\test_exe.bat        # หรือ: powershell -ExecutionPolicy Bypass -File scripts\test_exe.ps1 -Port 18089
```

ตรวจ end-to-end 13 ข้อ: server exe (health/WebUI/login/static), API (ingest/hosts/tags/metrics/alerts CRUD/export CSV), และ agent exe push จริง → host ขึ้น ใช้ config/data_dir ชั่วคราว (พอร์ต 18089) แล้วล้างอัตโนมัติ

> ⚠️ **ทดสอบ/ใช้จาก `.exe` เท่านั้น** — ห้ามรันจาก `.py` (`python run.py`) เพราะ `data/`+`logs/`+`config.toml` ถูก resolve **ข้างไฟล์ exe** (`sys.frozen=True` → ข้าง `dist\`), ไม่ได้ฝังใน exe และไม่ใช่รากโปรเจกต์แบบ dev path. รัน `.py` จะได้ข้อมูลอยู่คนละที่ → สรุปผลผิดจาก production. ดู `AGENTS.md` §กฎการทดสอบ.

## ตรวจก่อนส่งงาน

```powershell
ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q
```

## CI / Release อัตโนมัติ

- **`.github/workflows/ci.yml`** — ครัน `ruff` + `mypy` + `pytest` บน Python 3.11/3.12 ทุก push/PR → master
- **`.github/workflows/release.yml`** — เมื่อ push tag `v*` → build `monitor-server.exe` + `monitor-agent.exe` (Windows runner) แล้ว publish GitHub release + attach 2 exe
- release อัตโนมัติ: `git tag v0.3.0 && git push origin v0.3.0`

## เอกสาร

- **`docs/USER_GUIDE.md`** — คู่มือการใช้งาน (Quick Start → WebUI → Alerts → Service → Troubleshoot) ← เริ่มที่นี่
- `AGENTS.md` — กฎ + stack + คำสั่งหลัก
- `PRODUCT.md` — product context (Users/Purpose/Principles)
- `KNOWLEDGE_BASE.md` — ความรู้ก่อนเขียนโค้ด
- `docs/ARCHITECTURE.md` / `CONFIG.md` / `API.md` / `CODING_GUIDE.md` / `PLAN.md` / `BUILD.md` / `DEPLOYMENT.md` / `DEVELOPMENT.md` / `WEBUI_DESIGN.md` / `WEBUI_IMPROVEMENT_PLAN.md`

## License

MIT — ดู `LICENSE` (เพิ่มก่อน release)
