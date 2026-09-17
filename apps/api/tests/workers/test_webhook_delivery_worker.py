"""Runtime tests for the webhook delivery worker process."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.webhook_delivery_worker import WebhookDeliveryProcessResult
from app.workers import webhook_delivery_worker


class _FakeSessionContext:
    """Minimal async session context manager."""

    async def __aenter__(self) -> object:
        """Return a placeholder session object for the fake runtime."""
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Ignore context-manager cleanup exceptions in the fake runtime."""
        return None


class _FakeDatabase:
    """Database substitute that records lifecycle cleanup."""

    instances: list[_FakeDatabase] = []

    def __init__(self, *_: object, **__: object) -> None:
        self.disposed = False
        self.session_factory = _FakeSessionContext
        self.__class__.instances.append(self)

    async def dispose(self) -> None:
        """Mark the fake database as disposed during shutdown."""
        self.disposed = True


@dataclass
class _FakeDispatcher:
    """Runtime dispatcher substitute that records shutdown."""

    closed: bool = False

    async def aclose(self) -> None:
        """Mark the fake dispatcher as closed during shutdown."""
        self.closed = True


@dataclass
class _FakeLogger:
    """Capture structured worker events without emitting output."""

    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **fields: object) -> None:
        """Record an informational worker event."""
        self.entries.append((event, fields))

    def error(self, event: str, **fields: object) -> None:
        """Record an error worker event."""
        self.entries.append((event, fields))


def _settings() -> Settings:
    """Build valid local settings for an isolated worker runtime test."""
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
        webhook_allowed_hosts=["hooks.partner.example.test"],
        webhook_delivery_worker_id="webhook-worker-test",
        webhook_delivery_worker_poll_interval_seconds=3,
        webhook_delivery_worker_batch_size=7,
    )


@pytest.fixture(autouse=True)
def _reset_runtime_fakes() -> None:
    """Prevent fake state from leaking between tests."""
    _FakeDatabase.instances.clear()


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    dispatcher: _FakeDispatcher,
    logger: _FakeLogger,
) -> None:
    """Replace runtime dependencies with deterministic local fakes."""

    async def build_dispatcher(_: Settings) -> _FakeDispatcher:
        return dispatcher

    monkeypatch.setattr(webhook_delivery_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(webhook_delivery_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(webhook_delivery_worker, "Database", _FakeDatabase)
    monkeypatch.setattr(webhook_delivery_worker, "logger", logger)
    monkeypatch.setattr(
        webhook_delivery_worker,
        "_build_dispatcher",
        build_dispatcher,
    )


@pytest.mark.asyncio
async def test_worker_records_heartbeat_after_successful_cycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A completed poll writes a heartbeat before the next cycle."""
    heartbeat_path = tmp_path / "webhook-delivery.heartbeat"
    settings = _settings().model_copy(
        update={"webhook_delivery_worker_heartbeat_path": heartbeat_path}
    )
    dispatcher = _FakeDispatcher()
    logger = _FakeLogger()
    _patch_runtime(
        monkeypatch,
        settings=settings,
        dispatcher=dispatcher,
        logger=logger,
    )

    calls = 0

    async def process_once(_: object, **__: object) -> WebhookDeliveryProcessResult:
        nonlocal calls
        calls += 1

        if calls == 1:
            return WebhookDeliveryProcessResult(
                claimed=1,
                delivered=1,
                retried=0,
                failed=0,
                disabled=0,
            )

        raise asyncio.CancelledError()

    monkeypatch.setattr(
        webhook_delivery_worker,
        "process_pending_webhook_deliveries",
        process_once,
    )

    with pytest.raises(asyncio.CancelledError):
        await webhook_delivery_worker.main()

    assert heartbeat_path.exists()
    assert dispatcher.closed is True
    assert _FakeDatabase.instances[0].disposed is True
    assert any(
        event == "webhook_delivery_worker_cycle_complete"
        for event, _ in logger.entries
    )


@pytest.mark.asyncio
async def test_empty_worker_poll_heartbeats_then_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty poll remains healthy and waits for the configured interval."""
    heartbeat_path = tmp_path / "webhook-delivery.heartbeat"
    settings = _settings().model_copy(
        update={"webhook_delivery_worker_heartbeat_path": heartbeat_path}
    )
    dispatcher = _FakeDispatcher()
    logger = _FakeLogger()
    _patch_runtime(
        monkeypatch,
        settings=settings,
        dispatcher=dispatcher,
        logger=logger,
    )

    async def process_empty(_: object, **__: object) -> WebhookDeliveryProcessResult:
        return WebhookDeliveryProcessResult(
            claimed=0,
            delivered=0,
            retried=0,
            failed=0,
            disabled=0,
        )

    sleep_calls: list[int | float] = []

    async def stop_after_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        webhook_delivery_worker,
        "process_pending_webhook_deliveries",
        process_empty,
    )
    monkeypatch.setattr(
        webhook_delivery_worker.asyncio,
        "sleep",
        stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await webhook_delivery_worker.main()

    assert heartbeat_path.exists()
    assert sleep_calls == [3]
    assert dispatcher.closed is True
    assert _FakeDatabase.instances[0].disposed is True
