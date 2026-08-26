# WEBUI_DESIGN.md — ดีไซน์ Web UI (SPA)

> source of truth สำหรับหน้าตา WebUI. ล็อก: **Jinja2 + vanilla JS + Chart.js (bundle local)** — **ห้าม npm/node/React** (ดู `AGENTS.md`).
> สเปกนี้กำหนด **หน้าตา/เลย์เอาต์/พฤติกรรม/การ format** จริง — ไม่ใช่แค่โครง.

---

## 1. สแต็ก
- Server-render shell: `server/webui/templates/base.html` (single-page)
- ส่วนประกอบ: `templates/parts/*.html` — ใช้ `{% include %}`
- JS: `static/js/app.js` + `dashboard.js` + `alerts.js` + `scale.js` + `format.js` + `i18n.js` (vanilla, long page scroll + UI scale)
- Chart: `static/js/chart.umd.min.js` (**local bundle** — ไม่ใช้ CDN)
- API: `/api/v1/*` (ดู `API.md`)
- CSS: `static/css/tokens.css` (variables) + `app.css`

---

## 2. App Shell (โครงรวมทุกหน้า)

> **หน้าเดียวเลื่อนยาว (long page)** — ทุก section แสดงพร้อมกันเลื่อนแนวตั้ง **ไม่มี sidebar**; เมนูนำทาง (Fleet/Alerts/ตั้งค่า) เป็น `.topnav` แนวนอนใน topbar, คลิก → scroll ไป section; การ์ด host คลิก → เลือก host + scroll ไป section Host; Host มี dropdown เลือก host (default = host แรก หรือจาก hash `#/host/<id>`).

```
┌──────────────────────────────────────────────────────────┐
│  ● Monitor   🔍 ค้นหา host…  Fleet Alerts ตั้งค่า  [👤 admin ▼]  │  ← topbar (56px) + topnav
├──────────────────────────────────────────────────────────┤
│  Fleet (การ์ด host + สถิติ: จำนวน/ออนไลน์/OS)              │  ← scroll ลงต่อเนื่อง
│  Host (dropdown + KPI + chart)                           │
│  Alerts (กฎ + ประวัติ + ฟอร์ม)                            │
│   ตั้งค่า (Agent Token)                                   │
├──────────────────────────────────────────────────────────┤
│  v0.2.0 · 3 host ออนไลน์ · 2 ออฟไลน์                     │  ← status bar
└──────────────────────────────────────────────────────────┘
```

- **Topbar**: logo/ชื่อระบบ + ค้นหา host (กรอง fleet) + **`.topnav`** (Fleet/Alerts/ตั้งค่า แนวนอน — ไม่มี sidebar) + เมนูผู้ใช้ (logout). จอเล็ก topnav กะทัดรัดลง
- **Status bar** (ล่าง): version + สรุป quick count (อ่าน `v{__version__}` จาก server ไม่ hardcode)
- คลิก host card → `window.Monitor.setHostId(id)` → เลือก host + renderHostView + scroll ไป `#view-host`
- พื้นที่ content: card grid, padding 16–24px

---

## 3. Design Tokens

### สี (tokens.css)
| Token | ค่า | ใช้กับ |
|-------|-----|--------|
| `--bg` | `#f6f7f9` | พื้นหลังรวม |
| `--surface` | `#ffffff` | การ์ด/panel |
| `--border` | `#e5e7eb` | เส้นขอบ |
| `--text` | `#111827` | ตัวหนังสือหลัก |
| `--text-2` | `#6b7280` | ตัวหนังสือรอง/label |
| `--accent` | `#0d9488` (teal) | brand, active, link |
| `--accent-soft` | `#ccfbf1` | พื้นหลัง highlight |
| `--success` | `#16a34a` | online / ok |
| `--warn` | `#d97706` | เตือน / ใกล้เต็ม |
| `--danger` | `#dc2626` | offline / alert / ผิดพลาด |

