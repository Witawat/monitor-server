# SESSION_STATE — สถานะงานล่าสุด (อัปเดตทุกครั้งหลังจบงาน)

> ไฟล์นี้สรุปสถานะการทำงานแบบบีบอัด เพื่อให้ session ใหม่เริ่มงานได้ทันที
> (อ่านคู่กับ `AGENTS.md` ซึ่งเก็บกฎ/สถาปัตยกรรม/คำสั่งคงที่)
> **กฎ**: หลังจบงานแต่ละรอบ ต้องอัปเดตส่วน Completed/Active/Next Move + commit ล่าสุด

## เวอร์ชัน / commit ล่าสุด
- Version `0.3.2` (release ผ่านแล้ว · asset ครบ 4) · repo public: https://github.com/Witawat/monitor-server (branch `master`)
- Commit ล่าสุด: `3dadbb8` (v0.3.2 — build Linux ตรงบน ubuntu-latest) · tag บน origin: v0.3.0, v0.3.1, v0.3.2 (แต่ publish release จริงมีแค่ **v0.3.2** — 0.3.0/0.3.1 เป็น tag แก้ pipeline ที่ไม่ได้ publish)
- `__version__` = `0.3.2` แล้ว (เดิมค้าง 0.2.0 → WebUI/API เคยโชว์ "v0.2.0" ไม่ตรง tag)

## Objective
- Build/maintain `monitor-server` (FastAPI + aiosqlite + WebUI) + `monitor-agent` (stdlib-only) → แจกจ่ายเป็น PyInstaller exe (onefile + UPX)
- WebUI: login admin, fleet dashboard, per-host dashboard + graph ย้อนหลัง (rollup), alerting (webhook/Telegram), remote host config, metric ครบ, security headers + rate limit + audit log

## ข้อสำคัญ (อย่าลืม)
- Frozen exe: `sys.frozen` → resolve data/logs/config/state **ข้าง exe**; server exe ไม่ต้อง `--config` (default "" → config.toml ข้าง exe; ครั้งแรกสร้าง + พิมพ์ admin/random)
- venv **ไม่มี psutil** → agent (dev + exe) เป็น stdlib-only → ส่งได้แค่ `host_info`/`cpu_cores` (ทุกแพลตฟอร์ม) + `disk_io` (Linux); `top_process`/`nic_status`/`process_detail` ว่าง → UI ซ่อน section อัตโนมัติ
- Windows .ps1 ต้อง ASCII-only; TOML path ใช้ forward slash
- bash tool kill process ค้าง; ใช้ `run-long.ps1` (D:\MyCode\opencode\scripts) สำหรับคำสั่งยาว
- gitignore: data/, logs/, config.toml, build/, dist/, *.spec, scripts/tools/upx/, .venv/, state.json, host_id, queue.json, agent.cfg
- CI: ruff + `mypy --disable-error-code=unused-ignore server agent shared` + pytest (py3.11/3.12)
- **Linux ELF build บน ubuntu-24.04 (glibc 2.39)** → รองรับแค่ Ubuntu 24.04+/Debian 13+/Fedora 40+ — ถ้าต้องการลง Debian 12/Ubuntu 22.04 ต้อง build บน manylinux2014/2014 (ยังไม่ได้ทำ); release notes + workflow ขึ้น glibc 2.39+ แล้ว
- Release workflow: push tag `v*` → build matrix 2 OS → publish; **tag v0.3.0/v0.3.1 ไม่มี release object** (pipeline ยังไม่ผ่านตอนนั้น)

## Completed (งานที่ทำเสร็จทั้งหมด)
- CI + Release workflows + README badges; ruff/mypy/pytest ผ่าน
- Remote config (ชิ้น A): `desired_config`, API GET/PUT `/hosts/{id}/config`, ingest คืน config, agent `apply_remote()` ไม่ restart, WebUI "แก้ไข" modal + delete host — commit `6ff690b`
- Notifier settings (webhook/Telegram): `server/alerting/settings.py` (DB `state_kv["notifiers"]` > config.toml), API GET/PUT `/settings/notifiers` + test ทั้ง 2 + scan chatid, `notify.py` DB-aware + enabled, UI cards + test + toggle + badge + wizard — commits `13b906e` `562fa03` `1e23510` `38881da`
- Login security: DB rate limit (login_attempts, per-IP `login_rate_per_min`=5 + global `login_global_per_min`=30, `[auth]`) + `audit_log` + API `GET /auth/audit` + WebUI "ประวัติการเข้าสู่ระบบ" — commit `7486f80`
- Change password + first-run auto-fill: `POST /auth/password`, `GET /auth/setup`, login.js auto-fill, settings grid — commits `271f666` `bcd007b` `4d6d39f`
- **Chunk B — metric เพิ่ม (commit `67608c3`):**
  - `shared/metric.py`: +DiskIOSample/TopProcessSample/NicSample/HostInfo/ProcessDetail + Snapshot fields (disk_io/top_process/host_info/cpu_cores/nic_status/process_detail) + from/to dict
  - `agent/collect.py`: provider เก็บ metric ใหม่ (psutil ครบ / stdlib: host_info, cpu_cores, disk_io-linux) + snapshot()
  - `server/storage/db.py`: migrate columns ใหม่ + `disk_io_samples` (rate จาก delta) + `_metrics_values` (18 ค่า) + insert_snapshot/insert_batch + `_latest_summary` คืน field ใหม่ + `_latest_disk_io_rate` + json helpers
  - WebUI: `host.html` (hostInfoRow + topProcSection + nicSection) + `dashboard.js` (renderExtras + renderTable) — ซ่อนถ้าไม่มีข้อมูล
  - **fix guard (commit `0aa94fe`)**: top_process/process_detail ครอบ `try/except (psutil.AccessDenied, psutil.NoSuchProcess)`
