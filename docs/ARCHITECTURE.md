# ARCHITECTURE.md — สถาปัตยกรรม

## ภาพรวม

```
┌─────────────────────┐
│   agent (N เครื่อง)  │   Python stdlib เล็กๆ
│  agent/agent.py     │   collect → batch → push
│  collect loop       │
└─────────┬───────────┘
          │  POST /api/v1/ingest  (JSON batch, X-Agent-Token)
          ▼
┌─────────────────────────────────────────────┐
│              server/  (FastAPI)             │
│  ┌────────────┐  ┌─────────────┐  ┌─────────┐
│  │ api/        │  │ ingest.py   │  │ storage/│
│  │ routers     │  │ validate+   │  │ SQLite  │
│  │             │  │ rate limit  │  │ time-   │
│  └──────┬──────┘  └──────┬──────┘  │ series  │
│         │                │         └────┬────┘
│  ┌──────▼──────┐  ┌──────▼──────┐       │
│  │ alerting/   │  │ webui/      │◄──────┘
│  │ threshold+  │  │ Jinja2 SPA  │
│  │ notify      │  │ + Chart.js  │
│  └──────┬──────┘  └─────────────┘
│         │  webhook/Telegram
└─────────┼──────────────────────────────────┘
          ▼
   Admin Browser :18080
```

## ทำไมแยกแบบนี้

- **push model** — agent เป็นฝ่ายรุก, server เปิดรับฝั่งเดียว → agent อยู่หลัง NAT ได้ ไม่ต้อง expose port
- **`shared/` กัน drift** — schema metric อยู่ในที่เดียว, ทั้ง server (validate) และ agent (สร้าง) ใช้ร่วม
- **SQLite เป็น time-series store** — ต่อ host, ต่อ metric; retention/rollup เป็นงานของ `storage/`
- **agent กับ server แยกเป็นคนละส่วนโดยสิ้นเชิง** — agent stdlib เท่านั้น, ไม่ import server

## โมดูลและหน้าที่

| โมดูล | หน้าที่ | หมายเหตุ |
|-------|--------|----------|
| `server/main.py` | สร้าง FastAPI app, mount `/api` + `/` (webui), lifespan เปิด DB | entry: `python -m server.main` |
| `run.py` | wrapper รัน server + service mode (systemd/NSSM) | root entry เหมือน proxy-server |
| `server/api/ingest.py` | รับ `POST /api/v1/ingest` → `ingest.py` | auth ด้วย token |
| `server/ingest.py` | validate batch, rate limit, upsert host, เขียน metrics | หัวใจการรับ push |
| `server/api/hosts.py` | list hosts + status (online/offline) | online = มี push ภายใน timeout |
| `server/api/metrics.py` | `GET /hosts/{id}/metrics?range=` → series | rollup ตาม range |
| `server/storage/` | async SQLite access, migrations, retention, rollup | aiosqlite + WAL |
| `server/alerting/` | ประเมิน alert rules หลัง ingest + ส่ง notify | webhook/Telegram |
| `server/api/auth.py` | login WebUI (bcrypt + HttpOnly cookie), token gen/revoke | |
| `server/webui/` | Jinja2 SPA + static (Chart.js local) | กฎใน `WEBUI_DESIGN.md` |
| `agent/agent.py` | collect (stdlib) + push loop + retry/backoff + queue | entry: `monitor-agent.exe` (prod) หรือ `python -m agent.agent` (dev) |
| `agent/config.py` | server_url + token + interval (arg/env) | |
| `shared/metric.py` | metric snapshot schema + contract | บางพอให้ agent ใช้ |

## ลำดับ (data flow)

1. **agent**: collect → build batch (list of snapshots) → `POST /api/v1/ingest` ทุก `interval`
2. **server ingest**: check token → rate limit → validate schema (`shared/metric.py`) → upsert host (last_seen) → insert rows
3. **alerting** (หลัง insert): อ่าน rules → ถ้าเกิน threshold → บันทึก history + ส่ง notify
4. **webui**: poll `GET /api/v1/hosts` + `GET /hosts/{id}/metrics?range=` → Chart.js
5. **remote config** (agent ไม่ restart): server เก็บ `desired_config` ต่อ host → คืนใน ingest response (`config`) → agent อ่านแล้ว apply (interval/watch/ports/max_batch) ทุก loop; ผู้ใช้ตั้งผ่าน WebUI (`PUT /hosts/{id}/config`)

## Metric schema (โดยย่อ — เต็มใน `shared/metric.py`)

```json
{
  "host_id": "uuid",
  "hostname": "web-01",
  "platform": "linux",
  "ts": 1750000000,
  "cpu_percent": 23.5,
  "load": [0.2, 0.4, 0.3],
  "memory": {"total": 8589934592, "used": 3221225472, "percent": 37.5},
  "swap": {"total": 0, "used": 0},
  "disk": [{"mount": "/", "total": 0, "used": 0, "percent": 0}],
  "net": [{"iface": "eth0", "rx_bytes": 0, "tx_bytes": 0}],
  "ports": [{"port": 80, "name": "web", "up": true}],
  "uptime": 86400,
  "procs": 240
}
```

> `net.rx_bytes/tx_bytes` เป็น **cumulative counter** — server คำนวณ rate (bytes/s) จาก delta เอง

## ข้อจำกัดที่ต้องรู้

- agent ห้าม import `server/` — ใช้แค่ `shared/` ที่บาง (ถ้าจำเป็น)
- SQLite async: ใช้ WAL mode + 1 writer ต่อเนื่อง กัน lock; rollup ลดขนาดไฟล์
- interval agent ไม่ควรต่ำเกิน (default 15s) — กัน flood/ขนาด DB โต
- retention: กำหนดใน config (`retention_raw_days`, default 45) — เก็บ raw/กราฟย้อนหลัง 45 วัน แล้ว rollup 1m/5m/1h/1d
