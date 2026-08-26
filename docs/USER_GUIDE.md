# คู่มือการใช้งาน — monitor-server

> คู่มือสำหรับผู้ใช้ (User Manual) ครอบคลุมการติดตั้ง / ตั้งค่า / ใช้งานระบบ monitor server
> ประกอบด้วย **server** (central collector + WebUI), **agent** (client ที่ติดตั้งบนเครื่องที่ถูก monitor), และ **WebUI** (dashboard)

---

## สารบัญ

1. [ภาพรวมระบบ](#1-ภาพรวมระบบ)
2. [Quick Start (เริ่มต้นเร็ว)](#2-quick-start-เริ่มต้นเร็ว)
3. [ติดตั้งและรัน Server](#3-ติดตั้งและรัน-server)
4. [ติดตั้งและรัน Agent](#4-ติดตั้งและรัน-agent)
5. [ใช้งาน WebUI](#5-ใช้งาน-webui)
6. [Alerting (การแจ้งเตือน)](#6-alerting-การแจ้งเตือน)
7. [Service (รันเป็นบริการ)](#7-service-รันเป็นบริการ)
8. [Export / ข้อมูลย้อนหลัง](#8-export--ข้อมูลย้อนหลัง)
9. [การตั้งค่าขั้นสูง](#9-การตั้งค่าขั้นสูง)
10. [แก้ปัญหาทั่วไป](#10-แก้ปัญหาทั่วไป)

---

## 1. ภาพรวมระบบ

```
  [เครื่องที่ถูก monitor]                       [เครื่องที่รัน server]
┌────────────────────┐   HTTP POST (JSON)   ┌─────────────────────┐
│  agent (เล็ก)      │ ───────────────────► │  monitor-server      │
│  เก็บ CPU/RAM/     │   /api/v1/ingest     │  FastAPI + SQLite    │◄──── WebUI
│  Disk/Net/Ports    │   X-Agent-Token      │  + WebUI dashboard   │   (browser)
└────────────────────┘                      └─────────────────────┘
```

- **Agent** (ติดตั้งบนเครื่องที่ถูก monitor): เก็บ metric แล้ว **push** ไปที่ server (ไม่ต้องเปิด port รับจากนอก)
- **Server**: รับข้อมูล + เก็บลง SQLite (time-series) + แสดง WebUI + ตรวจ alert
- **WebUI**: ดู Fleet (ภาพรวม), รายละเอียดต่อ host, Alerts, ตั้งค่า token

**ข้อดีหลัก**: agent เล็ก (stdlib เท่านั้น), ข้ามแพลตฟอร์ม (Linux/Windows), เป็น service ได้ทั้งคู่

---

## 2. Quick Start (เริ่มต้นเร็ว)

### 2.1 เริ่ม server ก่อน

```powershell
# (Windows) จากโฟลเดอร์โปรเจกต์
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python run.py --config config.toml
```

เปิด browser ที่ `http://127.0.0.1:18080` → เข้าสู่ระบบด้วย `admin` + รหัสผ่านที่ตั้งไว้ใน config.

> 💡 ถ้ารัน **exe** (server): ครั้งแรกที่รันถ้ายังไม่มี config จะสร้าง `config.toml` อัตโนมัติ + พิมพ์รหัสผ่าน admin ให้ (เช่น `admin / <random>`).

### 2.2 ได้ token จาก WebUI

1. Login เข้า WebUI
2. ไปที่ **ตั้งค่า → Agent Token → สร้าง token** → ใส่ `host_id` (เช่น `web-01`)
3. คัดลอก token (แสดงครั้งเดียว)

### 2.3 ติดตั้ง agent

> ใช้ **`monitor-agent.exe`** ที่ build (ใน `dist\`) — คนได้แค่ exe ก็ใช้ได้เลย (ไม่ต้องมี python). รันจากโฟลเดอร์เดียวกับ exe → `agent.cfg` เขียนข้าง exe.

```powershell
# ติดตั้งเป็น service อัตโนมัติ (เขียน agent.cfg ข้าง exe + สร้าง service ให้เอง: NSSM/systemd)
monitor-agent.exe --install --server http://127.0.0.1:18080 --token <TOKEN> --interval 15 --ports 80:web,443:https --watch nginx

# หรือรันตรง ๆ (foreground)
monitor-agent.exe --server http://127.0.0.1:18080 --token <TOKEN> --interval 15

# ลบ service
monitor-agent.exe --uninstall
```

> 💡 **dev** (มีซอร์สโค้ด): ใช้ `python -m agent.agent ...` แทน `monitor-agent.exe` — ดู §4.2.
> `--install` สร้าง service Windows (NSSM) / Linux (systemd).

---

## 3. ติดตั้งและรัน Server

### 3.1 โหมด dev (จากโค้ด)

```powershell
python run.py --config config.toml
# หรือ
python -m server.main --config config.toml
```

> 💡 เมื่อรัน server แล้ว **เปิด WebUI ใน browser อัตโนมัติ** (url = `http://<host>:<port>/`)
> ถ้าไม่อยากเปิด ใส่ `--no-browser` ท้ายคำสั่ง

### 3.2 โหมด exe (build แล้ว) — แนะนำสำหรับ production

```powershell
# รัน exe (ไม่ต้อง --config — อ่าน config.toml ข้าง exe อัตโนมัติ, เปิด WebUI ใน browser)
monitor-server.exe
# ไม่เปิด browser อัตโนมัติ
monitor-server.exe --no-browser
# ระบุ config ตำแหน่งอื่น (ไม่ค่อยต้องทำ — ปกติข้าง exe)
monitor-server.exe --config "D:\path\config.toml"
```

**ไฟล์ runtime อยู่ข้าง exe**: `config.toml` + `data/` + `logs/` ถูกสร้าง/ใช้**ข้างตัว exe** (resolve ข้าง `dist\` เสมอ ไม่ใช่ cwd ไม่ต้อง `cd` ไปที่อื่น) — ครั้งแรกที่รันถ้ายังไม่มี config จะสร้าง default + พิมพ์รหัสผ่าน admin.

### 3.3 Config (config.toml)

ดูรายละเอียดเต็มใน `docs/CONFIG.md`. สรุปค่าสำคัญ:

| ส่วน | ค่า | ค่าเริ่มต้น |
|------|-----|-----------|
| `[server]` `host/port` | ที่อยู่ที่ server รับ | `127.0.0.1` / `18080` |
| `[webui]` `admin_user/pass_hash` | login WebUI | `admin` / bcrypt hash |
| `[ingest]` `rate_limit_per_min` | กัน flood ต่อ IP | `1200` |
| `[ingest]` `offline_timeout_sec` | ถ้าไม่มี push เกินนี้ = offline | `60` |
| `[storage]` `retention_raw_days` | เก็บกราฟย้อนหลังได้ | `45` วัน |
| `[storage]` `rollup_intervals` | บีบ raw เป็น rollup | `["1m","5m","1h","1d"]` |
| `[alerting]` `rules` | กฎ alert (array) | — |

> เปลี่ยน `host = "0.0.0.0"` ถ้าต้องการให้ agent/เครื่องอื่นเข้าได้จากนอก

### 3.4 เปลี่ยนรหัสผ่าน admin

```powershell
# gen hash
python -m server.webui.auth --hash "รหัสผ่านใหม่"
# เอา hash ไปใส่ [webui] admin_pass_hash ใน config.toml แล้ว restart
```

---

## 4. ติดตั้งและรัน Agent

Agent คือตัวที่ติดตั้งบน **เครื่องที่ถูก monitor** — เก็บ metric แล้ว push ไป server.

### 4.1 Arguments (flags)

| Flag | หน้าที่ | ตัวอย่าง |
|------|--------|---------|
| `--server` | URL ของ server (บังคับ) | `http://127.0.0.1:18080` |
| `--token` | agent token จาก WebUI (บังคับ) | `<TOKEN>` |
| `--interval` | รอบเก็บข้อมูล (วินาที) | `15` |
| `--watch` | service/process ที่เฝ้าดู | `nginx,mysql` |
| `--ports` | TCP port ที่เฝ้าดูว่าเปิด/ปิด | `80:web,443:https` |
| `--max-batch` | จำนวน snapshot สูงสุดต่อ request (default 100) | `100` |
| `--install` | ติดตั้งเป็น service + เขียน agent.cfg | — |
| `--uninstall` | ลบ service | — |
| `--config` | ชี้ไฟล์ agent.cfg | `agent.cfg` |

**env ทางเลือก**: `MONITOR_SERVER_URL` / `MONITOR_TOKEN` / `MONITOR_INTERVAL` / `MONITOR_PORTS` / `MONITOR_WATCH`

### 4.2 วิธีรัน

```powershell
# ── PRODUCTION (exe ที่ build — ใช้ได้แม้ไม่มี python) ──
# 1) รันตรง ๆ (foreground)
monitor-agent.exe --server http://127.0.0.1:18080 --token <TOKEN> --interval 15

# 2) รัน+เฝ้าดู service และ port
monitor-agent.exe --server http://... --token <TOKEN> --watch nginx,postgres --ports 80:web,443:https

# 3) ติดตั้งเป็น service (เขียน agent.cfg ข้าง exe + สร้าง service) — แนะนำ
monitor-agent.exe --install --server http://... --token <TOKEN> --interval 15 --ports 80:web,443:https --watch nginx
# ลบ service
monitor-agent.exe --uninstall

# ── DEV (มีซอร์สโค้ด) ใช้ python แทน monitor-agent.exe ──
python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
python -m agent.agent --install --server http://... --token <TOKEN> --interval 15
python -m agent.agent --uninstall
```

**การอ่าน config**: หลัง `--install` เขียน `agent.cfg` **ข้าง exe** ไว้ — รัน `monitor-agent.exe` (ไม่มี args) จะอ่านจากไฟล์อัตโนมัติ.
> ลำดับความสำคัญ: `--server/--token` (arg) > `MONITOR_*` (env) > `agent.cfg` (ไฟล์) > default
> ⚠️ ไฟล์ `agent.cfg` + `host_id` + `queue.json` ถูกเขียน**ข้าง exe** — ไม่ลบไฟล์พวกนี้ถ้ายังต้องการให้ agent จำตัวตน/queue ต่อ

### 4.3 (option) ใช้ exe

```powershell
dist\monitor-agent.exe --install --server http://... --token <TOKEN> --interval 15
# state (host_id/queue) เก็บข้าง exe
```

---

## 5. ใช้งาน WebUI

เข้าที่ `http://<server>:18080` แล้ว login. มี 4 section (หน้าเดียวเลื่อนยาว):

| เมนู | เนื้อหา |
|------|--------|
| Fleet | ภาพรวม host ทั้งหมด (การ์ด + OS icon + สถิติ) |
| Host | รายละเอียดรายเครื่อง (KPI, กราฟ, ports, services, alert) |
| Alerts | กฎ alert + ประวัติ + ack |
| ตั้งค่า | Agent Token + ข้อมูล server |

### 5.1 Fleet (ภาพรวม)

- **การ์ด host**: ชื่อ + OS icon + badge ออนไลน์/ออฟไลน์ + CPU/RAM/Disk + net + uptime + **sparkline** (แนวโน้ม) + เตือน service หยุด
- **สถิติด้านบน**: จำนวนเครื่อง / ออนไลน์ / ออฟไลน์ / Linux / Windows
- **กรอง**: ปุ่ม ทั้งหมด / ออนไลน์ / ออฟไลน์ + ค้นหา (ช่องบน) + tag filter (`#prod` ฯลฯ)
- **+ เพิ่มเครื่องใหม่**: เปิดวิซาร์ดระบุค่า agent สำหรับเครื่องใหม่ (host_id / interval / watch / ports / max-batch — มีคำอธิบายใต้ฟิลด์) → สร้าง token + พิมพ์คำสั่งให้คัดลอกไปรันบนเครื่องนั้น (ดู §5.5)
- **คลิกการ์ด** → ไปที่รายละเอียดของ host นั้น (section Host)

### 5.2 Host (รายละเอียดรายเครื่อง)

- เลือก host จาก **dropdown** (หรือคลิกการ์ดใน Fleet)
- **แก้ไขค่า Host** (ปุ่ม "แก้ไข" ใน toolbar): modal แก้ชื่อ (hostname) + tags + ค่า agent ระยะไกล (interval/watch/ports/max_batch) — agent จะ pull ค่าใหม่ในรอบถัดไป (ไม่ต้อง restart) + ปุ่มลบ host (confirm)
- **Realtime อัตโนมัติ**: KPI / services / ports / กราฟ **อัปเดตเองทุก ~5 วิ** (range 1h/6h) หรือ 1 นาที (range กว้าง) — ไม่ต้องรีเฟรชมือ (Fleet card poll ทุก 10 วิ)
- **KPI**: CPU / RAM / Disk / Uptime (สีเปลี่ยนตาม threshold: ≥80 เหลือง, ≥90 แดง)
- **Alert ล่าสุด**: แจ้ง alert ที่เพิ่งเกิดของ host นี้
- **Services**: badge แสดง service ทำงาน/หยุด (ถ้าตั้ง `--watch`)
- **Ports ที่เปิด/ปิด**: ตารางแสดง port เปิด/ปิด (ถ้าตั้ง `--ports`) — badge ● เปิด / ○ ปิด
- **กราฟ (Chart)**:
  - เลือก **metric** จาก chip (CPU%, RAM%, Load, Swap, Processes, Uptime...) — เลือกหลายตัวได้ (ต้องหน่วยเดียวกัน กันสเกลเพี้ยน)
  - เลือก **range**: 1h / 6h / 1d / 7d / 30d / 45d
  - y-axis ตั้งชื่อตามหน่วย, legend แสดงหลายเส้น
- **ตั้ง tags / export CSV**: ปุ่มด้านบนขวา

### 5.3 Alerts (แจ้งเตือน)

2 แท็บ: **กฎ** (rules) และ **ประวัติ** (history)

**สร้าง/แก้กฎ** (ปุ่ม "+ สร้างกฎ"):
| ช่อง | ความหมาย |
|------|----------|
| ชื่อ | ชื่อกฎ (เช่น "CPU สูง") |
| Host | host เฉพาะ / ว่าง = ทุก host (dropdown จาก host จริง) |
| Metric | ตัวชี้วัด (cpu_percent, memory.percent, disk.percent...) |
| Operator | `>` `>=` `<` `<=` `==` |
| Threshold | ค่าเกณฑ์ |
| Duration | ต้องเกินต่อเนื่องนานแค่ไหน (เช่น `5m`) |
| Notify | webhook / telegram (checkbox) |

- **กรองตาม host**: dropdown "ทุก host / <host>" ข้างปุ่มสร้าง
- **ประวัติ**: เวลา + host + metric + ค่า + ปุ่ม **ack** (รับทราบ; ack แล้วแถวจาง)

### 5.4 ตั้งค่า

- **ข้อมูล Server**: version / host:port / data_dir / log_dir / host_count / rate_limit / retention / rollup
- **Agent Token**: 
  - gen token: ใส่ `host_id` ที่ต้องการ → "สร้าง token" → คัดลอก (แสดงครั้งเดียว)
  - revoke: ปลด token (ต้องยืนยัน)
- **การแจ้งเตือน (Webhook / Telegram)** — ตั้งค่าช่องทางรับการแจ้งเตือน alert ผ่าน UI (บันทึกแล้วมีผลทันที ไม่ต้อง restart):
  - **Webhook**: กรอก URL → ปุ่ม **ทดสอบ** (POST ตัวอย่าง) → **บันทึก**
  - **Telegram**: กรอก **Bot Token** (จาก @BotFather) + **Chat ID** → ปุ่ม **ทดสอบส่งข้อความ** → **บันทึก**; มีตัวช่วย "วิธีหา Bot Token / Chat ID" (คลิกขยาย)
  - ติ๊ก **เปิดใช้งาน** เพื่อเปิดช่องทาง (ช่องใหม่ default เปิด); badge แสดงสถานะ: `พร้อมใช้งาน` / `ปิดใช้งาน` / `ยังไม่ได้ตั้งค่า`
  - ครั้งแรกที่ยังไม่ได้ตั้งค่าช่องใด → จะมี **วิซาร์ด** ชวนเลือกช่องทางแล้วพาไปกรอกค่าทีละขั้น
  - แล้วไปหน้า **Alerts → สร้างกฎ** เลือกช่องทางแจ้ง (webhook/telegram checkbox) ต่อกฎ — ช่องที่ยังไม่ได้ตั้งค่าจะมีข้อความ "(ยังไม่ได้ตั้งค่า)" กำกับ

### 5.5 เพิ่มเครื่องใหม่ (วิซาร์ด)

ปุ่ม **"+ เพิ่มเครื่องใหม่"** ใน toolbar Fleet — ตั้งค่า agent สำหรับเครื่องใหม่ แล้วคัดลอกคำสั่งไปรันบนเครื่องนั้น (ไม่ต้องมี Python; ไฟล์ config/data อยู่ข้าง exe):

| ฟิลด์ | คำอธิบาย / ใช้งานแบบไหน |
|-------|------------------------|
| `host_id` | ชื่อระบุเครื่องนี้ใน WebUI (ตัวตนของ host, token ผูกกับ id นี้) |
| `interval` (วินาที) | รอบที่ agent เก็บ + push metric — ถี่ = กราฟละเอียดขึ้น แต่โหลด server มากขึ้น (เช่น 15 = ทุก 15 วิ) |
| `watch` | service/process ที่เฝ้าว่า up/down — แสดง badge ในหน้า Host, คั่นด้วย `,` (ปล่อยว่างได้) |
| `ports` | TCP port ที่เฝ้าเปิด/ปิด — รูป `port:ชื่อ` (เช่น 80:web) แสดงตาราง Ports ในหน้า Host (ปล่อยว่างได้) |
| `max-batch` | จำนวน snapshot สูงสุดต่อ request — ตรงกับ server `ingest.max_batch_size` (100 มาตรฐาน) |

ขั้นตอน:
1. กรอกฟิลด์ตามต้องการ (มีคำอธิบายใต้ช่อง)
2. กด **"สร้าง token + พิมพ์คำสั่ง"** → สร้าง token อัตโนมัติจาก `host_id` + อัปเดตคำสั่ง
3. กด **"คัดลอกคำสั่ง"** → นำไปรันบนเครื่องเป้าหมาย (Windows: `monitor-agent.exe` · Linux: `./monitor-agent`)
4. รอสักครู่ → host ขึ้นใน Fleet (push แรกเข้ามา)

> 💡 ทางลัด: ถ้ายังไม่มี host กดปุ่ม **"ดูวิธีติดตั้ง agent"** ใน empty state (แสดง modal ที่ให้สร้าง token + คัดลอกคำสั่งได้เหมือนกัน)

---

## 6. Alerting (การแจ้งเตือน)

### 6.1 Rule (จาก config.toml)

```toml
[[alerting.rules]]
name = "CPU สูง"
host_id = ""                 # ว่าง = ทุก host
metric = "cpu_percent"
op = ">"
threshold = 90.0
duration = "5m"              # เกินต่อเนื่อง 5 นาที
notify = ["webhook", "telegram"]
```

### 6.2 Notifier

```toml
[alerting.notifiers.webhook]
url = "https://example.com/hook"     # POST JSON เมื่อ trigger

[alerting.notifiers.telegram]
bot_token = "..."
chat_id = "..."
```

- **host-down**: ถ้า host ไม่ส่งข้อมูลเกิน `offline_timeout_sec` จะแจ้ง (อัตโนมัติ)

### 6.3 ดู/ack

ใน WebUI → **Alerts → ประวัติ** → กด **ack** เพื่อรับทราบ.

---

## 7. Service (รันเป็นบริการ)

### 7.1 Windows (NSSM)

**Server exe**:
```powershell
monitor-server.exe --service install|start|stop|remove
```
- ต้องติดตั้ง **NSSM** ก่อน (https://nssm.cc) — อยู่ใน PATH

**Agent exe**:
```powershell
# ติดตั้งเป็น service (เขียน agent.cfg + NSSM)
monitor-agent.exe --install --server http://... --token <TOKEN> --interval 15
# ลบ
monitor-agent.exe --uninstall
```
> หรือใช้ `scripts\install-agent.ps1`

### 7.2 Linux (systemd)

```bash
# server
sudo bash scripts/install-server.sh
# agent
sudo bash scripts/install-agent.sh <server_url> <token> [interval]
```
> systemd unit อยู่ใน `scripts/systemd/` และ `agent/service/`.

---

## 8. Export / ข้อมูลย้อนหลัง

- **Export CSV**: ในหน้า Host → ปุ่ม "export CSV" (ตาม range ที่เลือก, เก็บข้อมูลตามช่วง)
- **ข้อมูลย้อนหลัง**: เลือก range **45d** เพื่อดูย้อนหลังถึง 45 วัน (ขึ้นกับ `retention_raw_days`)
- rollup: ช่วงกว้างจะอ่านจากตาราง rollup (1m/5m/1h/1d) อัตโนมัติ

---

## 9. การตั้งค่าขั้นสูง

| จุด | ทำอย่างไร |
|-----|-----------|
| เปิดให้เข้าจากนอก | config `[server] host = "0.0.0.0"` + เปิด firewall port |
| WebUI ใช้ HTTPS | config `[webui] secure_cookie = true` + ตั้ง reverse proxy TLS |
| เก็บข้อมูลนานขึ้น | config `[storage] retention_raw_days = 90` |
| เพิ่ม metric ที่เฝ้า | agent `--watch nginx,mysql` |
| เฝ้าดู port | agent `--ports 80:web,443:https` |
| rate limit ingest | config `[ingest] rate_limit_per_min` |

---

## 10. แก้ปัญหาทั่วไป

| อาการ | สาเหตุ/วิธีแก้ |
|-------|----------------|
| เข้า WebUI ไม่ได้ | server ไม่ได้รัน / ตรวจ `http://<host>:<port>` + logs |
| login ผิด | ตรวจ `admin_pass_hash` (bcrypt) — gen ใหม่: `python -m server.webui.auth --hash "..."` |
| agent push ไม่ทำงาน | ตรวจ `--server` และ `--token` ถูก (token จากหน้า ตั้งค่า) |
| agent ไม่สามารถ connect | server ต้อง `host="0.0.0.0"` + เปิด firewall port |
| host แสดงออฟไลน์ | ไม่มี push เกิน `offline_timeout_sec` — ตรวจ agent ยังรัน |
| host_id/queue อยู่ใต้ exe | agent exe เก็บ state ข้าง exe — อย่าลบไฟล์ `host_id`/`queue.json` |
| ไม่มี alert ตามที่ตั้ง | ตรวจ `duration` + metric name ต้องตรงรายการ (cpu_percent, memory.percent...) |
| ลง service ไม่ได้ (Windows) | ต้องติดตั้ง **NSSM** ก่อน อยู่ใน PATH |
| รันแล้วหน้า WebUI ไม่เปิด | ลองเปิดเอง `http://127.0.0.1:<port>/` หรือเพิ่ม `--no-browser` เพื่อลดข้อผิดพลาด |
| port ที่เฝ้าแสดงปิดผิด | agent ใช้ `127.0.0.1` — บริการที่ bind เฉพาะที่อยู่ (ไม่ใช่ localhost/all) จะไม่เห็น |

---

## เอกสารอ้างอิง

- `docs/CONFIG.md` — รายละเอียด config.toml + agent.cfg
- `docs/API.md` — REST API spec
- `docs/ARCHITECTURE.md` — สถาปัตยกรรม
- `docs/BUILD.md` — การ build exe
- `docs/DEPLOYMENT.md` — การ deploy
