"""Runtime tests for the Google Calendar synchronization worker."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_sync_worker import CalendarSyncWorkerResult
from app.workers import calendar_sync_worker


@dataclass
class FakeVault:
    """In-memory Infisical substitute used by worker runtime tests."""

    secrets: Mapping[str, SecretStr]
    requested_secret_names: list[str] = field(default_factory=list)

    async def read_runtime_secret(self, *, secret_name: str) -> SecretStr:
        """Return one configured test secret without external I/O."""
        self.requested_secret_names.append(secret_name)
        return self.secrets[secret_name]


class FakeHttpClient:
    """Records client construction and shutdown without network access."""

    instances: list["FakeHttpClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.__class__.instances.append(self)

    async def aclose(self) -> None:
        """Record shutdown ownership."""
        self.closed = True


class FakeSessionContext:
    """Minimal async database session context manager."""

    async def __aenter__(self) -> object:
        """Provide an unused placeholder session."""
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Perform no external cleanup."""


class FakeDatabase:
    """Database substitute that records disposal."""

    instances: list["FakeDatabase"] = []

    def __init__(self, *_: object, **__: object) -> None:
        self.disposed = False
        self.session_factory = FakeSessionContext
        self.__class__.instances.append(self)

    async def dispose(self) -> None:
        """Record disposal."""
        self.disposed = True


@dataclass
class FakeLogger:
    """Capture structured log fields without emitting sensitive test data."""

    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **fields: object) -> None:
        """Record an informational structured event."""
        self.entries.append((event, fields))

    def exception(self, event: str, **fields: object) -> None:
        """Record a failure structured event."""
        self.entries.append((event, fields))


def _settings() -> Settings:
    """Return valid settings for an isolated Google worker runtime."""
    client_id_secret_name = "tap_google_calendar_client_id"  # noqa: S105
    client_secret_secret_name = "tap_google_calendar_client_secret"  # noqa: S105

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
        calendar_oauth_provider="google",
        google_calendar_oauth_client_id_secret_name=client_id_secret_name,
        google_calendar_oauth_client_secret_secret_name=client_secret_secret_name,
        calendar_sync_worker_batch_size=7,
        calendar_sync_worker_poll_interval_seconds=1,
        calendar_sync_worker_id="calendar-sync-test-worker",
    )


def _vault() -> FakeVault:
    """Return the two static Google OAuth configuration secrets."""
    return FakeVault(
        secrets={
            "tap_google_calendar_client_id": SecretStr("google-client-id"),
            "tap_google_calendar_client_secret": SecretStr(
                "google-client-secret"
            ),
        }
    )


@pytest.fixture(autouse=True)
def _reset_runtime_fakes() -> None:
    """Prevent state leaking between tests."""
    FakeDatabase.instances.clear()
    FakeHttpClient.instances.clear()


def _patch_worker_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    vault: FakeVault,
    logger: FakeLogger,
) -> None:
    """Replace all external worker dependencies with deterministic fakes."""

    async def create_vault(**_: object) -> FakeVault:
        return vault

    monkeypatch.setattr(
        calendar_sync_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        calendar_sync_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        calendar_sync_worker,
        "Database",
        FakeDatabase,
    )
    monkeypatch.setattr(
        calendar_sync_worker,
        "logger",
        logger,
    )
    monkeypatch.setattr(
        calendar_sync_worker.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        calendar_sync_worker.httpx,
        "AsyncClient",
        FakeHttpClient,
    )


