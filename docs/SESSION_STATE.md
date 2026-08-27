# SESSION_STATE — สถานะงานล่าสุด (อัปเดตทุกครั้งหลังจบงาน)

> ไฟล์นี้สรุปสถานะการทำงานแบบบีบอัด เพื่อให้ session ใหม่เริ่มงานได้ทันที
> (อ่านคู่กับ `AGENTS.md` ซึ่งเก็บกฎ/สถาปัตยกรรม/คำสั่งคงที่)
> **กฎ**: หลังจบงานแต่ละรอบ ต้องอัปเดตส่วน Completed/Active/Next Move + commit ล่าสุด

## เวอร์ชัน / commit ล่าสุด
- Version `0.3.3` (release ผ่านแล้ว · asset ครบ 4) · repo public: https://github.com/Witawat/monitor-server (branch `master`)
- Commit ล่าสุด: `8ba007d` (v0.3.3 — build Linux บน manylinux_2_28 + build Python 3.11.14 `--enable-shared`) · tag บน origin: v0.3.0, v0.3.1, v0.3.2, **v0.3.3** (publish จริง: **v0.3.2 + v0.3.3**)
- `__version__` = `0.3.3` (`server/__init__.py`)

## Objective
- Build/maintain `monitor-server` (FastAPI + aiosqlite + WebUI) + `monitor-agent` (stdlib-only) → แจกจ่ายเป็น PyInstaller onefile (UPX สำหรับ .exe)
- WebUI: login admin, fleet dashboard, per-host dashboard + graph ย้อนหลัง (rollup), alerting (webhook/Telegram), remote host config, metric ครบ, security headers + rate limit + audit log
- Linux binary ต้องรันได้บน distro เก่า (Alma/Rocky 8, glibc 2.28)

## ข้อสำคัญ (อย่าลืม)
- Frozen exe: `sys.frozen` → resolve data/logs/config/state **ข้าง exe**; server exe ไม่ต้อง `--config` (default "" → config.toml ข้าง exe; ครั้งแรกสร้าง + พิมพ์ admin/random)
- venv **ไม่มี psutil** → agent (dev + exe) เป็น stdlib-only → ส่งได้แค่ `host_info`/`cpu_cores` (ทุกแพลตฟอร์ม) + `disk_io` (Linux); `top_process`/`nic_status`/`process_detail` ว่าง → UI ซ่อน section อัตโนมัติ
- Windows .ps1 ต้อง ASCII-only; TOML path ใช้ forward slash
- bash tool kill process ค้าง; ใช้ `run-long.ps1` (D:\MyCode\opencode\scripts) สำหรับคำสั่งยาว
- gitignore: data/, logs/, config.toml, build/, dist/, *.spec, scripts/tools/upx/, .venv/, state.json, host_id, queue.json, agent.cfg
- CI: ruff + `mypy --disable-error-code=unused-ignore server agent shared` + pytest (py3.11/3.12)
- **Linux build (release)**: docker `quay.io/pypa/manylinux_2_28_x86_64:2026.01.04-1` + `scripts/build-manylinux.sh` — build CPython 3.11.14 จาก source ด้วย `--enable-shared` (Python ใน image ไม่มี shared lib → PyInstaller ล้ม) → binary **glibc 2.28+** (ตรวจ GLIBC symbol + smoke test `--help` ใน container) — รองรับ Alma/Rocky 8-9, RHEL 8-9, Ubuntu 20.04+, Debian 11+, Fedora 32+
- Release workflow: push tag `v*` → build 2 OS (Windows + Linux docker) → publish (notes จากเทมเพลต `.github/release-notes.md` แทนที่ `vX.Y.Z`) + trigger มือได้ (`workflow_dispatch` + tag input)
- tag v0.3.0/v0.3.1 ไม่มี release object (pipeline ยังไม่ผ่านตอนนั้น) — tag แก้ pipeline ที่ไม่ได้ publish

