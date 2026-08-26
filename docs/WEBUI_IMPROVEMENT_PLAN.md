# แผนปรับปรุง Web UI — Monitor Server

> เอกสารวางแผนการปรับปรุง Web UI ให้ใช้งานง่าย / ดูง่าย (readable & usable)
> อ้างอิง: `WEBUI_DESIGN.md` (ดีไซน์), `API.md` (endpoint), `AGENTS.md` (กฎสแต็ก — vanilla JS + Chart.js local, ห้าม npm/node/React)
> สถานะ: เอกสารแผน (ยังไม่ได้ลงมือทำ) — ทำรายข้อแล้วเปลี่ยน `[ ]` → `[x]` พร้อมระบุ commit

---

## หลักการจัดลำดับ (Priority)
เรียงตาม "ความคุ้มค่า / ผลกระทบต่อคนใช้":
- **P0** — ผลกระทบสูง ใช้งานไม่ได้/เข้าใจยากที่สุด ทำก่อน
- **P1** — ทำให้ "เข้าใจไว" ดีขึ้นมาก
- **P2** — เสริมความสมบูรณ์ / สวยงาม / สะดวก

ทุกข้อต้องผ่านเกณฑ์ตรวจ (ดูหัวข้อ "เกณฑ์ตรวจ") ก่อนถือว่าเสร็จ

---

## P0 — ข้อ 1: กราฟดูได้มากกว่า 1 metric ในเวลาเดียว

### ปัญหาที่เจอ
- ตอนนี้ chart เลือกได้ **1 metric** (`currentMetric` ตัวเดียว) ผ่าน chip selector
- ผู้ใช้อยากเห็น "CPU พุ่งแล้ว RAM ตาม" พร้อมกัน **ต้องสลับ chip ไปมา 11 ตัว** — ไม่สะดวกและเข้าใจแนวโน้มช้า

### เป้าหมาย
- เลือก**หลาย metric** วาดในกราฟเดียวได้
- metric ที่หน่วยเดียวกัน (เช่น `%`) วาดร่วมกันได้; หน่วยต่างกัน (`%` vs `bytes` vs `num`/`sec`) **ต้องไม่ยัดรวมกัน** กันสเกลเพี้ยน

### แนวทางแก้ไข
1. **เปลี่ยน chip selector จาก "เลือกเอนเดียว" เป็น "toggle หลายตัว"** (คลิกได้หลาย chip; อย่างน้อย 1 ตัวต้อง active)
2. **จัดกลุ่มตามหน่วย**:
   - `%` : `cpu_percent`, `memory.percent`
   - `bytes` : `memory.used`, `memory.total`, `swap.used`, `swap.total`
   - `num` : `load1`, `load5`, `load15`, `procs`
   - `sec` : `uptime`
3. การวาด:
   - metric ที่เลือก**ทุกตัวต้องมีหน่วยเดียวกัน** ถึงจะวาดรวม (ยืนยันก่อน render — ถ้าหน่วยไม่ตรง ให้ toast เตือน + auto เลือกเฉพาะหน่วยแรก)
   - แต่ละ series ใช้**สีต่างกัน** (palette) + **เปิด legend** (แสดง label + หน่วย)
   - y-axis ตั้งชื่อตามหน่วย (เช่น `%` / `bytes` / `count`)
   - tooltip format ผ่าน `format.js` ตามหน่วยของแต่ละ series
4. **ค่า default**: เปิด `cpu_percent` + `memory.percent` (หน่วย % กัน อ่านง่ายสุด)
5. API: ใช้ query `?metrics=cpu_percent,memory.percent` (รองรับอยู่แล้วใน `server/api/metrics.py`)

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/static/js/dashboard.js` — `renderChart()`, `renderMetricChips()`, ตัวแปร `currentMetric`
- `server/webui/templates/parts/host.html` — โครงสร้าง `#metricChips`
- `server/webui/static/css/app.css` — สี legend / chip state (active)
- `docs/WEBUI_DESIGN.md` §7 (chart spec) — อัปเดตให้ตรง

### เกณฑ์เสร็จ
- [ ] เลือก 2+ metric หน่วยเดียวกัน → กราฟแสดงหลายเส้น + legend + สีต่างกัน
- [ ] เลือกหน่วยต่างกัน → ไม่พัง, เตือน + ตกไปหน่วยเดียว
- [ ] tooltip แสดงค่า+หน่วยถูกของแต่ละ series
- [ ] y-axis ตั้งชื่อตามหน่วย

