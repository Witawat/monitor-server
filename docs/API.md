# API.md — /api/v1/* spec

> ทุก endpoint อยู่ใต้ `/api/v1/*` ยกเว้น status/health/documentation. Agent ใช้ `X-Agent-Token` header; WebUI ใช้ cookie หลัง login. OpenAPI อัตโนมัติที่ `/docs`.

## Error format (ทั่วไป)
```json
{ "detail": "คำอธิบาย" }
```
Status: `400` invalid, `401` ไม่มี auth/token ผิด, `403` ไม่อนุญาต, `404` ไม่พบ, `429` rate limit

## Ingest (agent → server)
### `POST /api/v1/ingest`
- Header: `X-Agent-Token: <token>`
- Body: batch ของ metric snapshots (schema ใน `shared/metric.py` / `docs/ARCHITECTURE.md`)
- Response `200`: `{"status":"ok","received":N,"host_id":"uuid"}`

| เงื่อนไข | ผล |
|----------|-----|
| token ไม่รู้จัก | `401` |
| body ไม่ตรง schema / เกิน `max_batch_size` | `400` |
| เกิน `rate_limit_per_min` | `429` |

> ครั้งแรกที่ token ใหม่ push (ถ้า `allow_registration=true`) → auto-register host.

## Hosts
### `GET /api/v1/hosts`
- Query: `?online=bool` (กรองเฉพาะออนไลน์/ออฟไลน์)
- Response: list hosts + `online` (push ภายใน `offline_timeout_sec`) + `platform` (`linux`/`windows`) + `tags` + latest summary (cpu/mem/disk/uptime)

### `GET /api/v1/hosts/{id}`
- Detail ของ host เดียว + latest snapshot + tags

### `DELETE /api/v1/hosts/{id}` *(admin)*
- ลบ host + metrics + revoke token

### `PUT /api/v1/hosts/{id}/tags` *(admin)*
- ตั้ง tags ของ host: `{"tags": ["env=prod", "location=th"]}`

### `GET /api/v1/hosts/{id}/config` *(admin)*
- คืน remote config ที่ตั้งผ่าน UI (`desired_config`) เช่น `{"interval":10,"watch":"nginx","ports":"80:web"}` (ว่างถ้ายังไม่ตั้ง)

### `PUT /api/v1/hosts/{id}/config` *(admin)*
- ตั้ง remote config ต่อ host (agent จะ pull ไป apply ในรอบถัดไป **ไม่ restart**):
  `{"interval":10,"watch":"nginx,mysql","ports":"80:web,443:https","max_batch":50,"hostname":"web-prod"}`
- check: `interval`/`max_batch` ต้อง int >= 1; `watch`/`ports` เป็น string คั่น `,`; `hostname` เปลี่ยนชื่อแสดงใน UI
- หมายเหตุ: `interval`/`watch`/`ports`/`max_batch` เป็น config ฝั่ง agent (เครื่องถูก monitor) — บันทึกที่ server แล้ว agent ตามมาเอง

## Metrics
### `GET /api/v1/hosts/{id}/metrics?range=1h&metrics=cpu_percent,memory.percent`
- `range`: `1h` (raw), `6h`/`1d`/`7d`/`30d`/`45d` (rollup อัตโนมัติ), default `1h`
- `metrics`: list ชื่อ metric คั่น `,` (ต้องอยู่ใน `METRIC_COLUMNS`) — ว่าง = คืน `cpu_percent,memory.percent,load1,load5,load15,uptime`
- Response:
```json
{
  "host_id": "uuid",
  "range": "1h",
  "series": {
    "cpu_percent": {"unit": "%", "points": [[ts, val], ...]}
  }
}
```

## Alerts
### `GET /api/v1/alerts` *(admin)* — list rules
### `POST /api/v1/alerts` *(admin)* — สร้าง rule (schema ใน `CONFIG.md:alerting.rules`)
### `PUT /api/v1/alerts/{id}` *(admin)* — แก้
### `DELETE /api/v1/alerts/{id}` *(admin)* — ลบ
### `GET /api/v1/alerts/history` — ประวัติ trigger (filter `?host_id=&rule_id=&ack=false`)
### `POST /api/v1/alerts/history/{id}/ack` *(admin)* — acknowledge

## Auth (WebUI)
### `POST /api/v1/auth/login`
- Body: `{"username","password"}` → set HttpOnly cookie, `200 {"ok":true}`
### `POST /api/v1/auth/logout`
### `GET /api/v1/auth/me` — ข้อมูลผู้ใช้ปัจจุบัน
### `GET /api/v1/auth/tokens` *(admin)* — list agent tokens
### `POST /api/v1/auth/tokens` *(admin)* — gen token ต่อ host_id
### `DELETE /api/v1/auth/tokens/{host_id}` *(admin)* — revoke

## Status / misc
### `GET /api/status` *(admin)* — version, host_count, server{host,port,data_dir,log_dir}, ingest{rate_limit,max_batch_size,offline_timeout}
### `GET /api/health` — `{"status":"ok"}` (ไม่ต้อง auth — ใช้ probe service)
### `GET /api/v1/hosts/{id}/export?range=1d` *(admin)* — export CSV

## Note
- WebUI SPA เรียก API เหล่านี้โดยตรง — ห้ามชน static (`/static`)
- agent ใช้เฉพาะ `POST /api/v1/ingest` เท่านั้น
