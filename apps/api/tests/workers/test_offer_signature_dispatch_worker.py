"""Runtime tests for the offer-signature dispatch worker."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.offer_signature_dispatch import OfferSignatureDispatchResult
from app.services.offer_signature_provider import OfferSignatureProvider
from app.services.outbox_worker import OutboxWorkerPolicy
from app.workers import offer_signature_dispatch_worker


class _FakeSessionContext:
    """Minimal async session context manager."""

    async def __aenter__(self) -> object:
        """Return a placeholder session for isolated runtime tests."""
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Perform no cleanup for the test placeholder."""
        return None


class _FakeDatabase:
    """Database replacement that records worker cleanup."""

    instances: list[_FakeDatabase] = []

    def __init__(self, *_: object, **__: object) -> None:
        self.disposed = False
        self.session_factory = _FakeSessionContext
        self.__class__.instances.append(self)

    async def dispose(self) -> None:
        """Record that the worker released database resources."""
        self.disposed = True


@dataclass
class _FakeLogger:
    """Capture structured log entries without emitting test output."""

    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **fields: object) -> None:
        """Capture an informational log event."""
        self.entries.append((event, fields))

    def exception(self, event: str, **fields: object) -> None:
        """Capture an exception log event."""
        self.entries.append((event, fields))


def _settings() -> Settings:
    """Build valid settings for an isolated local-worker test."""

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
        offer_signature_provider="local",
        offer_signature_dispatch_worker_id="signature-dispatch-test-worker",
        offer_signature_dispatch_worker_poll_interval_seconds=3,
        offer_signature_dispatch_worker_batch_size=7,
    )


@pytest.fixture(autouse=True)
def _reset_runtime_fakes() -> None:
    """Prevent fake instances leaking across tests."""
    _FakeDatabase.instances.clear()


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    logger: _FakeLogger,
) -> Mapping[str, OfferSignatureProvider]:
    """Replace process dependencies with deterministic test doubles."""

    providers: Mapping[str, OfferSignatureProvider] = {}

    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "configure_logging",
        lambda _: None,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "Database",
        _FakeDatabase,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "logger",
        logger,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "_build_providers",
        lambda _: providers,
    )

    return providers