---

## P1 — ข้อ 2: หน้า Host แสดง alert ที่เพิ่งเกิดขึ้น

### ปัญหาที่เจอ
- หน้า Host (dashboard รายเครื่อง) มี KPI + chart + services แต่**ไม่เห็นว่า host นี้เคย alert อะไร**
- เข้าไปดู web-01 แล้วไม่รู้ว่า CPU เพิ่งเกิน 90 → ขาดบริบท

### เป้าหมาย
- ที่ด้านบนของหน้า Host แสดง**รายการ alert ที่เพิ่งเกิดขึ้นของ host นี้** (เวลา + metric + ค่า + สถานะ ack) สั้นๆ
- ถ้าไม่มีการ alert → แสดงข้อความ "ไม่มี alert ล่าสุด" (หรือซ่อนหัวข้อ ขึ้นอยู่กับดีไซน์)

### แนวทางแก้ไข
1. API: ใช้ `/api/v1/alerts/history?host_id=<id>` (รองรับแล้ว)
2. เพิ่ม section ใน `host.html` (เหนือ KPI หรือใต้ toolbar)
3. แสดงเฉพาะ last N (เช่น 5) รายการ, เรียงเวลาใหม่ล่าสุด
4. กล่อง alert: host metrics ที่มี alert → ใช้สี `--danger` (แดง) / `--warn` (เหลือง); ack แล้ว → จางลง
5. ตัวเลือก: นำ `renderKpi` / `renderServices` มาใช้ซ้ำ pattern เดิม

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/templates/parts/host.html`
- `server/webui/static/js/dashboard.js` — `renderHostAlertHistory()`
- `server/webui/static/css/app.css`
- `docs/WEBUI_DESIGN.md` §5.3 (Host wireframe) — เพิ่มแถบ alert

### เกณฑ์เสร็จ
- [ ] แสดง alert ล่าสุดของ host ที่เลือก (เวลา + metric + ค่า + ack)
- [ ] ไม่มี alert → ข้อความ/หัวข้อจัดการถูก
- [ ] เปลี่ยน host (dropdown/card) → อัปเดต alert ตาม

---

## P1 — ข้อ 3: การ์ด Fleet มี mini sparkline (กราฟเล็ก)

### ปัญหาที่เจอ
- การ์ด Fleet แสดงค่า % ปัจจุบัน (CPU/RAM/Disk) + net + uptime
- **ไม่รู้แนวโน้ม** — ค่า 50% จะ "กำลังขึ้นหรือลง" เห็นไม่ได้

### เป้าหมาย
- การ์ดแต่ละใบมี**กราฟเล็ก (sparkline)** ของ CPU (หรือ metric หลักที่เลือก) เห็นแนวโน้มปราดเดียว
- ใช้ Chart.js (bundle local มีแล้ว) ทำ mini chart opacity เบาๆ ไม่เกะกะ

### แนวทางแก้ไข
1. Fleet data จาก `/api/v1/hosts` มี `summary` เท่านั้น (ค่าเดียว) — ต้องดึง trend:
   - **ตัวเลือก A (แนะนำ)**: เพิ่ม API หรือ reuse `/api/v1/hosts/{id}/metrics?range=1h&metrics=cpu_percent` ต่อ host
   - **ตัวเลือก B (เบากว่า)**: ถ้าอยากลด request — เพิ่ม field `summary.trend` (points สั้นๆ) ใน endpoint `/api/v1/hosts` (server ฝั่ง)
2. วาด sparkline ใน `renderFleetCards()` — ใช้ `<canvas>` ต่อการ์ด + `new Chart(..., {animation:false, pointRadius:0, ...})`
3. ระวัง: การ์ดหลายใบ → สร้าง chart เยอะ ต้อง `destroy` เก่าเมื่อ re-render (poll ทุก 10s) กัน leak
4. ใช้สีตาม threshold (≥80 เหลือง, ≥90 แดง) ให้เห็น "วิกฤต" เร็ว

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/static/js/dashboard.js` — `renderFleetCards()` เพิ่ม sparkline
- `server/api/hosts.py` / `server/storage/db.py` (ถ้าใช้ทางเลือก B)
- `server/webui/static/css/app.css` — ขนาด sparkline
- `docs/API.md` / `WEBUI_DESIGN.md` §5.2 (Fleet wireframe)

