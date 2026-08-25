# monitor-server — ข้ามแพลตฟอร์ม Server Monitoring + WebUI

ระบบ monitor server ข้ามแพลตฟอร์ม (Linux + Windows) ที่มี **central server** รวบรวม metrics จากหลายเครื่อง แล้วแสดงผ่าน **Web UI แบบ dashboard** (แรงบันดาลใจจาก DigitalOcean / Plesk) โดยมี **agent ขนาดเล็ก** ติดตั้งบนแต่ละเครื่องที่ถูก monitor คอยเก็บ metrics แล้ว **push** มาที่ server แบบรวดเร็ว

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

## ฟีเจอร์หลัก (วางแผน)

| หมวด | รายละเอียด |
|------|------------|
| Fleet dashboard | รายการ host + การ์ดสถานะ (CPU/RAM/Disk/Net/Uptime) + ออนไลน์/ออฟไลน์ |
| Per-host dashboard | เลือก host → กราฟย้อนหลัง per metric (1m/5m/1h/1d) + ข้อมูลเรียลไทม์ |
| Agent | push model, batch + retry + backoff + queue offline, stdlib-only |
| Alerting | เงื่อนไข threshold ต่อ host/metric + history + notify (webhook/Telegram) |
| Auth/Security | API token ต่อ host (`X-Agent-Token`), rate limit ingest, login admin WebUI |
| เสริม (แนะนำ) | grouping/tag host, uptime/offline detection, process/service watch, export CSV |

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

## รัน

```powershell
# server (dev)
python -m server.main --config config.toml       # เปิด http://127.0.0.1:18080
# หรือ python run.py --config config.toml

# agent (dev — ชี้ไป server ตัวเอง, token จาก WebUI)
python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
```

## ตรวจก่อนส่งงาน

```powershell
ruff check .; mypy server agent shared; pytest -q
```

## เอกสาร

- `AGENTS.md` — กฎ + stack + คำสั่งหลัก
- `PRODUCT.md` — product context (Users/Purpose/Principles)
- `KNOWLEDGE_BASE.md` — ความรู้ก่อนเขียนโค้ด
- `docs/ARCHITECTURE.md` / `CONFIG.md` / `API.md` / `CODING_GUIDE.md` / `PLAN.md` / `BUILD.md` / `DEPLOYMENT.md` / `DEVELOPMENT.md` / `WEBUI_DESIGN.md`

## License

MIT — ดู `LICENSE` (เพิ่มก่อน release)
