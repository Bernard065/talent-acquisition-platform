"""Unit tests for job-board dispatch worker lifecycle and health checks."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.job_board_dispatch import JobBoardDispatchResult
from app.workers import (
    job_board_dispatch_worker,
    job_board_dispatch_worker_health,
)


@dataclass
class _WorkerSettings:
    """Only the settings consumed by the worker runtime."""

    database_url: str | None
    app_env: str
    job_board_provider: str
    job_board_dispatch_worker_poll_interval_seconds: int
    job_board_dispatch_worker_batch_size: int
    job_board_dispatch_worker_id: str | None
    job_board_dispatch_worker_heartbeat_path: Path
    job_board_dispatch_worker_heartbeat_max_age_seconds: int
    job_board_dispatch_visibility_timeout_seconds: int = 300
    log_level: str = "INFO"


class _SessionContext:
    """Minimal async database-session context manager."""

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
    """Database substitute that tracks health and shutdown behavior."""

    instances: list["_FakeDatabase"] = []

    def __init__(self, _: str) -> None:
        self.disposed = False
        self.ping_called = False
        self.__class__.instances.append(self)

    def session_factory(self) -> _SessionContext:
        return _SessionContext()

    async def dispose(self) -> None:
        self.disposed = True

    async def ping(self) -> None:
        self.ping_called = True


async def _cancel_sleep(_: float) -> None:
    """Stop an infinite poll loop after it reaches its normal wait point."""
    raise asyncio.CancelledError


def _settings(path: Path, **overrides: object) -> _WorkerSettings:
    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://worker-test",
        "app_env": "local",
        "job_board_provider": "local",
        "job_board_dispatch_worker_poll_interval_seconds": 1,
        "job_board_dispatch_worker_batch_size": 25,
        "job_board_dispatch_worker_id": "job-board-worker-test",
        "job_board_dispatch_worker_heartbeat_path": path,
        "job_board_dispatch_worker_heartbeat_max_age_seconds": 90,
    }
    values.update(overrides)
    return _WorkerSettings(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_poll_writes_heartbeat_and_disposes_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "nested" / "job-board-worker.heartbeat"
    settings = _settings(heartbeat)
    results: list[dict[str, object]] = []

    async def fake_dispatch(
        _: object,
        *,
        worker_id: str,
        providers: object,
        policy: object,
    ) -> JobBoardDispatchResult:
        results.append(
            {
                "worker_id": worker_id,
                "providers": providers,
                "policy": policy,
            }
        )
        return JobBoardDispatchResult(0, 0, 0, 0)

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(job_board_dispatch_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(job_board_dispatch_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(job_board_dispatch_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(
        job_board_dispatch_worker,
        "dispatch_job_board_events",
        fake_dispatch,
    )
    monkeypatch.setattr(job_board_dispatch_worker.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await job_board_dispatch_worker.main()

    assert len(results) == 1
    assert results[0]["worker_id"] == "job-board-worker-test"
    assert heartbeat.exists()
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_transient_poll_failure_retries_and_later_records_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "job-board-worker.heartbeat"
    settings = _settings(heartbeat)
    calls = 0
    sleep_calls = 0

    async def fake_dispatch(
        *_: object,
        **__: object,
    ) -> JobBoardDispatchResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database outage must not escape worker loop")
        return JobBoardDispatchResult(0, 0, 0, 0)

    async def stop_after_second_cycle(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError

    _FakeDatabase.instances.clear()
    monkeypatch.setattr(job_board_dispatch_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(job_board_dispatch_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(job_board_dispatch_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(
        job_board_dispatch_worker,
        "dispatch_job_board_events",
        fake_dispatch,
    )
    monkeypatch.setattr(
        job_board_dispatch_worker.asyncio,
        "sleep",
        stop_after_second_cycle,
    )

    with pytest.raises(asyncio.CancelledError):
        await job_board_dispatch_worker.main()

    assert calls == 2
    assert heartbeat.exists()
    assert _FakeDatabase.instances[0].disposed is True


def test_provider_configuration_is_explicit_and_local_only(
    tmp_path: Path,
) -> None:
    """Do not start silently without a provider or allow the fake in production."""
    with pytest.raises(RuntimeError, match="JOB_BOARD_PROVIDER must be configured"):
        job_board_dispatch_worker._build_providers(
            _settings(tmp_path / "heartbeat", job_board_provider="none")  # type: ignore[arg-type]
        )

    with pytest.raises(RuntimeError, match="permitted only in local and test"):
        job_board_dispatch_worker._build_providers(
            _settings(
                tmp_path / "heartbeat",
                app_env="production",
                job_board_provider="local",
            )  # type: ignore[arg-type]
        )

    providers = job_board_dispatch_worker._build_providers(
        _settings(tmp_path / "heartbeat")  # type: ignore[arg-type]
    )
    assert tuple(providers) == ("local",)


@pytest.mark.asyncio
async def test_health_check_requires_fresh_heartbeat_and_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "job-board-worker.heartbeat"
    heartbeat.touch()
    settings = _settings(heartbeat)
    _FakeDatabase.instances.clear()
    monkeypatch.setattr(job_board_dispatch_worker_health, "get_settings", lambda: settings)
    monkeypatch.setattr(job_board_dispatch_worker_health, "Database", _FakeDatabase)

    await job_board_dispatch_worker_health.main()
    assert _FakeDatabase.instances[0].ping_called is True
    assert _FakeDatabase.instances[0].disposed is True

    heartbeat.unlink()
    with pytest.raises(RuntimeError, match="heartbeat is missing"):
        await job_board_dispatch_worker_health.main()


@pytest.mark.asyncio
async def test_health_check_rejects_stale_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "job-board-worker.heartbeat"
    heartbeat.touch()
    settings = _settings(
        heartbeat,
        job_board_dispatch_worker_heartbeat_max_age_seconds=10,
    )
    old_time = heartbeat.stat().st_mtime - 30
    os.utime(heartbeat, (old_time, old_time))
    monkeypatch.setattr(job_board_dispatch_worker_health, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="heartbeat is stale"):
        await job_board_dispatch_worker_health.main()