### เกณฑ์เสร็จ
- [ ] การ์ดมี sparkline trend ของ metric หลัก
- [ ] re-render (poll) ไม่ leak chart (destroy เก่า)
- [ ] ไม่กระทบ performance ห หลายสิบการ์ด (หรือ virtualize/pagination ตาม §9)

---

## P2 — ข้อ 4: ตาราง Alerts ดูเป็นมิตร + กรอง host

### ปัญหาที่เจอ
- ตารางกฎ alert โชว์ `db-02` / `ทุก host` ในคอลัมน์ Host — ดูแล้วไม่รู้ว่า "คือเครื่องอะไร"
- ไม่มีวิธีกรอง/เรียงตาม host

### เป้าหมาย
- แสดงชื่อ host ที่อ่านรู้เรื่อง (hostname หรือ host_id) + มี dropdown กรอง host ในตาราง

### แนวทางแก้ไข
1. ใน `loadAlerts()` มี `hosts` อยู่แล้ว — นำมาสร้าง dropdown กรอง (ทั้งหมด / db-02 / web-01) เหนือตาราง
2. คอลัมน์ Host: ถ้า `host_id` ว่าง → "ทุก host"; ถ้ามี → แสดง `hostname (host_id)` ให้อ่านง่าย
3. เรียง/กรองกฎตาม host ที่เลือก

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/templates/parts/alerts.html`
- `server/webui/static/js/alerts.js` — `loadAlerts()` / `render()`
- `server/webui/static/css/app.css`
- `docs/WEBUI_DESIGN.md` §5.4 (Alerts wireframe)

### เกณฑ์เสร็จ
- [ ] มีกรอง host ในตารางกฎ
- [ ] คอลัมน์ Host อ่านง่าย (hostname + host_id)

---

## P2 — ข้อ 5: หน้า ตั้งค่า ครอบคลุมกว่า

### ปัญหาที่เจอ
- หน้า ตั้งค่า มีแค่ **Agent Token** (gen/revoke)
- ไม่มีข้อมูล/server config/การตั้ง alert notifier

### เป้าหมาย
- ทำให้ "ตั้งค่า" เป็นศูนย์รวม: token + ข้อมูล server (version/retention/rollup/เส้นทาง) + ตั้ง webhook/telegram ของ alert

### แนวทางแก้ไข
1. **Agent Token**: คงเดิม + เพิ่ม host_id ใหม่ auto-fill (optional)
2. **ข้อมูล server (read-only)**: แสดง `version`, `host:port`, `data_dir`, `log_dir`, `retention_raw_days`, `rollup_intervals` — จาก `/api/status` (รองรับแล้ว)
3. **ตั้งค่า alert notifier** (webhook url / telegram bot_token + chat_id):
   - UI แบบฟอร์ม → บันทึกเขียนกลับ config.toml + reload config (อยู่บน server `maintenance`/`config` ฝั่ง)
   - เป็นงานใหญ่ (ต้องเขียน config กลับ) → แยก sub-task / งดทำถ้าเกินขอบเขต

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/templates/parts/settings.html`
- `server/webui/static/js/alerts.js` — `loadSettings()`
- `server/api/` (ถ้าเพิ่ม endpoint บันทึก config) + `server/config.py`
- `docs/WEBUI_DESIGN.md` §5.5

### เกณฑ์เสร็จ
- [ ] แสดงข้อมูล server/config (version, retention, rollup, data_dir) แบบ read-only
- [ ] (ถ้าทำ) ตั้ง webhook/telegram ผ่าน UI แล้ว config อัปเดตจริง

---

## P2 — ข้อ 6: หน้าว่าง / กำลังโหลด สวยขึ้น + ปุ่มแนะนำ

### ปัญหาที่เจอ
- host ไม่มีข้อมูล → chart + KPI แสดง "ไม่มีข้อมูล" เป็นข้อความล้วน (ตาม §10 ของ WEBUI_DESIGN มีระบุ "illustration + ปุ่มดูวิธี" แต่ยังไม่ทำ)

### เป้าหมาย
- Empty state / loading มี icon + ข้อความชัด + ปุ่ม/ลิงก์ "วิธีติดตั้ง agent"

