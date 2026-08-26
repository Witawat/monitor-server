# Changelog

ทุกการเปลี่ยนแปลงสำคัญจะถูกบันทึกไว้ในไฟล์นี้

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) และใช้ [Semantic Versioning](https://semver.org/).

## [Unreleased]

### เพิ่ม
- WebUI เป็นหน้าเดียวเลื่อนยาว (long page) — ไม่มี sidebar, เมนูนำทาง (Fleet/Alerts/ตั้งค่า) เป็น topnav แนวนอนใน topbar, คลิกการ์ด → เลือก host + scroll ไป section Host
- **ปุ่ม "แก้ไขค่า Host"**: modal แก้ hostname/tags + remote config (interval/watch/ports/max_batch) ที่ agent จะ pull ไปใช้ในรอบถัดไป (ไม่ต้อง restart) + ลบ host แบบ confirm
- **Remote config (agent)**: server เก็บ desired_config ต่อ host (DB) + คืนให้ agent ผ่าน ingest response → agent เปลี่ยน interval/watch/ports/max_batch แบบ live โดยไม่ restart (ตามที่ตั้งใน WebUI)
- input/select/textarea/checkbox เป็นกล่องสไตล์เดียวกันทั้งหมด (rule กลางใน app.css)
- Fleet: OS icon (linux/windows/mac จาก `platform`) + แถบสถิติ (จำนวน/ออนไลน์/ออฟไลน์/Linux/Windows) เมื่อมีหลาย server
- กราฟย้อนหลังสูงสุด 45 วัน: `retention_raw_days` default 45 + range 30d/45d ใน API/chart/export
- **Host realtime auto-refresh**: section Host poll `/api/v1/hosts/{id}` + `/metrics` ทุก 5s (range 1h/6h) หรือ 1 นาที (range กว้าง) — KPI/services/ports/chart อัปเดตเอง (Fleet card poll 10s อยู่แล้ว)
- **วิซาร์ด "+ เพิ่มเครื่องใหม่"**: ปุ่มใน Fleet toolbar → modal ระบุค่า agent (host_id/interval/watch/ports/max-batch พร้อมคำอธิบาย) → สร้าง token + พิมพ์คำสั่ง `--install` ให้คัดลอก (ไม่พึ่งไฟล์ .md); empty state มี "ดูวิธีติดตั้ง agent" (modal) เปิด `/docs/*.md` ที่ 404 → แสดงข้อมูลจากเว็บแทน
- **CI + Release automation**: `.github/workflows/ci.yml` (ruff+mypy+pytest บน py3.11/3.12) + `release.yml` (push tag `v*` → build exe + publish release ต่อไฟล์)
- **README badges** (CI/Release/Python/version/license) + `--no-browser` เปิด WebUI อัตโนมัติแบบไม่บังคับ

### แก้
- hostname ค้างว่าง: ingest ใช้ hostname/platform จาก snapshot ถ้า host ถูกสร้างด้วย token ก่อน first push
- chart: เลือก metric ทีละตัว (chip) + y-axis ตาม unit + format ผ่าน format.js (เดิม plot ทุก metric สีเดียว/ปิด legend อ่านไม่ออก)
- KPI disk fallback, net arrow (↑=tx/send, ↓=rx/receive), favicon, version แสดงจาก `__version__` จริง
- **login**: textbox เต็มความกว้าง (`.field input width:100%`) + login เลื่อนหน้าตรง dashboard (เดิมค้างที่ login)
- **server exe ไม่ต้องสั่ง `--config`**: default ว่าง → อ่าน `config.toml` ข้าง exe (frozen) / รากโปรเจกต์ (dev) อัตโนมัติ
- เครดิตผู้พัฒนา + version + URL GitHub แสดงบนหน้า login + footer หน้าหลัก

### แก้ (bug audit รอบ 2 + จุดเสี่ยง)
- `port_samples` ไม่ถูกเก็บกวาด/ลบใน `retention_cleanup()` + `delete_host()` → เพิ่มลบตารางนี้ (กัน DB โต/orphan)
- token ว่าง (`X-Agent-Token: ""`) ยึด identity ของ host ที่ถูก revoke → ตอนนี้ 401 กัน auto-register
- agent วนลูป crash เมื่อ `collect.snapshot()` ยกเว้น → `try/except` + แยก retryable (offline/5xx/429 → queue+backoff), 4xx (ทิ้ง batch), 401/403 (exit)
- alerting: engine ส่ง notify ตาม `rule["notify"]` เฉพาะ + prune state ค้างเมื่อลบ rule/host
- agent `--max-batch` ใช้ batch size จาก config (เดิม `MAX_BATCH_SIZE` คงที่ 100)
- rollup off-by-one `ts > start_ts` ตก 1 จุดตรงจุดตัด bucket → เริ่มที่ `last`
- rate limit รองรับ reverse proxy: `client_ip()` อ่าน `X-Forwarded-For`
- mypy cross-platform: ใช้ `--disable-error-code=unused-ignore` (ctypes.windll/os.statvfs ฟ้องคนละที่ตาม platform)

## [0.2.0] - 2026-08-26

### เพิ่ม (เฟส 0–5 + งานเสริม + เฟส 6)
- Server core: ingest + storage (SQLite/WAL) + API hosts/metrics/alerts/auth + login (bcrypt + HttpOnly cookie)
- Agent: collect (stdlib, psutil optional) + push + retry/backoff + offline queue
- WebUI: Jinja2 SPA + Chart.js local + format.js/zoom/responsive 360/768/1280
- Alerting: engine ตรวจ rule หลัง ingest + webhook/Telegram + history/ack + host-down notify
- งานเสริม: host tags/filter, service watch (--watch), export CSV, rate-limit login, CSP/security headers
- Build EXE: PyInstaller onefile (`scripts/build.ps1`) + icon monitor+pulse (`scripts/make_icon.py`) + UPX ล่าสุด
- Rollup tables (1m/5m/1h/1d) + background RollupWorker/RetentionWorker

### แก้ (bug audit)
- login พังเพราะ CSP → ย้าย inline script ไป `login.js`
- auto-register แย่งชิง token host เดิม → host มีอยู่แล้ว = 400
- stored XSS → `escapeHtml()` ทุก field จาก API
- delete_host/retention ลบ service/history, offline monitor ข้าม host ไร้ข้อมูล + persist fired
- /api/status ต้อง auth, session secret คงที่ (state.json), chart x-axis แสดงเวลา, net/disk แสดงถูก
- agent chunk flush (กัน queue ติดตาย), หยุด retry เมื่อ 401, disk % ใช้ bavail, cookie Secure flag