### ตัวอักษร (clamp)
| บทบาท | ค่า |
|--------|-----|
| heading | `clamp(1.25rem, 1rem + 1vw, 1.5rem)` |
| KPI เลขเด่น | `clamp(1.75rem, 1.25rem + 2vw, 2.5rem)` |
| body | `0.875rem`–`0.9375rem` |
| label/รอง | `0.75rem`–`0.8125rem` (สี `--text-2`) |
| font-family | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (ไม่โหลด font ภายนอก) |

### พื้นที่/ระยะ
- card: `padding 16px`, `border-radius 12px`, `border 1px var(--border)`, `background var(--surface)`
- gap card: `12–16px` (grid)
- shadow: เล็กๆ `0 1px 3px rgba(0,0,0,.06)` — การ์ดลอยเบาๆ

### Responsive
- **360**: 1 คอลัมน์, topnav กะทัดรัด, KPI ซ้อนแนวตั้ง
- **768**: 2 คอลัมน์ KPI, fleet 2 การ์ด
- **1280+**: 3–4 คอลัมน์ fleet, content เต็ม (ไม่มี sidebar)

### UI Scaling — ขยายทั้งกรอบ (ไม่ใช่แค่ฟอนต์)
ปรับ **ทั้ง container/grid/card/ระยะ/ฟอนต์** ให้สัดส่วนลื่นไหลตามความละเอียดหน้าจอ (เหมือน zoom ทั้ง UI) — ใช้ **CSS `zoom`** กับ wrapper หลัก

```css
.app-root {
  zoom: var(--ui-scale, 1);   /* ขยายทั้งกรอบ — จัดการ layout ให้อัตโนมัติ */
}
```

```js
// static/js/scale.js
const DESIGN_WIDTH = 1280;              // ความกว้างที่ออกแบบ (baseline)
function setScale() {
  const scale = Math.min(1.4, Math.max(0.6, window.innerWidth / DESIGN_WIDTH));
  document.documentElement.style.setProperty('--ui-scale', scale);
}
window.addEventListener('resize', setScale);
setScale();
```

**หลักการทำงาน:**
- ออกแบบ UI ที่ความกว้าง baseline `1280px` → `--ui-scale = 1`
- จอเล็ก/ใหญ่ → JS คำนวณ `innerWidth / 1280` แล้วตั้ง `--ui-scale` → `zoom` ขยาย/หด **ทั้งกรอบ** (การ์ด, ระยะ, ฟอนต์, grid ขยับพร้อมกัน)
- กำหนดขอบ `clamp(0.6, …, 1.4)` กันหดเล็กเกิน/โตเกิน
- **ยังคงมี breakpoints 360/768/1280 ไว้** — `zoom` จัดสัดส่วนส่วนตัว แต่โครงสร้าง (กี่คอลัมน์, ขนาด topnav) ยังเป็นหน้าที่ของ media query

**ข้อควรรู้:**
- `zoom` เป็น non-standard แต่รองรับ Chrome/Edge/Safari + Firefox (126+) — เหมาะกับ dashboard
- `transform: scale()` **ไม่ใช้** — มันไม่ reflow layout (เหลือที่ว่างรอบ) แต่ `zoom` reflow ถูกต้อง
- fallback ถ้า `zoom` ไม่รองรับ: ตั้ง `--ui-scale` เป็นตัวคูณแล้วใช้กับทุกขนาด (`calc(px * var(--ui-scale))`) ใน tokens

---

## 4. ภาษา UI + Data Formatting & Units

### 4.1 ภาษา UI (i18n)
- **ล็อกภาษา UI = ไทย** (ตาม convention โปรเจกต์ — comment/docstring ไทยด้วย) — ป้าย/label/ข้อความทั้งหมดเป็นไทย
- เก็บสตริงไว้ใน `static/js/i18n.js` (object `{ "fleet": "Fleet", ... }`) — กัน hardcode กระจาย, เปลี่ยนภาษาได้ทีเดียว
- **ตัวเลข/หน่วย เป็นสากล** (ไม่ผูกภาษา) — ใช้จุดทศนิยม, ตัวคั่นหลักพันแบบมาตรฐาน
- ศัพท์เทคนิค (CPU/RAM/Disk/Net/Uptime) ใช้ภาษาอังกฤษตามปกติ (ไม่มีคำไทยเทียบตรง)