- **Alert badge** (รอบนี้): `db.count_unacked_history()` + `GET /api/v1/alerts/badge` → `{unacked:N}` + `.nav-badge` บนเมนู Alerts (poll 30s)
- **Filter fleet polish** (รอบนี้): ตัวนับผลลัพธ์ "แสดง X / Y เครื่อง" + คลิก "ทั้งหมด" เคลียร์ tag ด้วย
- **SSE realtime** (รอบนี้): `server/streaming.py` (SSEHub — event bus, กัน leak + queue เต็ม) + `GET /api/v1/stream` (admin, heartbeat 15s) + broadcast: ingest→hosts+alerts / ack→alerts / host-down(offline.py)→alerts + `initSSE()` ฝั่ง client (backoff reconnect, ลด poll fleet 10s→30s safety net)
- i18n: **ข้าม** (ผู้ใช้เลือกไม่ทำรอบนี้)
- **Alert rules ค่าเริ่มต้น + กัน seed ซ้ำ** (รอบนี้): `AlertingConfig.rules` default 3 กฎ (CPU>90% 10m / RAM>90% 10m / Disk>85% 15m, metric `disk.percent`) + `seed_rules_from_config` ใช้ flag `rules_seeded` กันเด้งกลับตอน user ลบกฎหมด (รองรับ install เก่าด้วย) — test_exe 14/14
- **ตาราง Alerts แสดงช่องแจ้งเตือน** (รอบนี้): เพิ่มคอลัมน์ "แจ้งเตือน" ในตารางกฎ — badge ตามสถานะ (Webhook/Telegram configured+enabled=เขียว, ปิด/ยังไม่ได้ตั้ง=เทา-เหลือง, ไม่เลือก=—) — `loadAlerts` ดึง `/settings/notifiers` เอง render badge ถูกเสมอ — ยืนยัน UI จาก exe จริงด้วย playwright
- **Release cross-platform v0.3.0→v0.3.2**: `release.yml` build matrix 2 OS (Windows .exe + Linux ELF) — แก้ pipeline Linux 3 รอบ: manylinux2014 (pillow 11+ ไม่มี wheel → ล้ม) → manylinux_2_17 → **build ตรงบน ubuntu-latest ข้าม Docker** (commit `e937694` `a333b1c` `4171d24` `2a28ba9` `bf4abb5` `3dadbb8`) — v0.3.2 publish ผ่าน asset ครบ 4 (0.3.0/0.3.1 เป็น tag ที่ไม่ได้ publish)
- **bump `__version__` 0.2.0 → 0.3.2**: WebUI/API เคยโชว์ "v0.2.0" ไม่ตรง release tag — `server/__init__.py` + test ยืนยัน (test ใช้ `__version__` จริง ไม่ hardcode)
- **จัด CHANGELOG ตาม release**: ย้าย feature ที่ค้างใน [Unreleased] ลง [0.3.0] + เพิ่มหัวข้อ [0.3.1]/[0.3.2] + หมายเหตุความรองรับ glibc ของ Linux ELF
- **แก้ release notes/ความรองรับ Linux**: workflow + `--notes` ขึ้น glibc 2.39+ (Ubuntu 24.04+/Debian 13/Fedora 40+) แทนข้อความเดิมที่เคลม glibc 2.35+/Debian 12 (ไม่จริง — build บน ubuntu-24.04)

## Active / งานที่ทำได้ต่อ (ยังไม่ทำ)
- i18n ธีม/ข้อความ WebUI (ข้ามมา 3 รอบแล้ว — ทำได้ถ้าต้องการ)
- เพิ่ม psutil ลง requirements-agent → agent บนเครื่องจริงส่ง top_process/NIC/process_detail ครบ (ตอนนี้ stdlib-only ส่งได้จำกัด)
- Linux รองรับ glibc 2.17/2.30 (Debian 12/Ubuntu 22.04) → ต้องกลับ build บน manylinux image (ตอนนี้ build บน ubuntu-24.04 = glibc 2.39+ เท่านั้น)
- (เลือกทำ) release notes ของ v0.3.2 ที่ publish อยู่แล้วบน GitHub ยังเป็นข้อความเก่า (เคลม glibc 2.35+/Debian 12) — แก้ด้วย `gh release edit v0.3.2 --notes "..."` ได้ (workflow แก้แล้วสำหรับ release ถัดไป)
- dark mode — user ไม่เอา (ปิดประเด็น)

## Blocked
- (ไม่มี)

## Next Move
- เปิด session ใหม่: อ่าน AGENTS.md + SESSION_STATE.md แล้วเริ่มจาก Active ตามที่ผู้ใช้เลือก
- ลำดับแนะนำ: psutil agent (ได้ metric ครบบนเครื่องจริง) → i18n → manylinux (ถ้าต้องการลง distro เก่า)
- **จำไว้**: ตอนตัด release ถัดไป (v0.3.3/v0.4.0) ต้อง bump `__version__` ใน `server/__init__.py` ให้ตรงกับ tag (ตอนนี้ = 0.3.2 ตรง release ปัจจุบัน; ตัวที่ปล่อย v0.3.2 ยังโชว์ v0.2.0 เพราะ build ก่อน bump)

## คำสั่งยืนยัน (ตัวอย่าง)
- `.\dist\monitor-agent.exe --install --server http://127.0.0.1:18080 --token <TOKEN> --interval 15 [--ports 80:web,443:https] [--watch nginx,mysql]`
- dev: `python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15`
- ตรวจก่อนส่ง: `ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q`
- build: `scripts\build.bat` · test exe: `scripts\test_exe.ps1 -Port 18089` (13 checks ต้องผ่าน)