@pytest.mark.asyncio
async def test_worker_dispatches_successfully_writes_heartbeat_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A successful dispatch cycle is healthy and releases resources on stop."""

    heartbeat_path = tmp_path / "signature-dispatch.heartbeat"
    settings = _settings().model_copy(
        update={
            "offer_signature_dispatch_worker_heartbeat_path": heartbeat_path,
        }
    )
    logger = _FakeLogger()
    providers = _patch_runtime(
        monkeypatch,
        settings=settings,
        logger=logger,
    )
    captured: dict[str, object] = {}
    calls = 0

    async def dispatch_once(
        _: object,
        *,
        worker_id: str,
        providers: Mapping[str, OfferSignatureProvider],
        policy: OutboxWorkerPolicy,
    ) -> OfferSignatureDispatchResult:
        nonlocal calls
        calls += 1

        captured["worker_id"] = worker_id
        captured["providers"] = providers
        captured["policy"] = policy

        if calls == 1:
            return OfferSignatureDispatchResult(
                claimed=1,
                processed=1,
                retried=0,
                dead_lettered=0,
            )

        raise asyncio.CancelledError()

    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "dispatch_offer_signature_requests",
        dispatch_once,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_dispatch_worker.main()

    assert heartbeat_path.exists()
    assert captured["worker_id"] == "signature-dispatch-test-worker"
    assert captured["providers"] is providers

    policy = captured["policy"]
    assert isinstance(policy, OutboxWorkerPolicy)
    assert policy.batch_size == 7

    assert _FakeDatabase.instances[0].disposed is True
    assert any(
        event == "offer_signature_dispatch_worker_cycle_complete"
        for event, _ in logger.entries
    )


@pytest.mark.asyncio
async def test_empty_worker_poll_heartbeats_then_waits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty poll remains healthy and waits for the configured interval."""

    heartbeat_path = tmp_path / "signature-dispatch.heartbeat"
    settings = _settings().model_copy(
        update={
            "offer_signature_dispatch_worker_heartbeat_path": heartbeat_path,
        }
    )
    logger = _FakeLogger()
    _patch_runtime(
        monkeypatch,
        settings=settings,
        logger=logger,
    )

    async def dispatch_empty(
        _: object,
        **__: object,
    ) -> OfferSignatureDispatchResult:
        return OfferSignatureDispatchResult(
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
        offer_signature_dispatch_worker,
        "dispatch_offer_signature_requests",
        dispatch_empty,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker.asyncio,
        "sleep",
        stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_dispatch_worker.main()

    assert heartbeat_path.exists()
    assert sleep_calls == [3]
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_fields"),
    [
        (
            OfferSignatureDispatchResult(
                claimed=1,
                processed=0,
                retried=1,
                dead_lettered=0,
            ),
            {
                "claimed": 1,
                "processed": 0,
                "retried": 1,
                "dead_lettered": 0,
            },
        ),
        (
            OfferSignatureDispatchResult(
                claimed=1,
                processed=0,
                retried=0,
                dead_lettered=1,
            ),
            {
                "claimed": 1,
                "processed": 0,
                "retried": 0,
                "dead_lettered": 1,
            },
        ),
    ],
)
async def test_worker_records_retry_and_terminal_dispatch_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    result: OfferSignatureDispatchResult,
    expected_fields: dict[str, int],
) -> None:
    """Retryable and terminal outcomes are surfaced safely in worker telemetry."""

    settings = _settings().model_copy(
        update={
            "offer_signature_dispatch_worker_heartbeat_path": (
                tmp_path / "signature-dispatch.heartbeat"
            ),
        }
    )
    logger = _FakeLogger()
    _patch_runtime(
        monkeypatch,
        settings=settings,
        logger=logger,
    )

    calls = 0

    async def dispatch_once(
        _: object,
        **__: object,
    ) -> OfferSignatureDispatchResult:
        nonlocal calls
        calls += 1

        if calls == 1:
            return result

        raise asyncio.CancelledError()

    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "dispatch_offer_signature_requests",
        dispatch_once,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_dispatch_worker.main()

    cycle_logs = [
        fields
        for event, fields in logger.entries
        if event == "offer_signature_dispatch_worker_cycle_complete"
    ]

    assert cycle_logs == [
        {
            "worker_id": "signature-dispatch-test-worker",
            **expected_fields,
        }
    ]
    assert _FakeDatabase.instances[0].disposed is True


@pytest.mark.asyncio
async def test_worker_retries_after_unexpected_cycle_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unexpected runtime failures are logged and retried without exiting."""

    settings = _settings().model_copy(
        update={
            "offer_signature_dispatch_worker_heartbeat_path": (
                tmp_path / "signature-dispatch.heartbeat"
            ),
            "offer_signature_dispatch_worker_poll_interval_seconds": 2,
        }
    )
    logger = _FakeLogger()
    _patch_runtime(
        monkeypatch,
        settings=settings,
        logger=logger,
    )

    attempts = 0
    sleep_calls: list[int | float] = []

    async def fail_once_then_stop(
        _: object,
        **__: object,
    ) -> OfferSignatureDispatchResult:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            raise RuntimeError("temporary worker failure")

        raise asyncio.CancelledError()

    async def record_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        offer_signature_dispatch_worker,
        "dispatch_offer_signature_requests",
        fail_once_then_stop,
    )
    monkeypatch.setattr(
        offer_signature_dispatch_worker.asyncio,
        "sleep",
        record_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await offer_signature_dispatch_worker.main()

    assert attempts == 2
    assert sleep_calls == [2]
    assert any(
        event == "offer_signature_dispatch_worker_cycle_failed"
        for event, _ in logger.entries
    )
    assert _FakeDatabase.instances[0].disposed is True