@pytest.mark.asyncio
async def test_worker_builds_google_runtime_processes_cycle_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The worker owns its runtime resources and passes bounded dependencies."""
    settings = _settings().model_copy(
        update={
            "calendar_sync_worker_heartbeat_path": (
                tmp_path / "calendar-worker.heartbeat"
            ),
        }
    )
    vault = _vault()
    logger = FakeLogger()
    captured: dict[str, object] = {}

    _patch_worker_runtime(
        monkeypatch,
        settings=settings,
        vault=vault,
        logger=logger,
    )

    async def process_once(
        _: object,
        *,
        worker_id: str,
        credential_resolver: object,
        providers: Mapping[CalendarProvider, object],
        policy: object,
    ) -> CalendarSyncWorkerResult:
        captured["worker_id"] = worker_id
        captured["credential_resolver"] = credential_resolver
        captured["providers"] = providers
        captured["policy"] = policy

        if captured.get("processed"):
            raise asyncio.CancelledError()

        captured["processed"] = True
        return CalendarSyncWorkerResult(
            claimed=1,
            processed=1,
            retried=0,
            dead_lettered=0,
        )

    monkeypatch.setattr(
        calendar_sync_worker,
        "process_interview_calendar_sync_events",
        process_once,
    )

    with pytest.raises(asyncio.CancelledError):
        await calendar_sync_worker.main()

    assert captured["worker_id"] == "calendar-sync-test-worker"
    assert captured["credential_resolver"] is vault

    providers = captured["providers"]
    assert isinstance(providers, Mapping)
    assert set(providers) == {CalendarProvider.GOOGLE}

    assert vault.requested_secret_names == [
        "tap_google_calendar_client_id",
        "tap_google_calendar_client_secret",
    ]
    assert len(FakeHttpClient.instances) == 1
    assert FakeHttpClient.instances[0].closed is True
    assert len(FakeDatabase.instances) == 1
    assert FakeDatabase.instances[0].disposed is True
    assert settings.calendar_sync_worker_heartbeat_path.exists()

    logged_values = str(logger.entries)
    assert "google-client-secret" not in logged_values
    assert "test-infisical-secret" not in logged_values


@pytest.mark.asyncio
async def test_worker_heartbeats_and_waits_after_empty_poll(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty outbox poll writes a heartbeat before waiting."""
    settings = _settings().model_copy(
        update={
            "calendar_sync_worker_heartbeat_path": (
                tmp_path / "calendar-worker.heartbeat"
            ),
            "calendar_sync_worker_poll_interval_seconds": 3,
        }
    )
    logger = FakeLogger()
    _patch_worker_runtime(
        monkeypatch,
        settings=settings,
        vault=_vault(),
        logger=logger,
    )

    async def process_empty(
        _: object,
        **__: object,
    ) -> CalendarSyncWorkerResult:
        return CalendarSyncWorkerResult(
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
        calendar_sync_worker,
        "process_interview_calendar_sync_events",
        process_empty,
    )
    monkeypatch.setattr(
        calendar_sync_worker.asyncio,
        "sleep",
        stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await calendar_sync_worker.main()

    assert settings.calendar_sync_worker_heartbeat_path.exists()
    assert sleep_calls == [3]
    assert FakeHttpClient.instances[0].closed is True
    assert FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_worker_retries_after_temporary_cycle_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A temporary worker failure does not terminate the process."""
    settings = _settings().model_copy(
        update={
            "calendar_sync_worker_heartbeat_path": (
                tmp_path / "calendar-worker.heartbeat"
            ),
            "calendar_sync_worker_poll_interval_seconds": 2,
        }
    )
    logger = FakeLogger()
    _patch_worker_runtime(
        monkeypatch,
        settings=settings,
        vault=_vault(),
        logger=logger,
    )

    attempt_count = 0
    sleep_calls: list[int | float] = []

    async def process_with_one_failure(
        _: object,
        **__: object,
    ) -> CalendarSyncWorkerResult:
        nonlocal attempt_count
        attempt_count += 1

        if attempt_count == 1:
            raise RuntimeError("temporary test failure")

        raise asyncio.CancelledError()

    async def record_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        calendar_sync_worker,
        "process_interview_calendar_sync_events",
        process_with_one_failure,
    )
    monkeypatch.setattr(
        calendar_sync_worker.asyncio,
        "sleep",
        record_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await calendar_sync_worker.main()

    assert attempt_count == 2
    assert sleep_calls == [2]
    assert any(
        event == "calendar_sync_worker_cycle_failed"
        for event, _ in logger.entries
    )

    logged_values = str(logger.entries)
    assert "google-client-secret" not in logged_values
    assert "test-infisical-secret" not in logged_values


@pytest.mark.asyncio
async def test_google_runtime_fails_closed_when_calendar_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disabled calendar integration never initializes external clients."""
    settings = _settings().model_copy(
        update={
            "calendar_oauth_provider": "none",
            "credential_vault_provider": "none",
        }
    )
    vault_factory_called = False

    async def create_vault(**_: object) -> FakeVault:
        nonlocal vault_factory_called
        vault_factory_called = True
        return _vault()

    monkeypatch.setattr(
        calendar_sync_worker.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        calendar_sync_worker.httpx,
        "AsyncClient",
        FakeHttpClient,
    )

    with pytest.raises(
        RuntimeError,
        match="CALENDAR_OAUTH_PROVIDER=google",
    ):
        await calendar_sync_worker._build_google_runtime(settings)  # pylint: disable=protected-access

    assert vault_factory_called is False
    assert not FakeHttpClient.instances
