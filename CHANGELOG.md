# Changelog

ทุกการเปลี่ยนแปลงสำคัญจะถูกบันทึกไว้ในไฟล์นี้

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) และใช้ [Semantic Versioning](https://semver.org/).

## [Unreleased]

### เพิ่ม
- โครงโปรเจกต์ + เอกสารออกแบบครบชุด (AGENTS.md, README, PRODUCT, KNOWLEDGE_BASE, docs/ ทั้งหมด, .gitignore)
- วางแผนสถาปัตยกรรม: server (FastAPI + SQLite) + agent (stdlib push model) + shared schema
- ยังไม่มีโค้ด functional — ช่วงวางแผน/ออกแบบ

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

