"""Runtime tests for the HRIS handoff worker."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domains.hris.enums import HrisProvider
from app.services.hris_handoff_dispatch import HrisHandoffDispatchResult
from app.services.hris_provider import HrisProviderAdapter
from app.services.outbox_worker import OutboxWorkerPolicy
from app.workers import hris_handoff_worker


class _FakeHttpClient:
    """HTTP-client substitute that records graceful shutdown."""

    instances: list[_FakeHttpClient] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.__class__.instances.append(self)

    async def aclose(self) -> None:
        """Record resource shutdown."""
        self.closed = True


class _FakeSessionContext:
    """Minimal async database-session context manager."""

    async def __aenter__(self) -> object:
        """Return a placeholder database session."""
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Perform no work for the fake session."""
        return None


class _FakeDatabase:
    """Database substitute that records disposal."""

    instances: list[_FakeDatabase] = []

    def __init__(self, *_: object, **__: object) -> None:
        self.disposed = False
        self.session_factory = _FakeSessionContext
        self.__class__.instances.append(self)

    async def dispose(self) -> None:
        """Record cleanup during worker shutdown."""
        self.disposed = True


@dataclass
class _FakeVault:
    """Minimal in-memory substitute for the HRIS Infisical vault."""


@dataclass
class _FakeLogger:
    """Capture structured worker logs without emitting output."""

    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **fields: object) -> None:
        """Record informational telemetry."""
        self.entries.append((event, fields))

    def exception(self, event: str, **fields: object) -> None:
        """Record classified cycle failures."""
        self.entries.append((event, fields))


def _settings() -> Settings:
    """Build valid settings for an isolated HRIS worker runtime."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url="postgresql+asyncpg://tap:tap@127.0.0.1:5432/tap_test",
        redis_url="redis://127.0.0.1:6379/0",
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
        credential_vault_provider="infisical",
        infisical_client_id="test-machine-identity",
        infisical_client_secret=SecretStr("test-infisical-secret"),
        infisical_project_id="test-project",
        infisical_environment="test",
        hris_handoff_provider="bamboohr",
        hris_handoff_worker_id="hris-handoff-test-worker",
        hris_handoff_worker_poll_interval_seconds=3,
        hris_handoff_worker_batch_size=7,
    )


@pytest.fixture(autouse=True)
def _reset_runtime_fakes() -> None:
    """Prevent fake state from leaking between tests."""
    _FakeDatabase.instances.clear()
    _FakeHttpClient.instances.clear()


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    vault: _FakeVault,
    logger: _FakeLogger,
) -> None:
    """Replace external process dependencies with deterministic fakes."""

    async def create_vault(**_: object) -> _FakeVault:
        return vault

    monkeypatch.setattr(
        hris_handoff_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        hris_handoff_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        hris_handoff_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        hris_handoff_worker,
        "logger",
        logger,
    )
    monkeypatch.setattr(
        hris_handoff_worker.InfisicalHrisCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        hris_handoff_worker.httpx,
        "AsyncClient",
        _FakeHttpClient,
    )


@pytest.mark.asyncio
async def test_worker_processes_successful_cycle_heartbeats_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The worker owns its database and HTTP resources through shutdown."""
    heartbeat_path = tmp_path / "hris-handoff.heartbeat"
    settings = _settings().model_copy(
        update={
            "hris_handoff_worker_heartbeat_path": heartbeat_path,
        }
    )
    vault = _FakeVault()
    logger = _FakeLogger()
    captured: dict[str, object] = {}
    calls = 0

    _patch_runtime(
        monkeypatch,
        settings=settings,
        vault=vault,
        logger=logger,
    )

    async def process_once(
        _: object,
        *,
        worker_id: str,
        credential_vault: object,
        providers: Mapping[HrisProvider, HrisProviderAdapter],
        policy: OutboxWorkerPolicy,
    ) -> HrisHandoffDispatchResult:
        nonlocal calls
        calls += 1

        captured["worker_id"] = worker_id
        captured["credential_vault"] = credential_vault
        captured["providers"] = providers
        captured["policy"] = policy

        if calls == 1:
            return HrisHandoffDispatchResult(
                claimed=1,
                processed=1,
                retried=0,
                dead_lettered=0,
            )

        raise asyncio.CancelledError()

    monkeypatch.setattr(
        hris_handoff_worker,
        "dispatch_hris_handoff_events",
        process_once,
    )

    with pytest.raises(asyncio.CancelledError):
        await hris_handoff_worker.main()

    assert heartbeat_path.exists()
    assert captured["worker_id"] == "hris-handoff-test-worker"
    assert captured["credential_vault"] is vault

    providers = captured["providers"]
    assert isinstance(providers, Mapping)
    assert set(providers) == {HrisProvider.BAMBOOHR}

    policy = captured["policy"]
    assert isinstance(policy, OutboxWorkerPolicy)
    assert policy.batch_size == 7

    assert len(_FakeHttpClient.instances) == 1
    assert _FakeHttpClient.instances[0].closed is True
    assert len(_FakeDatabase.instances) == 1
    assert _FakeDatabase.instances[0].disposed is True

    assert any(
        event == "hris_handoff_worker_cycle_complete"
        for event, _ in logger.entries
    )

    logged_values = str(logger.entries)
    assert "test-infisical-secret" not in logged_values