### 4.2 รูปแบบตัวเลข/หน่วย (format.js — ใช้ร่วมกันทุกคอมโพเนนต์)
| ประเภท | กติกา | ตัวอย่าง |
|--------|-------|----------|
| เปอร์เซ็นต์ | 1 ทศนิยม + `%` | `42.5%` |
| bytes (ขนาด) | หลักพัน: B→KB→MB→GB→TB (base 1024), 2 ทศนิยมเมื่อ ≥1 หลัก | `8589934592` → `8.00 GB` |
| อัตรา (bytes/s) | หลักเดียวกับ bytes + `/s` | `1258291` → `1.20 MB/s` |
| จำนวนเต็ม (procs, cores) | ตัวคั่นหลักพัน | `1200` → `1,200` |
| uptime | ย่อ: `Xd`, `Xh`, `Xm` (ใหญ่สุดที่เหลือ) | `86400` → `1d`, `129600` → `1d 12h` |
| ค่า 0/ไม่มีข้อมูล | แสดง `—` (ไม่ใช่ 0 ที่ทำให้เข้าใจผิด) | `—` |

- ใส่ helper ใน `static/js/format.js`:
  - `formatPercent(v)`, `formatBytes(v)`, `formatRate(v)`, `formatInt(v)`, `formatUptime(sec)`
- **ห้าม** แต่ละคอมโพเนนต์เขียน format เอง — ใช้ helper ร่วมกัน (กันตัวเลขเพี้ยนข้ามหน้า)
- หน่วยของค่าใน API: server คืนค่า raw (bytes) + `unit` — client เป็นคน format (`API.md` series มี `unit`)

---

## 5. View + Wireframe

### 5.1 Login
```
┌──────────────┐
│   ● Monitor  │
│              │
│   Username   │  [input]
│   Password   │  [••••••]
│   [เข้าสู่ระบบ]  │
│              │
└──────────────┘   (การ์ดกลางจอ, กว้าง ~360px)
```
- ศูนย์กลางจอ, error แสดงแดงใต้ฟอร์ม, rate-limit ถ้าผิดบ่อย

### 5.2 Fleet (หน้าหลัก)
```
┌───────────────────────────────────────────────────┐
│ Fleet            [🟢 ออนไลน์] [⚪ ทั้งหมด]   [+เพิ่ม] │
├───────────────────────────────────────────────────┤
│ 5 เครื่อง · 4 ออนไลน์ · 1 ออฟไลน์ · 4 Linux · 1 Win  │  ← สถิติ Fleet
├───────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │🖥 web-01     │ │🖥 db-02      │ │🪟 app-03     │ │
│ │ ● ออนไลน์     │ │ ○ ออฟไลน์    │ │ ● ออนไลน์     │ │
│ │ CPU ████░░ 42%│ │ CPU ██░░░░ 18%│ │ CPU ███░░░ 33%│ │
│ │ RAM ████░░ 48%│ │ RAM ██████ 91%│ │ RAM ██░░░░ 25%│ │
│ │ Disk ██░░░░ 20%│ │ Disk ████░░ 55%│ │ Disk █░░░░░  8%│ │
│ │ ↑1.2↓0.8 MB/s │ │ —             │ │ ↑0.4↓0.9 MB/s │ │
│ │ uptime 24d    │ │ —             │ │ uptime 3h     │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
│ (การ์ด grid, คลิก → host-view)                       │
└───────────────────────────────────────────────────┘
```
- **Fleet ด้านบนมีสถิติ**: `N เครื่อง · X ออนไลน์ · Y ออฟไลน์ · L Linux · W Windows` (`#fleetStats`)
- **toolbar**: filter tab (ทั้งหมด/ออนไลน์/ออฟไลน์) + tag filter + ปุ่ม **"+ เพิ่มเครื่องใหม่"** + รีเฟรช
- **+ เพิ่มเครื่องใหม่** → modal วิซาร์ด (ตั้งค่า agent: host_id/interval/watch/ports/max-batch พร้อม hint อธิบายใต้ฟิลด์) → สร้าง token (POST `/api/v1/auth/tokens`) + พิมพ์คำสั่ง `--install` → คัดลอก; ก็มี "ดูวิธีติดตั้ง agent" ใน empty state (modal แบบย่อ)
- **HostCard**: OS icon (ได้จาก `platform` → linux/windows/mac) + ชื่อ + badge (🟢 ออนไลน์ / ○ ออฟไลน์) + progress bar CPU/RAM/Disk + Net + uptime
- ออฟไลน์: การ์ด dim (opacity .6) + badge แดง, ไม่มีค่า net (`—`)
- filter: tab ทั้งหมด/ออนไลน์/ออฟไลน์ + ค้นหาจาก topbar + tag filter
- poll `GET /api/v1/hosts` ทุก ~10s

