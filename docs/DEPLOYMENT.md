# DEPLOYMENT.md — deploy / service

> ทั้ง server และ agent ต้องรันเป็น service ได้บน Linux (systemd) + Windows (NSSM / Windows Service). scripts อยู่ที่ `scripts/`.

## Server

### Linux (systemd)
สร้าง `/etc/systemd/system/monitor-server.service`:
```ini
[Unit]
Description=Monitor Server
After=network.target

[Service]
Type=simple
User=monitor
WorkingDirectory=/opt/monitor-server
ExecStart=/usr/bin/python3 -m server.main --config /etc/monitor-server/config.toml
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-server
```

### Windows (NSSM หรือ Windows Service)
- NSSM (ง่าย, ไม่ต้องเขียนโค้ด service):
```powershell
nssm install MonitorServer "C:\Program Files\Python311\python.exe" "-m server.main --config C:\monitor-server\config.toml"
nssm start MonitorServer
```
- หรือ Windows Service ผ่าน wrapper ใน `run.py` (แบบ proxy-server: `install|start|stop|remove`)

## Agent

### Linux (systemd)
สร้าง `/etc/systemd/system/monitor-agent.service`:
```ini
[Unit]
Description=Monitor Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m agent.agent --server http://SERVER:18080 --token TOKEN --interval 15
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now monitor-agent
```
> ถ้าใช้ PyInstaller binary (ทาง B ใน `BUILD.md`): `ExecStart=/opt/monitor-agent/monitor-agent --server ...`

### Windows (NSSM)
```powershell
nssm install MonitorAgent "C:\Program Files\Python311\python.exe" "-m agent.agent --server http://SERVER:18080 --token TOKEN --interval 15"
nssm start MonitorAgent
```
หรือใช้ binary `.exe` (ทาง B) เป็น target ตรง.

## ขั้นตอนติดตั้งจริง (script)
`scripts/` มี helper:
- `scripts/install-server.ps1` / `.sh` — สร้าง service + config + data_dir
- `scripts/install-agent.ps1` / `.sh` — สร้าง service agent
- ใช้ pathlib/os.path ในโค้ด; script รับ param server_url + token

## CI / Release
- CI วิ่งบนทุก push/PR (`.github/workflows/ci.yml`) — `ruff`+`mypy`+`pytest` py3.11/3.12 (กัน regression)
- release: push tag `v*` → `release.yml` build `monitor-server.exe` + `monitor-agent.exe` (Windows) + publish release พร้อมแนบ exe (`gh release`)
- หลัง bump version ใน `pyproject.toml`/`CHANGELOG.md` → `git tag v0.3.0 && git push origin v0.3.0`

## สิ่งที่ต้องระวัง
- `config.toml`/`.env`/`*.pem`/`*.key`/`data/*.db`/`logs/` — **ห้าม commit**
- server: เปิดพอร์ต (18080) — ถ้า agent อยู่หลัง NAT ก็ push เข้ามาได้ (push model)
- ⚠️ **agent เครื่องอื่น push ไม่ถึง ถ้า `server.host = "127.0.0.1"`** (default ฟังแค่ localhost) — ต้องตั้งเป็น `0.0.0.0` ใน config.toml ก่อน deploy จริง (ดู `docs/CONFIG.md`)
- agent: ไม่ต้องเปิดพอร์ตใดๆ (เป็น client push)
- permission: service user ต้องเขียน `data/` + `logs/` ได้
- หลัง deploy → ตรวจ `/api/health` + host ขึ้นใน WebUI
