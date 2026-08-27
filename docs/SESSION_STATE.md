# SESSION_STATE — สถานะงานล่าสุด (อัปเดตทุกครั้งหลังจบงาน)

> ไฟล์นี้สรุปสถานะการทำงานแบบบีบอัด เพื่อให้ session ใหม่เริ่มงานได้ทันที
> (อ่านคู่กับ `AGENTS.md` ซึ่งเก็บกฎ/สถาปัตยกรรม/คำสั่งคงที่)
> **กฎ**: หลังจบงานแต่ละรอบ ต้องอัปเดตส่วน Completed/Active/Next Move + commit ล่าสุด

## เวอร์ชัน / commit ล่าสุด
- Version `0.2.0` · repo public: https://github.com/Witawat/monitor-server (branch `master`)
- Commit ล่าสุด: (จะ commit หลังรอบนี้ — alert badge + filter fleet polish + SSE realtime)

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

## Active / งานที่ทำได้ต่อ (ยังไม่ทำ)
- กลุ่มที่เหลือจากรายการแนะนำ: dark mode (user ไม่เอา), i18n (ข้ามรอบนี้ — ทำได้ถ้าต้องการ), alert badge+filter fleet+SSE ทำแล้ว
- เพิ่ม psutil ลง requirements-agent ถ้าต้องการเห็น top_process/NIC เต็มบนเครื่องจริง

## Blocked
- (ไม่มี)

## Next Move
- เปิด session ใหม่: อ่าน AGENTS.md + SESSION_STATE.md แล้วเริ่มจาก Active ตามที่ผู้ใช้เลือก

## คำสั่งยืนยัน (ตัวอย่าง)
- `.\dist\monitor-agent.exe --install --server http://127.0.0.1:18080 --token <TOKEN> --interval 15 [--ports 80:web,443:https] [--watch nginx,mysql]`
- dev: `python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15`
- ตรวจก่อนส่ง: `ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q`
- build: `scripts\build.bat` · test exe: `scripts\test_exe.ps1 -Port 18089` (13 checks ต้องผ่าน)
