# CODING_GUIDE.md — รูปแบบการเขียน Code + คำอธิบาย Code

> source of truth สำหรับสไตล์โค้ด + ภาษา docstring ของโปรเจกต์นี้. อ้างอิงจาก `AGENTS.md` (กฎสั้น) — ไฟล์นี้คือรายละเอียดเต็ม + ตัวอย่าง.

## 1. ภาพรวม

- **ภาษา comment/docstring: ไทย** — ใช้ศัพท์เทคนิคภาษาอังกฤษเท่าที่จำเป็น (ชื่อคลาส/method/library)
- ยึด **PEP 8** (format) + **PEP 257** (docstring)
- ใช้ `ruff` + `mypy` เป็นเกณฑ์บังคับ — `ruff check .; mypy --disable-error-code=unused-ignore server agent shared; pytest -q` ต้องผ่านก่อน PR

## 2. ชื่อ (naming)

| ประเภท | แบบ | ตัวอย่าง |
|--------|-----|----------|
| module/package | snake_case | `ingest.py`, `metric.py` |
| class | PascalCase | `IngestService`, `MetricStore` |
| function/method | snake_case | `build_batch`, `validate_snapshot` |
| private (ไม่ใช้ภายนอก) | ขึ้นต้น `_` | `_parse_header`, `_delta` |
| constant | UPPER_SNAKE | `OFFLINE_TIMEOUT_SEC`, `MAX_BATCH` |
| type hint | ระบุเสมอ | `def run(url: str) -> None:` |

## 3. Docstring (PEP 257) — ภาษาไทย

- **ทุก public function/class/method ต้องมี docstring** (สรุป 1 บรรทัด)
- private (ขึ้นต้น `_`) ไม่บังคับ แต่ถ้าซับซ้อนควรมี
- เพิ่ม `Args:` / `Returns:` / `Raises:` / `Notes:` **เฉพาะเมื่อจำเป็น** (หลาย param / exception / พฤติกรรมไม่ชัด)

```python
def compute_rate(prev: int, curr: int, dt: float) -> float:
    """คำนวณอัตรา (bytes/s) จาก cumulative counter สองจุด.

    Args:
        prev: ค่า counter ครั้งก่อน (cumulative bytes).
        curr: ค่า counter ครั้งล่าสุด.
        dt: ระยะเวลาระหว่างสองจุด (วินาที).

    Returns:
        อัตราเป็น bytes/s; คืน 0 ถ้า dt <= 0 หรือ curr < prev (clock reset).
    """
    if dt <= 0 or curr < prev:
        return 0.0
    return (curr - prev) / dt
```

```python
class MetricStore:
    """Async access layer สำหรับตาราง metrics/time-series ใน SQLite."""

    def upsert_host(self, host_id: str, info: HostInfo) -> None:
        """สร้างหรืออัปเดตแถว host + อัปเดต last_seen.

        Raises:
            sqlite3.IntegrityError: ถ้า token ใช้ไม่ได้ (host ถูก revoke).
        """
        ...
```

### หลักของ docstring
- สรุป 1 บรรทัดแรกบอก **"ทำอะไร"** ไม่ใช่ "เป็นอย่างไร"
- อย่าอธิบายสิ่งที่เห็นจากชื่อ function อยู่แล้วซ้ำ (`def start(): """เริ่มระบบ"""` แบบนี้ฟุ่มเฟือย — ให้บอก *ผล/จุดประสงค์* ที่ไม่ชัด เช่น `"""เริ่ม worker เก็บ metrics พื้นหลัง โดยไม่บล็อก caller."""`)
- ถ้าไม่มีอะไรต้องเพิ่ม → ใช้ docstring 1 บรรทัดสั้นๆ ก็พอ (ไม่ต้องบังคับ Args/Returns ทุกครั้ง)

## 4. Inline Comment (PEP 8) — เขียนแบบ "why"

- เว้น **2 ช่อง** ก่อน `#` + 1 ช่องหลัง `#`
- เขียน **จุดประสงค์/เหตุผล (why)** ไม่ใช่เล่าโค้ด (what)
- comment ทั้งบรรทัดเริ่มด้วย `# `
- **ห้าม comment ที่ obvious** — โค้ดอ่านรู้เรื่อง = ไม่ต้อง comment

