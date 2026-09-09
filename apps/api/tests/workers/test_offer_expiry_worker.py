"""Unit tests for the offer expiry worker process and health check."""

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.offer_expiry import OfferExpiryResult
from app.workers import offer_expiry_worker, offer_expiry_worker_health


@dataclass
class _WorkerSettings:
    """Minimum settings surface used by the expiry worker."""

    database_url: str | None
    offer_expiry_worker_poll_interval_seconds: int
    offer_expiry_worker_batch_size: int
    offer_expiry_worker_id: str | None
    offer_expiry_worker_heartbeat_path: Path
    offer_expiry_worker_heartbeat_max_age_seconds: int
    log_level: str = "INFO"


class _SessionContext:
    """Minimal asynchronous session context manager."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


class _FakeDatabase:
    """Database replacement that records cleanup and health calls."""

    instances: list["_FakeDatabase"] = []

    def __init__(self, _: str) -> None:
        self.disposed = False
        self.ping_called = False
        _FakeDatabase.instances.append(self)

    def session_factory(self) -> _SessionContext:
        """Return a disposable fake request session."""
        return _SessionContext()

    async def dispose(self) -> None:
        """Record worker shutdown cleanup."""
        self.disposed = True

    async def ping(self) -> None:
        """Record a successful database health check."""
        self.ping_called = True


async def _cancel_sleep(_: float) -> None:
    """End an intentionally infinite worker loop after one observed cycle."""
    raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_empty_cycle_records_heartbeat_and_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty batch is healthy and waits before its next poll."""
    heartbeat_path = tmp_path / "offer-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        offer_expiry_worker_poll_interval_seconds=1,
        offer_expiry_worker_batch_size=50,
        offer_expiry_worker_id="expiry-test-worker",
        offer_expiry_worker_heartbeat_path=heartbeat_path,
        offer_expiry_worker_heartbeat_max_age_seconds=120,
    )
    calls: list[dict[str, object]] = []

    async def fake_expire_due_offers(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> OfferExpiryResult:
        calls.append(
            {
                "batch_size": batch_size,
                "request_id": request_id,
            }
        )
        return OfferExpiryResult(expired_offer_ids=())

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(offer_expiry_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(offer_expiry_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(offer_expiry_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(
        offer_expiry_worker,
        "expire_due_offers",
        fake_expire_due_offers,
    )
    monkeypatch.setattr(offer_expiry_worker.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await offer_expiry_worker.main()

    assert calls == [
        {
            "batch_size": 50,
            "request_id": "expiry-test-worker",
        }
    ]
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_successful_expiry_batch_is_processed_before_next_poll(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-empty batch is processed immediately without sleeping first."""
    heartbeat_path = tmp_path / "offer-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        offer_expiry_worker_poll_interval_seconds=1,
        offer_expiry_worker_batch_size=25,
        offer_expiry_worker_id="expiry-test-worker",
        offer_expiry_worker_heartbeat_path=heartbeat_path,
        offer_expiry_worker_heartbeat_max_age_seconds=120,
    )
    calls = 0

    async def fake_expire_due_offers(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> OfferExpiryResult:
        nonlocal calls
        calls += 1

        assert batch_size == 25
        assert request_id == "expiry-test-worker"

        if calls == 1:
            return OfferExpiryResult(expired_offer_ids=(uuid4(),))

        raise RuntimeError("temporary database failure")

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(offer_expiry_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(offer_expiry_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(offer_expiry_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(
        offer_expiry_worker,
        "expire_due_offers",
        fake_expire_due_offers,
    )
    monkeypatch.setattr(offer_expiry_worker.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await offer_expiry_worker.main()

    assert calls == 2
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_temporary_failure_does_not_write_a_false_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed cycle waits to retry and does not report unhealthy work as live."""
    heartbeat_path = tmp_path / "offer-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        offer_expiry_worker_poll_interval_seconds=1,
        offer_expiry_worker_batch_size=50,
        offer_expiry_worker_id="expiry-test-worker",
        offer_expiry_worker_heartbeat_path=heartbeat_path,
        offer_expiry_worker_heartbeat_max_age_seconds=120,
    )

    async def failing_expiry(_: object, **__: object) -> OfferExpiryResult:
        raise RuntimeError("database temporarily unavailable")

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(offer_expiry_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(offer_expiry_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(offer_expiry_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(
        offer_expiry_worker,
        "expire_due_offers",
        failing_expiry,
    )
    monkeypatch.setattr(offer_expiry_worker.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await offer_expiry_worker.main()

    assert not heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_requires_fresh_heartbeat_and_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Health succeeds only when liveness and PostgreSQL checks both succeed."""
    heartbeat_path = tmp_path / "offer-expiry.heartbeat"
    offer_expiry_worker.__dict__["_record_heartbeat"](heartbeat_path)

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        offer_expiry_worker_heartbeat_path=heartbeat_path,
        offer_expiry_worker_heartbeat_max_age_seconds=120,
    )

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        offer_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        offer_expiry_worker_health,
        "Database",
        _FakeDatabase,
    )

    await offer_expiry_worker_health.main()

    assert _FakeDatabase.instances[0].ping_called is True
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_rejects_stale_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stale worker heartbeat must fail container health checks."""
    heartbeat_path = tmp_path / "offer-expiry.heartbeat"
    offer_expiry_worker.__dict__["_record_heartbeat"](heartbeat_path)

    stale_time = time.time() - 121
    os.utime(heartbeat_path, (stale_time, stale_time))

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        offer_expiry_worker_heartbeat_path=heartbeat_path,
        offer_expiry_worker_heartbeat_max_age_seconds=120,
    )

    monkeypatch.setattr(
        offer_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="stale"):
        await offer_expiry_worker_health.main()


def test_worker_id_uses_configured_value() -> None:
    """An explicit worker ID supports deterministic operational tracing."""
    worker_id = offer_expiry_worker.__dict__["_worker_id"]
    assert (
        worker_id("production-offer-expiry-1")
        == "production-offer-expiry-1"
    )