### 5.3 Host (dashboard รายเครื่อง)
```
┌──────────────────────────────────────────────────┐
│ ลงตัว  web-01   ● ออนไลน์   [1h][6h][1d][7d][30d][45d]   │
├──────────────────────────────────────────────────┤
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │
│ │ CPU 42%│ │ RAM 48%│ │ Disk 20%│ │ Uptime │      │  ← KPI row
│ │ 4 cores│ │ 8.0 GB │ │ 500 GB │ │ 24d 3h │      │
│ └────────┘ └────────┘ └────────┘ └────────┘      │
├──────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────┐     │
│ │  CPU (%)                          ┌────┐ │     │
│ │     ▄▄▄▄  ▄▄                              │ │     │  ← MetricChart
│ │  ▄▄▄      ▄▄▄    ▄▄▄                       │ │     │  (Chart.js line)
│ │        ▄▄      ▄▄▄      ▄▄▄                │ │     │
│ │  └──────────────────────────────▶ 1h       │ │     │
│ └──────────────────────────────────────────┘     │
│ (กราฟ CPU + RAM + Disk/Net สลับแท็บ)             │
└──────────────────────────────────────────────────┘
```
- **Host** (section ในหน้านี้): dropdown เลือก host + KPI row + metric chips + chart (เลือก metric ทีละตัว กันสเกล) — เปลี่ยน host จาก dropdown หรือคลิกการ์ด Fleet
- **ปุ่ม "แก้ไข"** (toolbar): modal แก้ hostname/tags + remote config (interval/watch/ports/max_batch) + ลบ host (confirm) — ค่าตั้งผ่านนี้ถูกเก็บเป็น `desired_config` แล้ว agent pull ไป apply (ไม่ restart)
- **MetricChart**: line chart, เลือก range (1h raw / 6h,1d,7d,30d,45d rollup), เลือก metric (CPU/RAM/Load/Swap/Processes/Uptime ผ่าน chip selector — plot ทีละตัวเดียว กันสเกลเพี้ยน)
- alert ที่ active ของ host นี้: แถบเตือนสีแดง/เหลืองด้านบน
- data: `GET /api/v1/hosts/{id}/metrics?range=...&metrics=<metric>` (ระบุ metric เดียว → แสดงเส้นเดียว + y-axis ตั้งชื่อตาม unit)

### 5.4 Alerts
```
┌──────────────────────────────────────────────────┐
│ Alerts          [กฎ] [ประวัติ]        [+สร้างกฎ]   │
├──────────────────────────────────────────────────┤
│ ▸ CPU สูง (web-01 >90% 5m)          [แก้][ลบ]     │
│ ▸ RAM เต็ม (ทุก host >85%)          [แก้][ลบ]     │
│ ───────────────────────────────────────────────── │
│ ● 14:32  web-01  CPU 94% เกิน 90%   [ack]        │  ← history
│ ● 13:05  db-02   RAM 91% เกิน 85%   [ack ✓]      │
└──────────────────────────────────────────────────┘
```
- Tab: กฎ / ประวัติ
- ประวัติ: timestamp + host + metric + ค่า + ปุ่ม ack (สีจางลงเมื่อ ack แล้ว)

