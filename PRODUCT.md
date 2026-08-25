# PRODUCT.md — monitor-server (Product Context)

## Users
- ผู้ดูแลระบบ / DevOps / เจ้าของเครื่องหลายเครื่อง ที่อยากเห็นสถานะเครื่องทั้งหมดในที่เดียวแบบ realtime
- คนใช้ VPS / dedicated servers หลายตัว (DigitalOcean/Plesk ไลฟ์สไตล์) — ไม่ชอบ login หลายที่
- คนที่อยากได้แจ้งเตือนอัตโนมัติ (CPU/RAM/Disk เต็ม, host หาย) โดยไม่ต้องมานั่งเฝ้า

## Purpose (ปัญหาที่แก้)
- รวม metrics จากเครื่องหลายเครื่องไว้ที่ **central server เดียว** ดูผ่าน Web UI หน้าเดียว
- **Push model**: agent เก็บ metrics แล้ว push ไปที่ server (เร็ว, ผ่าน NAT/firewall ได้ — ไม่ต้อง expose port บนเครื่องที่ monitor)
- ข้ามแพลตฟอร์ม: เดิมเครื่องผสม Linux/Windows มักต้องใช้หลาย tool — ระบบนี้ครอบทั้งคู่
- agent **เล็ก** + รันเป็น service — ลงได้แม้เครื่อง resource ต่ำ ไม่กินสเปก

## Design Principles
1. **Push ก่อน Pull เสมอ** — agent เป็นฝ่ายรุก push; server ไม่ต้องดึง (รองรับ NAT/offline ได้)
2. **Agent ต้องเล็กมาก** — stdlib-only (psutil optional) footprint ต่ำ, deploy ง่าย
3. **ทุกอย่างผ่าน Web UI** — ไม่เน้น CLI; server config ด้วย toml, จัดการ agent token ผ่านหน้าเว็บ
4. **กัน drift** — schema/contract อยู่ใน `shared/` เดียว ใช้ทั้ง server+agent
5. **ทน offline** — agent queue + retry + backoff ส่งข้อมูลย้อนหลังได้
6. **ข้ามแพลตฟอร์ม** — path ด้วย `pathlib`, service ทั้ง systemd + NSSM
7. **Security แน่น** — token ต่อ host, rate limit ingest, login admin WebUI

## สิ่งที่ "ไม่ใช่" (non-goals สำหรับ MVP)
- ไม่ใช่ APM / tracing (Logz/NewRelic) — โฟกัส host-level metrics
- ไม่ใช่ log aggregator — เก็บแค่ metrics/time-series
- ไม่ต้อง realtime ระดับ millisecond — ระดับวินาที/นาที (interval agent) พอ

## การวัดความสำเร็จ
- agent ติดตั้ง/รัน service ได้ 1 นาทีทั้ง 2 OS
- dashboard โหลด 1 host เร็ว, กราฟย้อนหลัง 1h/1d แสดงถูก
- alert ผิด threshold → notify ได้จริง
- agent offline → กลับมา push ส่งข้อมูลที่ค้างไว้ให้