## Completed (งานที่ทำเสร็จทั้งหมด)
- CI + Release workflows + README badges; ruff/mypy/pytest ผ่าน
- Remote config (ชิ้น A): `desired_config`, API GET/PUT `/hosts/{id}/config`, ingest คืน config, agent `apply_remote()` ไม่ restart, WebUI "แก้ไข" modal + delete host — commit `6ff690b`
- Notifier settings (webhook/Telegram): `server/alerting/settings.py` (DB `state_kv["notifiers"]` > config.toml), API GET/PUT `/settings/notifiers` + test ทั้ง 2 + scan chatid, `notify.py` DB-aware + enabled, UI cards + test + toggle + badge + wizard — commits `13b906e` `562fa03` `1e23510` `38881da`
- Login security: DB rate limit (login_attempts, per-IP `login_rate_per_min`=5 + global `login_global_per_min`=30, `[auth]`) + `audit_log` + API `GET /auth/audit` + WebUI "ประวัติการเข้าสู่ระบบ" — commit `7486f80`
- Change password + first-run auto-fill: `POST /auth/password`, `GET /auth/setup`, login.js auto-fill, settings grid — commits `271f666` `bcd007b` `4d6d39f`
- **Chunk B — metric เพิ่ม (commit `67608c3`):**
  - `shared/metric.py`: +DiskIOSample/TopProcessSample/NicSample/HostInfo/ProcessDetail + Snapshot fields + from/to dict
  - `agent/collect.py`: provider เก็บ metric ใหม่ (psutil ครบ / stdlib: host_info, cpu_cores, disk_io-linux) + snapshot()
  - `server/storage/db.py`: migrate columns ใหม่ + `disk_io_samples` (rate จาก delta) + `_metrics_values` (18 ค่า) + insert_snapshot/insert_batch + `_latest_summary` + `_latest_disk_io_rate` + json helpers
  - WebUI: `host.html` (hostInfoRow + topProcSection + nicSection) + `dashboard.js` (renderExtras + renderTable) — ซ่อนถ้าไม่มีข้อมูล
  - **fix guard (commit `0aa94fe`)**: top_process/process_detail ครอบ `try/except (psutil.AccessDenied, psutil.NoSuchProcess)`
- **Alert badge**: `db.count_unacked_history()` + `GET /api/v1/alerts/badge` → `{unacked:N}` + `.nav-badge` บนเมนู Alerts (poll 30s)
- **Filter fleet polish**: ตัวนับผลลัพธ์ "แสดง X / Y เครื่อง" + คลิก "ทั้งหมด" เคลียร์ tag ด้วย
- **SSE realtime**: `server/streaming.py` (SSEHub — event bus, กัน leak + queue เต็ม) + `GET /api/v1/stream` (admin, heartbeat 15s) + broadcast: ingest→hosts+alerts / ack→alerts / host-down(offline.py)→alerts + `initSSE()` ฝั่ง client (backoff reconnect, ลด poll fleet 10s→30s safety net)
- i18n: **ข้าม** (ผู้ใช้เลือกไม่ทำ)
- **Alert rules ค่าเริ่มต้น + กัน seed ซ้ำ**: `AlertingConfig.rules` default 3 กฎ (CPU>90% 10m / RAM>90% 10m / Disk>85% 15m, metric `disk.percent`) + `seed_rules_from_config` ใช้ flag `rules_seeded` กันเด้งกลับตอน user ลบกฎหมด — test_exe 14/14
- **ตาราง Alerts แสดงช่องแจ้งเตือน**: คอลัมน์ "แจ้งเตือน" + badge สถานะ — `loadAlerts` ดึง `/settings/notifiers` เอง render badge ถูกเสมอ — ยืนยัน UI จาก exe จริงด้วย playwright
- **Release cross-platform v0.3.0→v0.3.2**: `release.yml` build matrix 2 OS — แก้ pipeline Linux 3 รอบ (manylinux2014 → manylinux_2_17 → build ตรงบน ubuntu-latest) — v0.3.2 publish ผ่าน asset ครบ 4
- **bump `__version__` 0.2.0 → 0.3.2** (+ 0.3.3): WebUI/API โชว์ version ตรง tag — `server/__init__.py` + test ใช้ `__version__` จริง
- **จัด CHANGELOG ตาม release** + หมายเหตุความรองรับ glibc ของ Linux ELF
- **แก้ release notes v0.3.2** (`gh release edit`): ขึ้น glibc 2.39+ จริง + ชี้ไป v0.3.3 สำหรับ distro เก่า
- **Release notes เป็นเทมเพลต**: `.github/release-notes.md` (asset table + quick start + EN summary) — release.yml แทนที่ version อัตโนมัติ
- **v0.3.3 — Linux binary รองรับ glibc 2.28+ (รอบนี้)**:
  - Root cause: PyInstaller บน Linux ต้อง `libpython3.11.so` แต่ Python ใน manylinux image (ทุก tag) build โดยไม่มี shared lib → build v0.3.3 แรก (tag ชี้ commit เก่า) ล้ม
  - แก้: `scripts/build-manylinux.sh` — build CPython **3.11.14** จาก source (`--enable-shared`, ไม่มี PGO/LTO) ใน container → venv → pytest → PyInstaller ×2 → smoke test `--help` → ตรวจ GLIBC symbol ≤ 2.28
  - `release.yml` job build-linux: docker manylinux_2_28:2026.01.04-1 (แทน ubuntu-latest) + `workflow_dispatch` (tag input)
  - `requirements-build.txt`: ปลด pin pillow (Pillow 12 ใช้ได้กับ make_icon.py)
  - verify: probe workflow รัน script ฉบับเต็มผ่าน → re-tag v0.3.3 ที่ `8ba007d` → release run 33052825280 ผ่านทุก job · asset 4 · GLIBC symbol สูงสุด **2.14** · 109 passed · smoke test OK ใน container glibc 2.28 · notes แทนที่ version ถูก
  - commit: `8ba007d` (+ probe workflow ที่ลบแล้ว)

