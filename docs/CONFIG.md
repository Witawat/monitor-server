# CONFIG.md — server config.toml

## ตำแหน่ง
- dev: `./config.toml` (รากโปรเจกต์) — gitignore แล้ว, ใช้ `config.example.toml` เป็นต้นแบบ
- service: ข้าง `run.py` / ไดเรกทอรี install

> ใช้ **TOML** — อ่านง่าย (แบบ pyproject), รองรับ comment, Python 3.11 อ่านด้วย stdlib `tomllib` (ไม่ต้องลง dep แยก). Server validate ด้วย pydantic หลัง parse.

## ตัวอย่างเต็ม (server)

```toml
[server]
host = "127.0.0.1"       # 0.0.0.0 ถ้าให้ agent/คนเข้าจากนอก
port = 18080
data_dir = "data"        # เก็บ monitor.db
log_dir = "logs"

[webui]
admin_user = "admin"
admin_pass_hash = "$2b$12$..."   # bcrypt (gen: python -m server.webui.auth --hash "...")
secret_key = "สุ่มยาวๆ"          # เซ็น cookie
setup_done = false

[ingest]
rate_limit_per_min = 1200      # กัน flood ต่อ IP
max_batch_size = 100           # snapshot สูงสุดต่อ request
offline_timeout_sec = 60       # ถ้าไม่มี push เกินนี้ → host ถือว่า offline

[storage]
retention_raw_days = 45        # เก็บ raw/กราฟย้อนหลังได้นานแค่ไหน (default 45 วัน)
rollup_intervals = ["1m", "5m", "1h", "1d"]   # บีบ raw ไปตาราง rollup
wal = true

[alerting]
enabled = true

[alerting.notifiers.webhook]
url = ""                       # POST JSON เมื่อ trigger

[alerting.notifiers.telegram]
bot_token = ""
chat_id = ""

[[alerting.rules]]             # array of table — แต่ละ rule 1 บล็อก
name = "CPU สูง"
host_id = ""                   # ว่าง = ทุก host
metric = "cpu_percent"
op = ">"
threshold = 90.0
duration = "5m"                # ต้องเกินต่อเนื่องนานแค่ไหน
notify = ["webhook", "telegram"]

[auth]
allow_registration = true      # agent ใหม่ push ครั้งแรก auto-register
```

> หมายเหตุ TOML: ใช้ `[[alerting.rules]]` สำหรับ **array ของ rule** (ซ้ำบล็อกได้), และ `[alerting.notifiers.xxx]` สำหรับ nested table.

## กฎ validate (pydantic)
- `server.port` ต้องเป็น int 1–65535
- `admin_pass_hash` ต้องเป็น bcrypt — ถ้าใส่ plain ให้ fail ชัดเจน
- `alerting.rules[].op` ∈ `>`, `>=`, `<`, `<=`, `==`
- `rollup_intervals` ต้องเรียงจากละเอียดไปหยาบ
- rate limit / retention ต้องเป็น int ≥ 0

## Agent config (arg/env — ไม่ใช่ไฟล์)
```powershell
python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15
# env: MONITOR_SERVER_URL / MONITOR_TOKEN / MONITOR_INTERVAL
```

## การ gen bcrypt hash
```powershell
python -m server.webui.auth --hash "รหัสผ่านใหม่"
# หรือ
python -c "import bcrypt; print(bcrypt.hashpw(b'รหัสผ่าน', bcrypt.gensalt()).decode())"
```