### 5.5 Settings
```
┌──────────────────────────────────────────────────┐
│ ตั้งค่า                                            │
│  Agent Token     [table: host_id | token | revoke]│
│  Alert Rules     [table: name | metric | op | thr]│
│  Retention       [45d] [1m/5m/1h/1d]  [บันทึก]      │
│  WebUI           [user/pass/secret]               │
└──────────────────────────────────────────────────┘
```
- token: gen/revoke ต่อ host (ตาราง)
- เปลี่ยนแล้ว `POST` → เขียน config.toml + ใช้ทันที
- alert rule form: Host เป็น dropdown (— ทุก host — + รายชื่อ host จริง), Metric ตรงกับรายการที่ alert engine รองรับ (cpu_percent/memory.percent/used/total/swap.used/total/load1/5/15/disk.percent/uptime/procs)

---

## 6. Interaction & Behavior

### Navigation (SPA)
- **Hash routing** — view เปลี่ยนตาม `#/fleet`, `#/host/<id>`, `#/alerts`, `#/settings` — ปุ่ม **back/forward ใช้ได้**
- refresh หน้า → กลับมาที่ view เดิม (อ่านจาก hash)
- host-view: `#/host/<id>` — reload ยังอยู่ host เดียวกัน

### Click / Action
| อินเทอร์แอคชัน | พฤติกรรม |
|----------------|----------|
| คลิก HostCard | → host-view (`#/host/<id>`) |
| คลิก badge/filter tab | กรอง fleet (ออนไลน์/ทั้งหมด) |
| ปุ่ม range (1h/6h/1d/7d/30d/45d) | โหลด chart ใหม่ (active state ชัดเจน) |
| ลบ host / revoke token | **ต้อง confirm dialog** (กันลบพลาด) |
| บันทึก config | toast "บันทึกแล้ว" + ใช้ทันที |
| logout | ลบ cookie → กลับ login |
| 401 จาก API | redirect ไป login อัตโนมัติ + toast "เซสชันหมดอายุ" |

### Feedback (toast)
- ระบบ toast มุมขวาบน: `success` (เขียว) / `error` (แดง) / `info` (neutral)
- auto-hide ~4s (error คงอยู่จนปิด)
- ใช้กับผลลัพธ์การกระทำ (บันทึก, ลบ, gen token, ack)

### Loading / Disable
- ปุ่มที่กำลังทำงาน: `disabled` + spinner ในตัว (ไม่บล็อกทั้งหน้า)
- ระหว่าง poll: อย่าให้การ์ดกระพริบ — อัปเดตค่าเฉยๆ (diff แบบเงียบ)

---

## 7. Chart config spec (Chart.js)

### ทั่วไป
```js
new Chart(ctx, {
  type: 'line',
  data: { datasets: [{ data: points, borderColor: 'var(--accent)', borderWidth: 2,
                       pointRadius: 0, tension: 0.3, fill: false }] },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,            // ปิด animation — performance ตอน poll/ข้อมูลเยอะ
    interaction: { mode: 'nearest', intersect: false },
    scales: { x: { type: 'time', time: { tooltipFormat: 'HH:mm' } },
              y: { beginAtZero: true, ticks: { callback: fmtByUnit } } },
    plugins: { tooltip: { callbacks: { label: (c) => `${fmt(c.raw.value)} ${unit}` } },
               legend: { display: false } }   // single series → ปิด legend
  }
});
```

### กฎ
| ข้อ | ค่า/กติกา |
|-----|-----------|
| type | `line`, single dataset (ปิด legend) |
| animation | `false` (ข้อมูล poll ถี่ — กันกระตุก/CPU) |
| x-axis | time scale, format `HH:mm` (1h/6h) / `dd MMM` (1d+) |
| y-axis | `beginAtZero: true` ยกเว้น metric ที่ไม่มีค่าลบ; tick ใช้ `format.js` |
| tooltip | แสดงค่า + หน่วย (จาก `series[].unit`) — ใช้ `format.js` เหมือนกัน |
| สี | ใช้ `var(--accent)`; metric อันตราย (เกิน threshold) ใช้ `--danger` |
| จุด | `pointRadius: 0` (เส้นลื่น, ดู trend) — แสดงเฉพาะ hover |
| empty data | แสดงข้อความ "ไม่มีข้อมูลในช่วงนี้" แทนกราฟเปล่า |
| height | คงที่ ~240px (parent มี height, `maintainAspectRatio:false`) |

---

## 8. Form spec