## Active / งานที่ทำได้ต่อ (ยังไม่ทำ)
- i18n ธีม/ข้อความ WebUI (ข้ามมา 4 รอบแล้ว — ทำได้ถ้าต้องการ)
- เพิ่ม psutil ลง requirements-agent → agent บนเครื่องจริงส่ง top_process/NIC/process_detail ครบ (ตอนนี้ stdlib-only ส่งได้จำกัด)
- (ถ้าต้องการ) Linux รองรับ glibc เก่ากว่า 2.28 (Ubuntu 18.04/Debian 10) → ต้อง manylinux_2_27/manylinux2014 — นิชมาก ไม่คุ้ม

## Blocked
- (ไม่มี)

## Next Move
- เปิด session ใหม่: อ่าน AGENTS.md + SESSION_STATE.md แล้วเริ่มจาก Active ตามที่ผู้ใช้เลือก
- ลำดับแนะนำ: psutil agent (ได้ metric ครบบนเครื่องจริง) → i18n
- **จำไว้**: ตอนตัด release ถัดไปต้อง bump `__version__` ใน `server/__init__.py` ให้ตรงกับ tag (ตอนนี้ = 0.3.3 ตรง release ปัจจุบัน)
- **จำไว้**: Linux build = docker manylinux_2_28 + build Python source (~4 นาที) — ถ้าเปลี่ยน image tag ใหม่ต้อง probe ก่อน (Python ใน image อาจไม่มี shared lib)

## คำสั่งยืนยัน (ตัวอย่าง)
- `.\dist\monitor-agent.exe --install --server http://127.0.0.1:18080 --token <TOKEN> --interval 15 [--ports 80:web,443:https] [--watch nginx,mysql]`
- dev: `python -m agent.agent --server http://127.0.0.1:18080 --token <TOKEN> --interval 15`
- Linux (Alma/Rocky 8+): `chmod +x monitor-server && ./monitor-server` · agent: `./monitor-agent --install --server <URL> --token <TOKEN>`
- ตรวจก่อนส่ง: `ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q`
- build: `scripts\build.bat` (Windows) · test exe: `scripts\test_exe.ps1 -Port 18089` (13 checks ต้องผ่าน)