```python
# ตัวอย่างที่ถูก: อธิบาย "why"
if curr < prev:                 # ตัวนับถูกรีเซ็ต (reboot/nic down) — อย่าคำนวณลบ
    return 0.0

retry = min(retry * 2, 300)     # backoff แบบทวีคูณ กันยิง server ซ้ำถี่ยิบตอน offline
```

```python
# ตัวอย่างที่ผิด: เล่าโค้ดซ้ำ + เว้นช่องไม่ถูก
x = x + 1   #เพิ่ม x   # ← obvious + ผิด spacing
for i in items:   # วนลูป items   # ← obvious
```

### Section divider
```python
# ── helpers ──
# ── collect ──
# ── push ──
```
ใช้คั่นกลุ่มฟังก์ชันในไฟล์ยาว — คงรูปแบบ `# ── ชื่อ ──` ให้สม่ำเสมอ.

## 5. โครงสร้าง module (ตัวอย่าง)

```python
"""โมดูล collect metrics ฝั่ง agent (stdlib เท่านั้น)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ── schema / types ──

@dataclass
class Snapshot:
    """หนึ่งจุดข้อมูล metric ของ host."""

    ts: int
    cpu_percent: float
    memory: dict[str, int | float]
    ...

# ── collect ──

def _read_cpu() -> float:
    ...

def collect() -> Snapshot:
    """เก็บ snapshot ปัจจุบันของ host ทั้งหมด."""

    ...

# ── push ──

def push(url: str, token: str, batch: list[dict[str, Any]]) -> bool:
    """ส่ง batch ไป server; คืน True ถ้าสำเร็จ (204/200)."""

    ...
```

- import: ใช้ `from __future__ import annotations` (Python 3.11) · เรียงตาม isort/ruff `I`
- type hint ครบทุก public — `mypy` บังคับ
- ไฟล์ละ **หนึ่งความรับผิดชอบ** — `collect`, `push`, `storage` แยกกัน

## 6. ตัวอย่าง metric schema (shared/metric.py)

```python
class NetSample(BaseModel):
    """สถิติของหนึ่ง network interface."""

    iface: str
    rx_bytes: int = 0          # cumulative counter — server คำนวณ rate เอง
    tx_bytes: int = 0

class Snapshot(BaseModel):
    """หนึ่งจุดข้อมูล metric ของ host ณ เวลา ts."""

    host_id: str
    hostname: str
    platform: str              # linux / windows
    ts: int
    cpu_percent: float = 0.0
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)
    memory: MemorySample
    disk: list[DiskSample] = []
    net: list[NetSample] = []
    uptime: int = 0
    procs: int = 0
```

> ใช้ `BaseModel` (pydantic) จาก `shared/` — แต่ `shared/` **ต้องบาง** ไม่ import fastapi เพื่อให้ agent (stdlib) ใช้ได้ (ถ้า agent ไม่เอาพึ่ง pydantic → ใช้ dict schema ตรงและ validate ฝั่ง server).

## 7. กับดักสไตล์เฉพาะโปรเจกต์

- **agent ห้าม import `server/`** — ใช้แค่ `shared/` ที่บาง
- path: `pathlib`/`os.path` เสมอ ห้าม hardcode `/` (ข้ามแพลตฟอร์ม)
- `except Exception` ที่จับแล้วไม่มี log → ให้ log เหตุผล (ลด silent fail)
- async: `async def` สำหรับ I/O; ใช้ `aiosqlite`; ระวัง race เขียน DB พร้อมกัน

## 8. ตรวจ docstring ครบ (AST)

```powershell
.venv\Scripts\python.exe -c "import ast,pathlib;ms=[(str(p),n.name) for p in pathlib.Path('.').rglob('*.py') if '__pycache__' not in str(p) and '.venv' not in str(p) for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and not n.name.startswith('_') and ast.get_docstring(n) is None];print('missing:',ms)"
```

## 9. เกณฑ์ผ่าน (ก่อน commit)

```powershell
ruff check .          # format + lint
mypy --disable-error-code=unused-ignore server agent shared   # type check
pytest -q             # test
```
- แก้ comment/docstring อย่างเดียว = ไม่กระทบ logic → ไม่ต้อง rebuild service แต่ยังต้องผ่าน ruff/mypy/pytest
