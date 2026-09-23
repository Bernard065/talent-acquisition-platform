"""Unit tests for the offer-signature expiry worker and health check."""

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.offer_signature_expiry import OfferSignatureExpiryResult
from app.workers import (
    offer_signature_expiry_worker,
    offer_signature_expiry_worker_health,
)


@dataclass
class _WorkerSettings:
    """Minimum runtime settings consumed by the expiry worker."""

    database_url: str | None
    offer_signature_expiry_worker_poll_interval_seconds: int
    offer_signature_expiry_worker_batch_size: int
    offer_signature_expiry_worker_id: str | None
    offer_signature_expiry_worker_heartbeat_path: Path
    offer_signature_expiry_worker_heartbeat_max_age_seconds: int
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
    """Database replacement that tracks liveness and shutdown behavior."""

    instances: list["_FakeDatabase"] = []

    def __init__(self, _: str) -> None:
        self.disposed = False
        self.ping_called = False
        _FakeDatabase.instances.append(self)

    def session_factory(self) -> _SessionContext:
        """Return a disposable fake database session."""
        return _SessionContext()

    async def dispose(self) -> None:
        """Record worker resource shutdown."""
        self.disposed = True

    async def ping(self) -> None:
        """Record a database health-check request."""
        self.ping_called = True


async def _cancel_sleep(_: float) -> None:
    """End the intentionally infinite polling loop after one observed wait."""
    raise asyncio.CancelledError


def _settings(heartbeat_path: Path) -> _WorkerSettings:
    """Create deterministic worker settings for one test."""
    return _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        offer_signature_expiry_worker_poll_interval_seconds=1,
        offer_signature_expiry_worker_batch_size=50,
        offer_signature_expiry_worker_id="signature-expiry-test-worker",
        offer_signature_expiry_worker_heartbeat_path=heartbeat_path,
        offer_signature_expiry_worker_heartbeat_max_age_seconds=120,
    )


@pytest.mark.asyncio
async def test_empty_cycle_records_heartbeat_waits_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty batch is healthy, waits, and disposes database resources."""
    heartbeat_path = tmp_path / "signature-expiry.heartbeat"
    calls: list[dict[str, object]] = []

    async def fake_expire_due_signature_requests(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> OfferSignatureExpiryResult:
        calls.append(
            {
                "batch_size": batch_size,
                "request_id": request_id,
            }
        )
        return OfferSignatureExpiryResult(
            expired_signature_request_ids=(),
        )

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "get_settings",
        lambda: _settings(heartbeat_path),
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "expire_due_offer_signature_requests",
        fake_expire_due_signature_requests,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_expiry_worker.main()

    assert calls == [
        {
            "batch_size": 50,
            "request_id": "signature-expiry-test-worker",
        }
    ]
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_successful_expiry_processes_next_batch_without_initial_wait(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-empty batch is processed immediately before the next idle poll."""
    heartbeat_path = tmp_path / "signature-expiry.heartbeat"
    calls = 0

    async def fake_expire_due_signature_requests(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> OfferSignatureExpiryResult:
        nonlocal calls
        calls += 1

        assert batch_size == 50
        assert request_id == "signature-expiry-test-worker"

        if calls == 1:
            return OfferSignatureExpiryResult(
                expired_signature_request_ids=(uuid4(),),
            )

        return OfferSignatureExpiryResult(
            expired_signature_request_ids=(),
        )

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "get_settings",
        lambda: _settings(heartbeat_path),
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "expire_due_offer_signature_requests",
        fake_expire_due_signature_requests,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_expiry_worker.main()

    assert calls == 2
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_database_failure_retries_without_false_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed cycle waits to retry but never reports false liveness."""
    heartbeat_path = tmp_path / "signature-expiry.heartbeat"

    async def failing_expiry(
        _: object,
        **__: object,
    ) -> OfferSignatureExpiryResult:
        raise RuntimeError("database temporarily unavailable")

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "get_settings",
        lambda: _settings(heartbeat_path),
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker,
        "expire_due_offer_signature_requests",
        failing_expiry,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_expiry_worker.main()

    assert not heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_requires_fresh_heartbeat_and_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A worker is healthy only with fresh liveness and PostgreSQL access."""
    heartbeat_path = tmp_path / "signature-expiry.heartbeat"
    offer_signature_expiry_worker.__dict__["_record_heartbeat"](
        heartbeat_path
    )

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        offer_signature_expiry_worker_heartbeat_path=heartbeat_path,
        offer_signature_expiry_worker_heartbeat_max_age_seconds=120,
    )

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        offer_signature_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        offer_signature_expiry_worker_health,
        "Database",
        _FakeDatabase,
    )

    await offer_signature_expiry_worker_health.main()

    assert _FakeDatabase.instances[0].ping_called is True
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_rejects_stale_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stale heartbeat fails the worker health check."""
    heartbeat_path = tmp_path / "signature-expiry.heartbeat"
    offer_signature_expiry_worker.__dict__["_record_heartbeat"](
        heartbeat_path
    )

    stale_time = time.time() - 121
    os.utime(heartbeat_path, (stale_time, stale_time))

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        offer_signature_expiry_worker_heartbeat_path=heartbeat_path,
        offer_signature_expiry_worker_heartbeat_max_age_seconds=120,
    )

    monkeypatch.setattr(
        offer_signature_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="stale"):
        await offer_signature_expiry_worker_health.main()


def test_worker_id_uses_configured_value() -> None:
    """A configured worker ID supports deterministic operational tracing."""
    assert (
        offer_signature_expiry_worker.worker_id(
            "production-signature-expiry-1"
        )
        == "production-signature-expiry-1"
    )
