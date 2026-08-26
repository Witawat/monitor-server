# Changelog

ทุกการเปลี่ยนแปลงสำคัญจะถูกบันทึกไว้ในไฟล์นี้

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) และใช้ [Semantic Versioning](https://semver.org/).

## [Unreleased]

### เพิ่ม
- WebUI เป็นหน้าเดียวเลื่อนยาว (long page) — ไม่มี sidebar, เมนูนำทาง (Fleet/Alerts/ตั้งค่า) เป็น topnav แนวนอนใน topbar, คลิกการ์ด → เลือก host + scroll ไป section Host
- input/select/textarea/checkbox เป็นกล่องสไตล์เดียวกันทั้งหมด (rule กลางใน app.css)
- Fleet: OS icon (linux/windows/mac จาก `platform`) + แถบสถิติ (จำนวน/ออนไลน์/ออฟไลน์/Linux/Windows) เมื่อมีหลาย server
- กราฟย้อนหลังสูงสุด 45 วัน: `retention_raw_days` default 45 + range 30d/45d ใน API/chart/export

### แก้
- hostname ค้างว่าง: ingest ใช้ hostname/platform จาก snapshot ถ้า host ถูกสร้างด้วย token ก่อน first push
- chart: เลือก metric ทีละตัว (chip) + y-axis ตาม unit + format ผ่าน format.js (เดิม plot ทุก metric สีเดียว/ปิด legend อ่านไม่ออก)
- KPI disk fallback, net arrow (↑=tx/send, ↓=rx/receive), favicon, version แสดงจาก `__version__` จริง

## [0.2.0] - 2026-08-26

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