### แนวทางแก้ไข
1. Empty Fleet (ไม่มี host): icon + "ยังไม่มี host — ติดตั้ง agent" + ปุ่ม "ดูวิธีติดตั้ง" (ลิงก์ไป docs หรือ modal วิธี)
2. Host ยังไม่มี data: KPI `—` + chart "ไม่มีข้อมูล — รอ push แรก" + ปุ่ม refresh
3. Loading: skeleton (ไม่ใช่ spinner ทั้งหน้า) — เพิ่ม `.skeleton` ใน CSS

### ไฟล์ที่เกี่ยวข้อง
- `server/webui/static/js/app.js` / `dashboard.js`
- `server/webui/static/css/app.css`
- `server/webui/templates/parts/fleet.html` / `host.html`
- `docs/WEBUI_DESIGN.md` §10

### เกณฑ์เสร็จ
- [ ] Empty Fleet มี icon + ปุ่มวิธีติดตั้ง
- [ ] Host ไม่มี data → KPI `—` + chart message + refresh
- [ ] loading skeleton

---

## P2 — ข้อ 7: รายละเอียดเล็กๆ ที่ทำให้ใช้สะดวกขึ้น

### รายการ
| # | รายการ | ไฟล์ |
|---|--------|------|
| 7.1 | แสดงสถานะการกรอง (เช่น "กรอง: ออนไลน์ · #prod") ว่า Fleet กำลังโชว์อะไร | `app.js` |
| 7.2 | `<title>` ตาม section ที่ scroll ถึง (เช่น "Fleet — Monitor") | `app.js` |
| 7.3 | ปุ่ม "refresh" มุมบน Fleet (manual) | `fleet.html` / `app.js` |
| 7.4 | ตัวเลข KPI ใช้สีตาม threshold (CPU ≥80 เหลือง / ≥90 แดง) | `dashboard.js` |
| 7.5 | badge "ออนไลน์/ออฟไลน์" ใส่ `aria-label` ชัด (accessibility) | `dashboard.js` |
| 7.6 | chart range default เก็บใน localStorage (จำที่ผู้ใช้เลือกไว้) | `dashboard.js` |
| 7.7 | fleet card แสดง `swap` หรือ "services หยุด" เตือนเล็กๆ (เช่น redis down) | `dashboard.js` |

### เกณฑ์เสร็จ
- [ ] ทำรายการที่เลือกได้ครบ (เลือกทำได้ตามต้องการ ระบุใน commit)

---

## P1 — ข้อ 8: Fleet — OS icon + สถิติเมื่อมีหลาย server

### ปัญหาที่เจอ
- เมื่อติดตามหลาย server การ์ด Fleet รู้แค่สถานะ/ค่า แต่**ดูไม่ได้ว่าอันไหน Linux/Windows** (host ต้องเดาจากชื่อ — แบบ win-01 ค่อยเดาได้ แต่ fs-02/db-03 ไม่ชัด)
- ไม่มีภาพรวมว่ามีกี่เครื่อง/ออนไลน์/ออฟไลน์/แบ่ง OS ยังไง ต้องมานับเอง

### เป้าหมาย
- การ์ดแต่ละใบมี **icon OS** ที่มุมชื่อ host → รู้ OS ปราดเดียว
- Fleet ด้านบนมี**แถบสถิติ** (จำนวน/ออนไลน์/ออฟไลน์/แบ่ง OS) → ภาพรวมชัด

### แนวทางแก้ไข (ทำไปแล้ว — 2026-08-26)
1. **OS icon** ใน `renderFleetCards()`: ใช้ field `platform` (`linux`/`windows`) ที่ API `/api/v1/hosts` คืนอยู่แล้ว → `osIcon(platform)` คืน SVG (linux=🐧 สีเขียว, windows=🪟 สีฟ้า, darwin=mac) กัน emoji render ต่างกัน
2. **แถบสถิติ** `renderFleetStats()`: แสดง `N เครื่อง · X ออนไลน์ · Y ออฟไลน์ · L Linux · W Windows` (ใช้ข้อมูล **ทั้งหมด** ไม่ใช่ filtered — คงเดิมตอนกด filter)
3. โครงสร้าง: `.os-icon` + `.host-name` อยู่หน้า hostname; `.fleet-stats` อยู่ใต้ toolbar ของ Fleet
4. พฤติกรรมหลาย server: คง card grid `auto-fill minmax(240px)` — หลายเครื่องจัดเรียงอัตโนมัติ; ถ้าเกินหลักสิบ/ร้อย ค่อยพิจารณา virtualize/pagination ตาม §9

