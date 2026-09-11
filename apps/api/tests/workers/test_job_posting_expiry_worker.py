"""Unit tests for the job-posting expiry worker and health check."""

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.job_posting_expiry import JobPostingExpiryResult
from app.workers import (
    job_posting_expiry_worker,
    job_posting_expiry_worker_health,
)


@dataclass
class _WorkerSettings:
    """Minimum settings surface used by the expiry worker."""

    database_url: str | None
    job_posting_expiry_worker_poll_interval_seconds: int
    job_posting_expiry_worker_batch_size: int
    job_posting_expiry_worker_id: str | None
    job_posting_expiry_worker_heartbeat_path: Path
    job_posting_expiry_worker_heartbeat_max_age_seconds: int
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
        """Return a disposable fake database session."""
        return _SessionContext()

    async def dispose(self) -> None:
        """Record worker shutdown cleanup."""
        self.disposed = True

    async def ping(self) -> None:
        """Record a successful database health check."""
        self.ping_called = True


async def _cancel_sleep(_: float) -> None:
    """End the intentionally infinite worker loop after one observed wait."""
    raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_empty_cycle_records_heartbeat_and_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty batch is healthy and waits before polling again."""
    heartbeat_path = tmp_path / "job-posting-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        job_posting_expiry_worker_poll_interval_seconds=1,
        job_posting_expiry_worker_batch_size=50,
        job_posting_expiry_worker_id="job-posting-expiry-test-worker",
        job_posting_expiry_worker_heartbeat_path=heartbeat_path,
        job_posting_expiry_worker_heartbeat_max_age_seconds=180,
    )
    calls: list[dict[str, object]] = []

    async def fake_expire_due_job_postings(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> JobPostingExpiryResult:
        calls.append(
            {
                "batch_size": batch_size,
                "request_id": request_id,
            }
        )
        return JobPostingExpiryResult(expired_job_posting_ids=())

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "expire_due_job_postings",
        fake_expire_due_job_postings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await job_posting_expiry_worker.main()

    assert calls == [
        {
            "batch_size": 50,
            "request_id": "job-posting-expiry-test-worker",
        }
    ]
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_successful_expiry_batch_runs_again_without_waiting_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-empty batch starts the next cycle immediately."""
    heartbeat_path = tmp_path / "job-posting-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        job_posting_expiry_worker_poll_interval_seconds=1,
        job_posting_expiry_worker_batch_size=25,
        job_posting_expiry_worker_id="job-posting-expiry-test-worker",
        job_posting_expiry_worker_heartbeat_path=heartbeat_path,
        job_posting_expiry_worker_heartbeat_max_age_seconds=180,
    )
    calls = 0

    async def fake_expire_due_job_postings(
        _: object,
        *,
        batch_size: int,
        request_id: str,
    ) -> JobPostingExpiryResult:
        nonlocal calls
        calls += 1

        assert batch_size == 25
        assert request_id == "job-posting-expiry-test-worker"

        if calls == 1:
            return JobPostingExpiryResult(
                expired_job_posting_ids=(uuid4(),)
            )

        raise RuntimeError("temporary database failure")

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "expire_due_job_postings",
        fake_expire_due_job_postings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await job_posting_expiry_worker.main()

    assert calls == 2
    assert heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_temporary_failure_does_not_write_false_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed expiry cycle waits for retry without claiming healthy work."""
    heartbeat_path = tmp_path / "job-posting-expiry.heartbeat"
    settings = _WorkerSettings(
        database_url="postgresql+asyncpg://test",
        job_posting_expiry_worker_poll_interval_seconds=1,
        job_posting_expiry_worker_batch_size=50,
        job_posting_expiry_worker_id="job-posting-expiry-test-worker",
        job_posting_expiry_worker_heartbeat_path=heartbeat_path,
        job_posting_expiry_worker_heartbeat_max_age_seconds=180,
    )

    async def failing_expiry(
        _: object,
        **__: object,
    ) -> JobPostingExpiryResult:
        raise RuntimeError("database temporarily unavailable")

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker,
        "expire_due_job_postings",
        failing_expiry,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker.asyncio,
        "sleep",
        _cancel_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await job_posting_expiry_worker.main()

    assert not heartbeat_path.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_requires_fresh_heartbeat_and_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Health succeeds only with fresh liveness and PostgreSQL availability."""
    heartbeat_path = tmp_path / "job-posting-expiry.heartbeat"
    heartbeat_path.touch()

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        job_posting_expiry_worker_heartbeat_path=heartbeat_path,
        job_posting_expiry_worker_heartbeat_max_age_seconds=180,
    )

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(
        job_posting_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker_health,
        "Database",
        _FakeDatabase,
    )

    await job_posting_expiry_worker_health.main()

    assert _FakeDatabase.instances[0].ping_called is True
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_health_check_rejects_stale_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stale heartbeat must fail the container health check."""
    heartbeat_path = tmp_path / "job-posting-expiry.heartbeat"
    heartbeat_path.touch()

    stale_time = time.time() - 181
    os.utime(heartbeat_path, (stale_time, stale_time))

    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://test",
        job_posting_expiry_worker_heartbeat_path=heartbeat_path,
        job_posting_expiry_worker_heartbeat_max_age_seconds=180,
    )
    monkeypatch.setattr(
        job_posting_expiry_worker_health,
        "get_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="stale"):
        await job_posting_expiry_worker_health.main()


def test_worker_id_uses_configured_value() -> None:
    """An explicit worker ID supports deterministic operational tracing."""
    assert (
        job_posting_expiry_worker.worker_id(
            "production-job-posting-expiry-1"
        )
        == "production-job-posting-expiry-1"
    )
