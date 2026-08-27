<!-- เทมเพลต release notes — release.yml แทนที่ ${TAG} อัตโนมัติ
     จำเป็นต้องอัปเดตส่วน "จุดเด่นของเวอร์ชันนี้" ก่อนแต่ละ release -->

# monitor-server ${TAG}

ระบบ monitor ข้ามแพลตฟอร์ม: **central server** (FastAPI + SQLite + WebUI dashboard) + **agent** ตัวเล็ก (Python stdlib-only) ที่ push metrics มาให้ — แจกจ่ายเป็น binary ใช้งานทันที ไม่ต้องติดตั้ง Python

## ไฟล์ที่แนบ

| ไฟล์ | ระบบ | คืออะไร |
|------|------|--------|
| `monitor-server.exe` | Windows x64 | Central server — รันได้เลย / `--service install` ทำ Windows service |
| `monitor-agent.exe` | Windows x64 | Agent — ติดตั้งด้วย `--install` (สร้าง service + agent.cfg ให้เอง) |
| `monitor-server` | Linux x86_64 | Central server (glibc 2.28+ ดูด้านล่าง) |
| `monitor-agent` | Linux x86_64 | Agent (glibc 2.28+ ดูด้านล่าง) |

## Linux: รองรับ glibc 2.28+ (build บน manylinux_2_28)

binary Linux build ใน container `manylinux_2_28` (glibc 2.28) — **รันได้บน**:

- **AlmaLinux 8, 9 · Rocky Linux 8, 9**
- **RHEL 8, 9** · CentOS Stream 9
- Ubuntu 20.04 / 22.04 / 24.04 · Debian 11 / 12 / 13 · Fedora 32+

> หมายเหตุ: v0.3.2 และก่อนหน้า build บน Ubuntu 24.04 (ต้อง glibc 2.39+) — ใช้ release นี้สำหรับ distro ที่เก่ากว่า

## จุดเด่นของเวอร์ชันนี้

- **Linux binary รองรับ Alma/Rocky 8-9, RHEL 8-9** (glibc 2.28+) — build บน manylinux_2_28 แทน ubuntu-24.04
- pipeline build + smoke test: รัน `--help` ของ binary จริงใน container glibc 2.28 + ตรวจ glibc symbol ก่อน publish
- release notes เป็นเทมเพลต (`.github/release-notes.md`) แก้ไขง่าย + trigger release ด้วยมือได้ (workflow_dispatch)

## เริ่มต้นใช้งาน (เร็ว)

### 1) Server (เครื่องกลาง)

**Windows:** ดับเบิลคลิก `monitor-server.exe`
**Linux:**

```bash
chmod +x monitor-server
sudo ./monitor-server
```

> ครั้งแรก: สร้าง `config.toml` + `data/` **ข้างไฟล์** แล้ว**พิมพ์รหัสผ่าน admin (สุ่ม) ลง console** — จดไว้
> เปิด WebUI ที่ URL ที่พิมพ์ (default `http://127.0.0.1:18080`) — login ด้วยรหัสผ่านนั้น

### 2) Agent (เครื่องที่ถูก monitor)

สร้าง token ใน WebUI (หน้า Fleet → "+ เพิ่มเครื่องใหม่") แล้ว:

**Windows:**

```
monitor-agent.exe --install --server http://<IP-SERVER>:18080 --token <TOKEN> --interval 15
```

**Linux:**

```bash
chmod +x monitor-agent
sudo ./monitor-agent --install --server http://<IP-SERVER>:18080 --token <TOKEN> --interval 15
```

> optional: `--ports 80:web,443:https` (เฝ้า TCP port) · `--watch nginx,mysql` (เฝ้า service)
> uninstall: `--uninstall` (ลบ service)

<details>
<summary>English summary</summary>

- **monitor-server** (central) + **monitor-agent** (push-based, stdlib-only) — cross-platform monitoring with Web dashboard, alerting (webhook/Telegram), historical graphs (45-day retention with rollups).
- **Assets:** Windows x64 `.exe` × 2 + Linux x86_64 ELF × 2.
- **Linux compatibility:** built on `manylinux_2_28` (glibc 2.28) — runs on **AlmaLinux/Rocky 8 & 9, RHEL 8 & 9**, Ubuntu 20.04+, Debian 11+, Fedora 32+. (v0.3.2 and earlier required glibc 2.39+.)
- First server run auto-creates `config.toml` next to the binary and prints a random admin password.
- Install agent with `--install --server <url> --token <token>` (creates the OS service automatically).
</details>