### 8.1 สร้าง/แก้ Alert Rule
| ช่อง | type | validate |
|------|------|----------|
| ชื่อ | text | ต้องไม่ว่าง, ≤64 ตัว |
| Host | select (ทุก host / เฉพาะ) | — |
| Metric | select (cpu_percent/memory.percent/disk/…) | — |
| Operator | select (`>` `>=` `<` `<=` `==`) | — |
| Threshold | number | ต้องเป็นตัวเลข, ช่วงตาม metric |
| Duration | text | รูปแบบ `5m`/`1h` — parse ได้ |
| Notify | checkbox (webhook/telegram) | — |

- error: แดงใต้ช่องที่ผิด + ไม่ submit; ปุ่ม Submit disabled จนกว่า validate ผ่าน

### 8.0 กฎรูปแบบ input / select / textarea / checkbox (ทุกหน้า)

> **ต้องสไตล์เดียวกันทั้งหมด** — กันตกขอบ/ต่างแบบ ใช้ tokens ร่วมกัน (`--surface`/`--border`/`--accent`).

| กติกา | ค่า |
|-------|-----|
| กล่อง (`input:not(checkbox/radio/range/color/file)`, `select`, `textarea`) | `padding 8px 12px`, `border 1px var(--border)`, `radius 8px`, `bg var(--surface)`, `color var(--text)` |
| Focus | `border-color var(--accent)` + `box-shadow 0 0 0 2px var(--accent-soft)` |
| placeholder | `color var(--text-2)`, opacity .8 |
| disabled | `opacity .6` + `cursor not-allowed` |
| checkbox / radio | ใช้ `accent-color var(--accent)`, ขนาด 16px ไม่ใส่กล่อง |
| compact (toolbar/grid) | `padding 6px 10px` (ขนาดรอง) — ยังคง border/radius/bg เท่ากล่องหลัก |
| ห้าม | inline style ต่าง/สีเฉพาะตัว, ตั้ง font เอง (ใช้ `var(--font)`) |

- **ห้าม**เขียน CSS เฉพาะ `input`/`select` แยกกันจนต่างแบบ — ถ้าเพิ่ม input ชนิดใหม่ ให้ใช้ rule กลางแบบเดียว
- rule กลางอยู่ใน `app.css` (`input, select, textarea, button` + focus) — เดิมมีแค่ `.field input` ทำให้ select/checkbox ต่างจาก text box (แก้แล้ว)
- **ไม่มี sidebar** — เมนูนำทาง (Fleet/Alerts/ตั้งค่า) เป็น `.topnav` แนวนอนใน topbar, content กินพื้นที่เต็ม (long page)

### 8.2 Gen Agent Token
- เลือก host → ปุ่ม "สร้าง token" → แสดง token ครั้งเดียว (copy ได้) → **ไม่แสดงซ้ำหลังปิด**
- revoke: confirm dialog ก่อน

### 8.3 ตั้งค่า WebUI (user/pass/secret)
- เปลี่ยน password: ยืนยัน 2 รอบ (ใหม่/ยืนยัน) — ตรงกันถึง submit
- secret_key: ไม่ให้แก้จาก UI (แสดง masked, แก้ผ่าน config.toml)

---

## 9. Edge cases
| กรณี | พฤติกรรม |
|------|----------|
| host ใหม่ยังไม่มี data | host-view แสดง "ยังไม่มีข้อมูล — รอ push แรก" (KPI `—`), chart "ไม่มีข้อมูล" |
| ค่า = 0 จริง | แสดง `0%`/`0 B` — ต่างจาก `—` (ไม่มีข้อมูล) |
| fleet หลายร้อย host | virtualize/แบ่งหน้า (pagination หรือ infinite scroll), poll ฉลาด (ช้าลงถ้า offline) |
| network ช้า / API error | แบนเนอร์ + retry, ไม่ทำ poll ซ้อนกัน (skip ถ้า request ก่อนยังไม่จบ) |
| offline host นาน | การ์ด dim ถาวร + เน้นใน filter ออฟไลน์ |
| ค่าเกิน threshold ต่อเนื่อง | alert แถบแดง, chart เส้น `--danger` |
| ตัวเลขใหญ่เกินหน่วย | `formatBytes` เลื่อนเป็น TB อัตโนมัติ (ไม่ overflow) |

