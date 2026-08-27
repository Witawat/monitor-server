# BUILD.md — การ build / package

## Server (รันจาก source หลัก)
- dev: `python -m server.main --config config.toml` หรือ `python run.py --config config.toml`
- production (exe): `monitor-server.exe` — **ไม่ต้องสั่ง `--config`** (อ่าน `config.toml` ข้าง exe อัตโนมัติ; ไม่มีก็สร้าง default + พิมพ์รหัสผ่าน admin)
- production (service): รันผ่าน service (`docs/DEPLOYMENT.md`) — ไม่ต้อง build ไฟล์พิเศษ
- dependencies: `requirements.txt` (fastapi, uvicorn, jinja2, pydantic, aiosqlite, bcrypt, python-multipart, httpx) — config TOML อ่านด้วย stdlib `tomllib` ไม่ต้องลง dep แยก

## Agent (package ตัวเล็ก)
เป้าหมาย: agent ต้องเล็ก + ติดตั้งง่าย — 2 ทางเลือก

### ทาง A: สคริปต์ Python ตรง (ง่ายสุด, เล็กสุด)
- ใช้ source `agent/` ตรง (ต้องการ Python บน target — มีอยู่แล้วบนเครื่องส่วนใหญ่)
- deploy: คัดลอก `agent/` + `shared/metric.py` ไปเครื่อง, รันเป็น service (`docs/DEPLOYMENT.md`)
- **ไม่ต้อง build** — เหมาะกับ target ที่มี Python

### ทาง B: PyInstaller onefile (ไม่ต้องมี Python บน target)
- บิวเป็น exe/elf เดี่ยว → ใช้ PyInstaller
```powershell
# จากรากโปรเจกต์ (ใช้ .venv)
.venv\Scripts\pyinstaller --noconfirm --clean --onefile `
  --name monitor-agent `
  --hidden-import urllib.request `
  agent/agent.py
# ได้ dist/monitor-agent(.exe) — เล็ก, รัน standalone
```
- **หมายเหตุ**: ใช้ได้กับ Linux/Windows แยกกัน (บิวบน OS ไหนได้ binary ของ OS นั้น) — **binary ทางการสำหรับ Linux build โดย CI** (ดู §Linux binary ด้านล่าง); build ด้วยตัวเองบน Linux ต้องใช้ Python ที่ build ด้วย `--enable-shared` (ไม่งั้น PyInstaller ล้ม)

### ทาง C: zip กระจาย
- zip `agent/` + `shared/` + `service/` → ติดตั้งด้วย script (Windows/Linux) — กลางๆ ระหว่าง A/B

## Build EXE อัตโนมัติ (server + agent + icon + UPX)

มีสคริปต์เดียวรันครบ — เลือกได้ 2 แบบ (ผลเหมือนกัน):
```powershell
# ลง dev dep ก่อน (ครั้งแรก)
.venv\Scripts\python.exe -m pip install -r requirements-build.txt

# แบบ 1: build.bat (cmd ตรง — ไม่ต้อง powershell) ← ตัวหลัก
scripts\build.bat

# แบบ 2: build.ps1 (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```
ผลลัพธ์ (ใน `dist/`):
- `monitor-server.exe` — server แบบ onefile (มี WebUI/templates/static bundled)
- `monitor-agent.exe` — agent แบบ onefile (รวม `shared/` อัตโนมัติ)

