"""ทดสอบ server/ingest.py — validate batch + rate limit + auto-register."""

from __future__ import annotations

import pytest

from server.config import AppConfig
from server.ingest import (
    IngestService,
    InvalidBatch,
    RateLimited,
    UnauthorizedToken,
)
from server.storage.db import Database


@pytest.fixture
async def service(tmp_path):
    """IngestService + Database ตัวจริง (temp file)."""

    database = Database(tmp_path / "ingest.db")
    await database.connect()
    yield IngestService(database, AppConfig())
    await database.close()


def _batch(**overrides):
    """สร้าง batch 1 snapshot เป็น dict."""

    data = {
        "host_id": "h1",
        "hostname": "web-01",
        "platform": "linux",
        "ts": 1000,
        "cpu_percent": 10.0,
    }
    data.update(overrides)
    return [data]


async def test_auto_register_new_token(service):
    """token ใหม่ + allow_registration=True → สร้าง host ใหม่."""

    received, host_id, _cfg = await service.process_batch("tok-new", "1.1.1.1", _batch())
    assert received == 1
    assert host_id == "h1"
    assert await service._db.host_by_token("tok-new") is not None


async def test_known_token_updates_last_seen(service):
    """token เดิม → ใช้ host เดิม ไม่สร้างซ้ำ."""

    await service.process_batch("tok-a", "1.1.1.1", _batch())
    _, host_id, _cfg = await service.process_batch("tok-a", "1.1.1.1", _batch())
    assert host_id == "h1"


async def test_precreated_host_empty_hostname_adopts_snapshot(service):
    """host ที่สร้างก่อนด้วย token (hostname ว่าง) → ingest ใช้ hostname จาก snapshot.

    กันกรณี host ถูกสร้างผ่าน set_host_token ก่อน first push จน hostname ค้างว่าง.
    """

    await service._db.set_host_token("h2", "tok-b")
    await service.process_batch("tok-b", "1.1.1.1", _batch(host_id="h2", hostname="web-02"))
    host = await service._db.host_by_token("tok-b")
    assert host is not None
    assert host["hostname"] == "web-02"


async def test_unauthorized_when_registration_off(service):
    """token ไม่รู้จัก + ปิด auto-register → UnauthorizedToken."""

    cfg = AppConfig()
    cfg.auth.allow_registration = False
    service._config = cfg
    with pytest.raises(UnauthorizedToken):
        await service.process_batch("tok-x", "1.1.1.1", _batch())


async def test_empty_batch_invalid(service):
    """batch ว่าง → InvalidBatch."""

    with pytest.raises(InvalidBatch):
        await service.process_batch("tok", "1.1.1.1", [])


async def test_oversized_batch_invalid(service):
    """batch เกิน max_batch_size → InvalidBatch."""

    cfg = AppConfig()
    cfg.ingest.max_batch_size = 2
    service._config = cfg
    with pytest.raises(InvalidBatch):
        await service.process_batch("tok", "1.1.1.1", [_batch(), _batch(), _batch()])


async def test_rate_limit(service):
    """ยิงเกิน rate_limit_per_min → RateLimited."""

    cfg = AppConfig()
    cfg.ingest.rate_limit_per_min = 2
    service._config = cfg
    await service.process_batch("tok", "9.9.9.9", _batch())
    await service.process_batch("tok", "9.9.9.9", _batch())
    with pytest.raises(RateLimited):
        await service.process_batch("tok", "9.9.9.9", _batch())


async def test_empty_token_rejected(service):
    """token ว่าง → UnauthorizedToken (กันยึด identity host ที่ revoke แล้ว)."""

    with pytest.raises(UnauthorizedToken):
        await service.process_batch("", "1.1.1.1", _batch())


async def test_revoked_host_cannot_be_adopted_with_empty_token(service):
    """host ที่ revoke (token='') ต่อให้ส่ง token ว่าง ก็ไม่ยึด identity กลับมาได้."""

    await service._db.set_host_token("h1", "tok-real")
    await service._db.revoke_token("h1")   # token กลายเป็น ''
    with pytest.raises(UnauthorizedToken):
        await service.process_batch("", "1.1.1.1", _batch(host_id="h1"))