---

## 10. สถานะ (states)
| สถานะ | ลักษณะ |
|--------|--------|
| Loading | skeleton/shimmer ใน card (ไม่ใช่ spinner ทั้งหน้า) |
| Empty (ไม่มี host) | illustration ง่าย + "ยังไม่มี host — ติดตั้ง agent" + ปุ่มดูวิธี |
| Offline | card dim + badge แดง |
| Error API | แบนเนอร์แดงบน view + ปุ่มลองใหม่ |
| Alert active | แถบเตือนสี (warn/danger) เหนือ KPI |

---

## 11. คอมโพเนนต์ (spec ย่อ)
| คอมโพเนนต์ | ข้อกำหนด |
|-------------|----------|
| HostCard | grid minmax(240px,1fr), progress bar `--accent`/`--warn`/`--danger` ตามเปอร์เซ็นต์, offline dim |
| KPI | ตัวเลข `clamp` ใหญ่, label `--text-2`, 4 ต่อ row (2 @768, 1 @360) |
| MetricChart | Chart.js line ตาม section 7, tooltip มีหน่วย, legend ปิด |
| Badge | pill `border-radius 999px`, bg `--*-soft`, text สี semantic |
| ProgressBar | `height 6px`, radius 999px, fill เปลี่ยนสีตาม threshold (≥80 warn, ≥90 danger) |
| Button | primary `--accent`/white, ghost = border; radius 8px; `disabled` + spinner |
| Toast | มุมขวาบน, success/error/info, auto-hide 4s |
| Modal (confirm) | overlay + การ์ดกลาง, ปุ่ม ยกเลิก/ยืนยัน (danger ใช้ `--danger`) |

---

## 12. Accessibility
- **Contrast**: text หลักบน `--surface` ≥ 4.5:1, label `--text-2` ≥ 4.5:1 — ตรวจด้วย Lighthouse/axe
- **Focus state**: `:focus-visible` ใช้ `--accent` outline 2px — มองเห็นชัด, keyboard นำทางได้ทุกอินเทอร์แอคชัน
- **Keyboard**: Enter/Space เปิด action, Tab วนถูกลำดับ, Esc ปิด modal/toast
- **aria**: button/icon มี `aria-label`, modal มี `role="dialog"` + `aria-modal`, form field ผูก `label`/`aria-describedby` กับ error
- สีเดียวไม่พอ — ใช้ **ไอคอน/ข้อความ** ร่วมกับสี (เช่น offline มีคำว่า "ออฟไลน์" ด้วย ไม่ใช่แค่สีแดง)
- ลด motion: เคารพ `prefers-reduced-motion`

---

## 13. ข้อกำหนด
- API ใต้ `/api/*` ห้ามชน static (`/static`)
- Login หน้า WebUI ต้องมี (admin user/pass, bcrypt, HttpOnly cookie)
- `chart.umd.min.js` bundle local (offline ใช้ได้) — **ไม่ใช้ CDN**
- ทุกหน้า responsive 360/768/1280 — ตรวจด้วย Playwright ไม่ overflow แนวนอน
- (แนะนำ) CSP + security headers + rate-limit login

---

## 14. คำแนะนำเพิ่มเติม (ทำได้ทีหลัง)
- **SSE realtime** — แทน poll (ปัจจุบัน poll Fleet 10s + Host 5s/1นาที): `/api/v1/events` push ค่าใหม่ (fleet + chart สดขึ้นทันที) — ทางเลือกถ้าต้องการ push ต่อ
- **ธีมมืด** — เพิ่ม `data-theme="dark"` สลับ tokens (ยังใช้ `--` variables เดิม)
- **Export CSV** — ปุ่มต่อ metric/range (API มีแล้วใน `API.md`)
- **Mini-map** — sparkline เล็กใน HostCard (มีแล้วสำหรับ Fleet) ขยายให้ครบ metric
- **แจ้งเตือน popup** — toast ด้านขวาบนเมื่อ alert trigger (webhook → SSE ถึงเบราว์เซอร์)