### ไฟล์ runtime อยู่ข้าง exe
- exe เป็น **onefile**: code + static+template ฝังใน exe แต่ **`data/`/`logs/`/`config.toml` ถูกสร้างและ resolve ข้างไฟล์ exe** (`dist\`) — ไม่ได้ฝังใน exe (ครั้งแรกที่รัน exe จะสร้างโฟลเดอร์+config ข้าง exe)
- รัน exe จากที่ไหนก็ได้ — `config.toml`/`data/`/`logs/` ถูก resolve ข้างตัว exe (ไม่ต้อง cd ไปโปรเจกต์)
- ครั้งแรกที่รัน server exe ถ้ายังไม่มี config → สร้าง default `config.toml` ข้าง exe + พิมพ์รหัสผ่าน admin (`admin / <random>`) แล้ว login ได้เลย
- service: `monitor-server.exe --service install|start|stop|remove` (NSSM ชี้ตัว exe เอง) · agent: `scripts\install-agent.ps1` (detect exe) · Linux: systemd unit
- ⚠️ **ทดสอบ/ใช้ runtime จาก exe เท่านั้น** — ห้ามรันจาก `.py` (`python run.py` / `python -m server.main`) เพราะ dev path resolve ไปรากโปรเจกต์ ต่างจาก exe (ข้าง `dist\`) → data/logs อยู่คนละที่ สรุปผลผิดจาก production. ดู `AGENTS.md` §กฎการทดสอบ.

รายละเอียด:
- **icon**: `scripts/make_icon.py` (Pillow) วาดหน้าจอ monitor + เส้น pulse → `build/monitor.ico` (16–256) — ใช้เป็น icon ของทั้ง 2 exe
- **UPX**: ดาวน์โหลด release ล่าสุด → `scripts/tools/upx/upx.exe` (build tool — gitignore ไม่ติด commit) แล้วบีบ exe ด้วย `--upx-dir`
- ตรวจหลัง build: `dist\monitor-agent.exe --server http://127.0.0.1:18080 --token <TOKEN> --interval 15` + รัน `dist\monitor-server.exe` แล้วเปิด WebUI
- **ทดสอบ exe ครบทุกอย่างอัตโนมัติ**: `scripts\test_exe.bat` (หรือ `scripts\test_exe.ps1 -Port 18089`) — ตรวจ 13 ข้อ (health/WebUI/login/static + API ingest/hosts/tags/metrics/alerts CRUD/export CSV + agent exe push) ด้วย config/data_dir ชั่วคราว แล้วล้างเอง

## Linux binary (Release — CI สร้าง)

- build โดย GitHub Actions (`release.yml` job **build-linux**) — **ไม่ต้อง build เองบนเครื่อง Linux**:
  - container: `quay.io/pypa/manylinux_2_28_x86_64:2026.01.04-1` (glibc 2.28 = RHEL 8 base)
  - script: `scripts/build-manylinux.sh` — build **CPython 3.11.14 จาก source ด้วย `--enable-shared`** (Python ใน image ไม่มี shared lib → PyInstaller ล้ม; ใช้เวลา ~4 นาที) → venv → `pytest` → PyInstaller ×2 → smoke test `--help` → ตรวจ GLIBC symbol ≤ 2.28
  - ผลลัพธ์: `dist/monitor-server` + `dist/monitor-agent` — **glibc 2.28+** (รันได้บน Alma/Rocky 8-9, RHEL 8-9, CentOS Stream 9, Ubuntu 20.04+, Debian 11+, Fedora 32+)
- ทำไมต้อง glibc 2.28: PyInstaller binary ฝัง glibc ของเครื่อง build — build บน glibc 2.28 → รันได้บน glibc ≥ 2.28 (ถ้า build บน Ubuntu 24.04 = glibc 2.39 → รันได้บน 24.04+ เท่านั้น — ปัญหาเดิมที่แก้ใน v0.3.3)
- รันซ้ำเอง (คำสั่งเดียวกับ CI):
  ```bash
  docker run --rm -v "$PWD":/src -w /src \
    quay.io/pypa/manylinux_2_28_x86_64:2026.01.04-1 \
    bash scripts/build-manylinux.sh
  ```
- `scripts/build.sh` — build Linux เร็วๆ จาก venv ในเครื่อง (dev เท่านั้น) — **glibc ของผลลัพธ์ = glibc ของเครื่องที่ build** (ไม่รับรอง 2.28) — ใช้ release binary จาก CI สำหรับกระจาย
- ถ้าเปลี่ยน manylinux image tag ใหม่: Python ใน image อาจไม่มี shared lib → probe build ก่อน (ดู `docs/SESSION_STATE.md`)

## CI / Release อัตโนมัติ (GitHub Actions)
- **CI** (`.github/workflows/ci.yml`): `ruff` + `mypy --disable-error-code=unused-ignore` + `pytest` บน **py3.11/3.12** ทุก push/PR → master (กัน regression)
- **Release** (`.github/workflows/release.yml`): push tag `v*` (หรือ trigger ด้วยมือ — `workflow_dispatch` + กรอก tag) → 2 jobs:
  - **Windows** (windows-latest): venv + `scripts\build.bat` (icon+UPX+PyInstaller) → `monitor-server.exe` + `monitor-agent.exe`
  - **Linux** (docker manylinux_2_28): `scripts/build-manylinux.sh` → `monitor-server` + `monitor-agent` (glibc 2.28+)
  → publish release + attach 4 ไฟล์ + notes จากเทมเพลต `.github/release-notes.md` (แทนที่ version อัตโนมัติ)
- วิธีใช้: bump `__version__` ใน `server/__init__.py` + `version` ใน `pyproject.toml` + `CHANGELOG.md` → `git tag v0.3.3 && git push origin v0.3.3`

## เกณฑ์
- agent ห้ามมี dependency หนัก — ถ้าใช้ PyInstaller ต้องตรวจ size ≤ ~15MB และรันบนเครื่องไม่มี Python
- ทดสอบบนเครื่องไม่มี Python (ถ้าใช้ทาง B) ก่อนปิดงาน
- ล้าง `build/` `dist/` ก่อน commit (gitignore แล้ว)

## ตรวจหลัง build
```powershell
.\dist\monitor-agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
# ดู host ขึ้นใน WebUI / GET /api/v1/hosts
```