@pytest.mark.asyncio
async def test_empty_poll_heartbeats_then_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty poll remains healthy and waits for the configured interval."""
    heartbeat_path = tmp_path / "hris-handoff.heartbeat"
    settings = _settings().model_copy(
        update={
            "hris_handoff_worker_heartbeat_path": heartbeat_path,
        }
    )
    logger = _FakeLogger()

    _patch_runtime(
        monkeypatch,
        settings=settings,
        vault=_FakeVault(),
        logger=logger,
    )

    async def process_empty(
        _: object,
        **__: object,
    ) -> HrisHandoffDispatchResult:
        return HrisHandoffDispatchResult(
            claimed=0,
            processed=0,
            retried=0,
            dead_lettered=0,
        )

    sleep_calls: list[int | float] = []

    async def stop_after_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        hris_handoff_worker,
        "dispatch_hris_handoff_events",
        process_empty,
    )
    monkeypatch.setattr(
        hris_handoff_worker.asyncio,
        "sleep",
        stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await hris_handoff_worker.main()

    assert heartbeat_path.exists()
    assert sleep_calls == [3]
    assert _FakeHttpClient.instances[0].closed is True
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_worker_retries_after_temporary_cycle_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Transient cycle failures are logged and retried without process exit."""
    heartbeat_path = tmp_path / "hris-handoff.heartbeat"
    settings = _settings().model_copy(
        update={
            "hris_handoff_worker_heartbeat_path": heartbeat_path,
            "hris_handoff_worker_poll_interval_seconds": 2,
        }
    )
    logger = _FakeLogger()
    attempts = 0
    sleep_calls: list[int | float] = []

    _patch_runtime(
        monkeypatch,
        settings=settings,
        vault=_FakeVault(),
        logger=logger,
    )

    async def fail_once_then_stop(
        _: object,
        **__: object,
    ) -> HrisHandoffDispatchResult:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            raise RuntimeError("temporary worker failure")

        raise asyncio.CancelledError()

    async def record_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        hris_handoff_worker,
        "dispatch_hris_handoff_events",
        fail_once_then_stop,
    )
    monkeypatch.setattr(
        hris_handoff_worker.asyncio,
        "sleep",
        record_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await hris_handoff_worker.main()

    assert attempts == 2
    assert sleep_calls == [2]
    assert _FakeHttpClient.instances[0].closed is True
    assert _FakeDatabase.instances[0].disposed is True
    assert any(
        event == "hris_handoff_worker_cycle_failed"
        for event, _ in logger.entries
    )


@pytest.mark.asyncio
async def test_runtime_fails_closed_when_hris_provider_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not initialize Infisical or HTTP resources for disabled HRIS."""
    settings = _settings().model_copy(
        update={
            "hris_handoff_provider": "none",
            "credential_vault_provider": "none",
        }
    )
    vault_factory_called = False

    async def create_vault(**_: object) -> _FakeVault:
        nonlocal vault_factory_called
        vault_factory_called = True
        return _FakeVault()

    monkeypatch.setattr(
        hris_handoff_worker.InfisicalHrisCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        hris_handoff_worker.httpx,
        "AsyncClient",
        _FakeHttpClient,
    )

    with pytest.raises(
        RuntimeError,
        match="HRIS_HANDOFF_PROVIDER=bamboohr",
    ):
        await hris_handoff_worker._build_runtime(settings)  # pylint: disable=protected-access

    assert vault_factory_called is False
    assert not _FakeHttpClient.instances


@pytest.mark.asyncio
async def test_runtime_fails_closed_without_infisical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BambooHR worker cannot start without the configured secret vault."""
    settings = _settings().model_copy(
        update={
            "credential_vault_provider": "none",
        }
    )
    vault_factory_called = False

    async def create_vault(**_: object) -> _FakeVault:
        nonlocal vault_factory_called
        vault_factory_called = True
        return _FakeVault()

    monkeypatch.setattr(
        hris_handoff_worker.InfisicalHrisCredentialVault,
        "from_universal_auth",
        create_vault,
    )

    with pytest.raises(
        RuntimeError,
        match="CREDENTIAL_VAULT_PROVIDER=infisical",
    ):
        await hris_handoff_worker._build_runtime(settings)  # pylint: disable=protected-access

    assert vault_factory_called is False
