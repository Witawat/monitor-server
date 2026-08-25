# CONTRIBUTING.md

ขอบคุณที่สนใจ contribute! กฎสำคัญสำหรับการทำงานในโปรเจกต์นี้

## ก่อนเริ่ม
- อ่าน `AGENTS.md` (กฎ + stack) และ `KNOWLEDGE_BASE.md` (ความรู้) ก่อนเขียนโค้ด
- ยึดสไตล์โค้ด/docstring ใน `docs/CODING_GUIDE.md` (ภาษาไทย, PEP 8/257)

## กฎเหล็ก
- **ห้ามใช้ npm/node/React** บน WebUI — ล็อกเป็น Jinja2 + vanilla JS + Chart.js local
- **agent ต้อง stdlib เท่านั้น** (psutil optional) — ห้าม dependency หนัก, ห้าม import server/
- **ห้าม commit**: `data/*.db`, `logs/`, `config.toml`, `.env`, `*.pem`, `*.key`
- path ใช้ `pathlib`/`os.path` — ห้าม hardcode `/`

## ขั้นตอน
1. fork + branch (`feat/...`, `fix/...`)
2. เขียนโค้ดตาม `CODING_GUIDE.md` (docstring ครบ public + inline comment แบบ why)
3. เขียน/แก้ test — เทส server ด้วย mock, เทส agent ด้วย fake HTTP (ห้ามยิง server จริง)
4. รันผ่านให้ครบก่อน PR:
   ```powershell
   ruff check .
   mypy server agent shared
   pytest -q
   ```
5. อัปเดต `CHANGELOG.md` (ย้ายไป section ของเวอร์ชัน)
6. PR พร้อมคำอธิบายสั้นๆ ว่าทำอะไร + ผลตรวจผ่าน

## ทดสอบ
- ดู `docs/DEVELOPMENT.md` — ล้าง `data/`+`logs/`, kill process ค้างก่อนเทส

## Release
- รอผู้ดูแลจัดการ version bump + tag (SemVer) — ดู `AGENTS.md`