### ไฟล์ที่แก้
- `server/webui/static/js/dashboard.js` — `osIcon()`, `renderFleetStats()`, ปรับ h3 card
- `server/webui/static/js/app.js` — `renderFleetView()` เรียก `Dashboard.renderFleetStats(fleetData)`
- `server/webui/templates/parts/fleet.html` — เพิ่ม `<div id="fleetStats">`
- `server/webui/static/css/app.css` — `.fleet-stats` / `.fleet-stat` / `.os-icon` / `.host-name`

### เกณฑ์เสร็จ (ยืนยันแล้ว)
- [x] การ์ดมี OS icon (linux/windows/mac)
- [x] แถบสถิติ จำนวน/ออนไลน์/ออฟไลน์/Linux/Windows
- [x] responsive 360/768/1280 ไม่ overflow
- [x] console 0 error (เล่น Playwright จริง)

---

## สรุป Roadmap

| ลำดับ | ข้อ | ระดับ | ความคุ้มค่า |
|------|----|------|------------|
| 1 | หลาย metric ในกราฟเดียว | P0 | สูงมาก — เข้าใจแนวโน้มรวม |
| 2 | Host แสดง alert ล่าสุด | P1 | สูง — เห็นบริบทปัญหา |
| 3 | Fleet card sparkline | P1 | สูง — ดูแนวโน้มเร็ว |
| 4 | ตาราง Alerts กรอง host | P2 | กลาง |
| 5 | หน้า ตั้งค่า ครบ | P2 | กลาง-สูง (เหมือนตั้งค่าจริง) |
| 6 | empty/loading สวย | P2 | กลาง-ต่ำ |
| 7 | รายละเอียดเล็กๆ | P2 | กลาง (ทำที่คุ้มก่อน) |
| 8 | Fleet: OS icon + สถิติหลาย server | P1 | สูง — ดู OS/จำนวนได้ปราดเดียว |

---

## เกณฑ์ตรวจก่อนถือว่าเสร็จ (ใช้ทุกข้อ)

- [ ] `ruff check .` + `mypy server agent shared` ผ่าน
- [ ] `pytest -q` ผ่าน
- [ ] (ถ้าเปลี่ยน JS/CSS/template) verify ด้วย Playwright: ไปทุกหน้า, ไม่ overflow 360/768/1280, **console 0 error**
- [ ] (ถ้าเปลี่ยน server API) rebuild exe + `scripts\test_exe.ps1` 13 checks ผ่าน
- [ ] อัปเดต `docs/WEBUI_DESIGN.md` (+ `API.md` ถ้า API เปลี่ยน)

---

## การยืนยัน / วิธีทดสอบด้วยมือ (Playwright)

1. เปิด `/` (login) → เข้าสู่ระบบ → ไปแต่ละ section
2. Fleet: กรองออนไลน์/ออฟไลน์/แท็ก, ค้นหา host, คลิกการ์ด → เลื่อนไป Host
3. Host: เปลี่ยน host จาก dropdown, เลือก metric (1+ ตัว), สลับ range 1h→45d
4. Alerts: เปิด/ปิดฟอร์ม + สร้าง/แก้ไข/ลบกฎ; Tab ประวัติ + ack; (ถ้ามี) กรอง host
5. ตั้งค่า: gen/revoke token; (ถ้ามี) อ่านข้อมูล server
6. ยืนยัน: ไม่มี console error, ทุกหน้า responsive ไม่ overflow แนวนอน

---

## สถานะการทำ

| ข้อ | สถานะ | Commit |
|----|-------|--------|
| 1 | [ ] ยังไม่ทำ | — |
| 2 | [ ] ยังไม่ทำ | — |
| 3 | [ ] ยังไม่ทำ | — |
| 4 | [ ] ยังไม่ทำ | — |
| 5 | [ ] ยังไม่ทำ | — |
| 6 | [ ] ยังไม่ทำ | — |
| 7 | [ ] ยังไม่ทำ | — |
| 8 | [x] ทำแล้ว — OS icon + สถิติหลาย server | (ดู git log — commit ล่าสุด) |
