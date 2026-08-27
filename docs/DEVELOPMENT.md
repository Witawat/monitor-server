# DEVELOPMENT.md — คู่มือ dev + เทส

## เตรียมเครื่อง
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest ruff mypy
# หรือถ้าแยก agent: .venv\Scripts\pip install -r requirements-agent.txt
```

## รัน 3 แบบ

### 1. Server dev
```powershell
# ก่อนรัน/เทส: kill process ค้าง + ล้างข้อมูลเก่า
Get-Process python | Stop-Process
Remove-Item -Recurse -Force data, logs -ErrorAction SilentlyContinue

.venv\Scripts\python -m server.main --config config.toml
# เปิด http://127.0.0.1:18080
```

### 2. Agent dev (ชี้ไป server ตัวเอง)
```powershell
.venv\Scripts\python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
```
- gen token ผ่าน WebUI (`/api/v1/auth/tokens`) หรือตั้งตรงใน config

### 3. ทดสอบ API เร็ว (curl / Invoke-RestMethod)
```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/status
Invoke-RestMethod http://127.0.0.1:18080/api/v1/hosts -Headers @{"X-Agent-Token"="<TOKEN>"}
```

## เทส (สำคัญ)
```powershell
ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q
```
> ฉันว่า mypy ต้องมี `--disable-error-code=unused-ignore` — โค้ด cross-platform (ctypes.windll/os.statvfs) ฟ้องถูก/ผิดคนละที่ตาม platform ที่รัน (ตรงกับ CI)

### กฎการเทส
- **server**: ingest เทสด้วย **mock** — ไม่พึ่ง server จริง
- **agent**: เทส push/retry/backoff ด้วย **fake HTTP server** (`http.server` / `httpx MockTransport`) — **ห้ามยิง server จริง**
- e2e (agent→server จริง) แยกเป็น integration test — ไม่อยู่ใน `pytest -q`
- ล้าง `data/*.db` + `logs/` ก่อนเทสครั้งใหญ่ (กันข้อมูลเก่าปน)
- kill process ค้างก่อนเทส: `Get-Process python | Stop-Process` + เช็คพอร์ต 18080 ว่าง

### โฟลเดอร์เทส
```
tests/                          # pytest แบน (testpaths = ["tests"])
├── test_ingest.py              # IngestService (mock)
├── test_storage.py             # Database
├── test_alerts.py              # AlertEngine / Notifier / ack
├── test_api.py / test_api_status.py / test_webui.py
├── test_collect.py / test_push.py / test_retry_backoff.py / test_selfinstall.py
├── test_config.py / test_extras.py
└── __init__.py
```
- เทส server ใช้ **mock** (ไม่พึ่ง server จริง) · เทส agent ใช้ **fake HTTP server** (`http.server`/`httpx MockTransport`) — **ห้ามยิง server จริง**
- e2e (agent→server จริง) แยกเป็น integration — ไม่อยู่ใน `pytest -q` · เทส exe ใช้ `scripts/test_exe.ps1` (13 checks)

### เทส UI (Playwright — ตรวจ responsive ตาม `WEBUI_DESIGN.md`)
- ตรวจ 360/768/1280 ไม่ overflow แนวนอน + ฟังก์ชันหลัก (login, fleet→host, chart, settings)
```powershell
# ติดตั้ง (dev dep) + รัน
.venv\Scripts\pip install playwright
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\pytest tests/ui -q
```
- เป็นแค่ UI smoke — ไม่แทน unit test; ใช้ server จริง (dev) ในเครื่อง localhost

### ตรวจ docstring ครบ (ดู `CODING_GUIDE.md`)
```powershell
.venv\Scripts\python.exe -c "import ast,pathlib;ms=[(str(p),n.name) for p in pathlib.Path('.').rglob('*.py') if '__pycache__' not in str(p) and '.venv' not in str(p) for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and not n.name.startswith('_') and ast.get_docstring(n) is None];print('missing:',ms)"
```

## งานที่ควรทำเป็นประจำ
- รัน `ruff --check`/`mypy --disable-error-code=unused-ignore`/`pytest` ก่อน commit ทุกครั้ง (ตรงกับ CI)
- CI วิ่งอัตโนมัติบน push/PR (`ruff`+`mypy`+`pytest` py3.11/3.12) — ดู `.github/workflows/ci.yml`
- release: push tag `v*` → `release.yml` สร้าง 4 binaries (Windows `.exe` ×2 + Linux ELF ×2, glibc 2.28+) + publish release อัตโนมัติ
- ใช้ `run-long.ps1` ถ้ารันคำสั่งที่อาจนาน (test suite ใหญ่/build)
