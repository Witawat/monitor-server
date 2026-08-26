# BUILD.md — การ build / package

## Server (รันจาก source หลัก)
- dev: `python -m server.main --config config.toml` หรือ `python run.py --config config.toml`
- production: รันผ่าน service (`docs/DEPLOYMENT.md`) — ไม่ต้อง build ไฟล์พิเศษ
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
- **หมายเหตุ**: ใช้ได้กับ Linux/Windows แยกกัน (บิวบน OS ไหนได้ binary ของ OS นั้น)

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

รายละเอียด:
- **icon**: `scripts/make_icon.py` (Pillow) วาดหน้าจอ monitor + เส้น pulse → `build/monitor.ico` (16–256) — ใช้เป็น icon ของทั้ง 2 exe
- **UPX**: ดาวน์โหลด release ล่าสุด → `scripts/tools/upx/upx.exe` (build tool — gitignore ไม่ติด commit) แล้วบีบ exe ด้วย `--upx-dir`
- ตรวจหลัง build: `dist\monitor-agent.exe --server http://127.0.0.1:18080 --token <TOKEN> --interval 15` + รัน `dist\monitor-server.exe` แล้วเปิด WebUI

## เกณฑ์
- agent ห้ามมี dependency หนัก — ถ้าใช้ PyInstaller ต้องตรวจ size ≤ ~15MB และรันบนเครื่องไม่มี Python
- ทดสอบบนเครื่องไม่มี Python (ถ้าใช้ทาง B) ก่อนปิดงาน
- ล้าง `build/` `dist/` ก่อน commit (gitignore แล้ว)

## ตรวจหลัง build
```powershell
.\dist\monitor-agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
# ดู host ขึ้นใน WebUI / GET /api/v1/hosts
```
