"""Runtime tests for the notification email delivery process."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.email.resend_sender import ResendEmailSender
from app.services.email_sender import EmailMessage
from app.services.notification_intents import NotificationIntentWorkerResult
from app.workers import notification_worker


class FakeSessionContext:
    """Minimal async session context manager for the worker loop."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


class FakeDatabase:
    """Database lifecycle fake that records deterministic cleanup."""

    instances: list[FakeDatabase] = []

    def __init__(self, *_: object, **__: object) -> None:
        self.disposed = False
        self.session_factory = FakeSessionContext
        self.__class__.instances.append(self)

    async def dispose(self) -> None:
        self.disposed = True


class FakeHttpClient:
    """HTTP client fake used to validate startup and shutdown ownership."""

    instances: list[FakeHttpClient] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
    ) -> httpx.Response:
        self.requests.append((url, {"headers": headers, "json": json}))
        return httpx.Response(200, json={"id": "resend-email-id"})

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeVault:
    """Infisical substitute that exposes only the named runtime secret."""

    api_key: SecretStr = SecretStr("re_test_api_key_not_for_logs")
    requested_names: list[str] = field(default_factory=list)

    async def read_runtime_secret(self, *, secret_name: str) -> SecretStr:
        self.requested_names.append(secret_name)
        return self.api_key


@dataclass
class FakeLogger:
    """Capture structured worker events without emitting test secrets."""

    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, event: str, **fields: object) -> None:
        self.entries.append((event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.entries.append((event, fields))

    def exception(self, event: str, **fields: object) -> None:
        self.entries.append((event, fields))


class FakeSender:
    """Email port fake used to assert the worker passes its configured sender."""

    idempotency_retry_window: timedelta | None = timedelta(hours=23)

    async def send(self, message: EmailMessage) -> str:
        return f"fake:{message.idempotency_key}"


def _settings() -> Settings:
    """Create valid local worker settings without external dependencies."""
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
        notification_worker_id="notification-test-worker",
        notification_worker_batch_size=6,
        notification_worker_poll_interval_seconds=2,
    )


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    FakeDatabase.instances.clear()
    FakeHttpClient.instances.clear()


@pytest.mark.asyncio
async def test_builds_resend_sender_from_infisical_without_live_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the configured API-key secret is read and HTTP redirects are off."""
    settings = _settings().model_copy(
        update={
            "notification_email_provider": "resend",
            "notification_email_api_key_secret_name": "tap_resend_key",
            "notification_email_from_address": "notifications@example.com",
            "credential_vault_provider": "infisical",
            "infisical_client_id": "worker-client-id",
            "infisical_client_secret": SecretStr("infisical-client-secret"),
            "infisical_project_id": "project-id",
            "infisical_environment": "production",
        }
    )
    vault = FakeVault()
    auth_arguments: dict[str, object] = {}

    async def create_vault(**kwargs: object) -> FakeVault:
        auth_arguments.update(kwargs)
        return vault

    monkeypatch.setattr(
        notification_worker.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(notification_worker.httpx, "AsyncClient", FakeHttpClient)

    sender, http_client = await notification_worker._build_sender(settings)

    assert isinstance(sender, ResendEmailSender)
    assert http_client is FakeHttpClient.instances[0]
    assert vault.requested_names == ["tap_resend_key"]
    assert auth_arguments == {
        "project_id": "project-id",
        "environment_slug": "production",
        "client_id": "worker-client-id",
        "client_secret": "infisical-client-secret",
        "host": "https://app.infisical.com/",
    }
    client = FakeHttpClient.instances[0]
    assert client.kwargs["follow_redirects"] is False
    assert client.kwargs["timeout"].connect == 3.0

    provider_id = await sender.send(
        EmailMessage(
            notification_id=uuid4(),
            idempotency_key="e" * 64,
            recipient_email="user@example.test",
            subject="Safe notification",
            text_body="A workflow update is available.",
        )
    )

    assert provider_id == "resend-email-id"
    request_url, request = client.requests[0]
    assert request_url == "https://api.resend.com/emails"
    assert request["headers"]["Authorization"] == "Bearer re_test_api_key_not_for_logs"
    await http_client.aclose()
    assert client.closed is True


@pytest.mark.asyncio
async def test_build_sender_fails_closed_without_infisical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend is never started with an environment or placeholder API key."""
    settings = _settings().model_copy(
        update={
            "notification_email_provider": "resend",
            "notification_email_api_key_secret_name": "tap_resend_key",
            "notification_email_from_address": "notifications@example.com",
        }
    )
    vault_factory_called = False

    async def create_vault(**_: object) -> FakeVault:
        nonlocal vault_factory_called
        vault_factory_called = True
        return FakeVault()

    monkeypatch.setattr(
        notification_worker.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(notification_worker.httpx, "AsyncClient", FakeHttpClient)

    with pytest.raises(RuntimeError, match="CREDENTIAL_VAULT_PROVIDER=infisical"):
        await notification_worker._build_sender(settings)

    assert vault_factory_called is False
    assert FakeHttpClient.instances == []


@pytest.mark.asyncio
async def test_build_sender_sanitizes_infisical_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret provider error messages are not surfaced in startup exceptions."""
    settings = _settings().model_copy(
        update={
            "notification_email_provider": "resend",
            "notification_email_api_key_secret_name": "tap_resend_key",
            "notification_email_from_address": "notifications@example.com",
            "credential_vault_provider": "infisical",
            "infisical_client_id": "worker-client-id",
            "infisical_client_secret": SecretStr("infisical-client-secret"),
            "infisical_project_id": "project-id",
        }
    )

    async def create_vault(**_: object) -> FakeVault:
        raise RuntimeError("provider leaked secret re_private_value")

    monkeypatch.setattr(
        notification_worker.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )

    with pytest.raises(RuntimeError) as raised:
        await notification_worker._build_sender(settings)

    assert str(raised.value) == "Unable to initialize Resend credentials from Infisical."
    assert "re_private_value" not in str(raised.value)
    assert FakeHttpClient.instances == []


@pytest.mark.asyncio
async def test_worker_closes_http_and_database_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider client and DB engine are both released on cancellation."""
    settings = _settings().model_copy(
        update={
            "notification_worker_heartbeat_path": Path("notification.heartbeat"),
        }
    )
    logger = FakeLogger()
    sender = FakeSender()
    client = FakeHttpClient()
    captured_senders: list[object] = []
    intent_calls = 0

    monkeypatch.setattr(notification_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(notification_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(notification_worker, "Database", FakeDatabase)
    monkeypatch.setattr(notification_worker, "logger", logger)
    heartbeats: list[Path] = []
    monkeypatch.setattr(
        notification_worker,
        "_record_heartbeat",
        heartbeats.append,
    )

    async def build_sender(_: Settings) -> tuple[FakeSender, FakeHttpClient]:
        return sender, client

    async def process_intents(*_: object, **__: object) -> NotificationIntentWorkerResult:
        nonlocal intent_calls
        intent_calls += 1
        if intent_calls > 1:
            raise asyncio.CancelledError
        return NotificationIntentWorkerResult(claimed=1, processed=1, dead_lettered=0)

    async def process_notifications(
        _: object,
        *,
        sender: object,
        **__: object,
    ) -> int:
        captured_senders.append(sender)
        return 1

    monkeypatch.setattr(notification_worker, "_build_sender", build_sender)
    monkeypatch.setattr(
        notification_worker,
        "process_notification_request_events",
        process_intents,
    )
    monkeypatch.setattr(
        notification_worker,
        "process_pending_notifications",
        process_notifications,
    )

    with pytest.raises(asyncio.CancelledError):
        await notification_worker.main()

    assert captured_senders == [sender]
    assert heartbeats == [settings.notification_worker_heartbeat_path]
    assert client.closed is True
    assert FakeDatabase.instances[0].disposed is True
    assert any(event == "notification_worker_cycle_complete" for event, _ in logger.entries)


@pytest.mark.asyncio
async def test_empty_poll_heartbeats_then_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty queues remain healthy while the worker respects its poll interval."""
    settings = _settings().model_copy(
        update={
            "notification_worker_heartbeat_path": Path("notification.heartbeat"),
        }
    )
    logger = FakeLogger()
    sender = FakeSender()
    client = FakeHttpClient()
    sleep_calls: list[int | float] = []

    monkeypatch.setattr(notification_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(notification_worker, "configure_logging", lambda _: None)
    monkeypatch.setattr(notification_worker, "Database", FakeDatabase)
    monkeypatch.setattr(notification_worker, "logger", logger)
    heartbeats: list[Path] = []
    monkeypatch.setattr(
        notification_worker,
        "_record_heartbeat",
        heartbeats.append,
    )

    async def build_sender(_: Settings) -> tuple[FakeSender, FakeHttpClient]:
        return sender, client

    async def process_intents(*_: object, **__: object) -> NotificationIntentWorkerResult:
        return NotificationIntentWorkerResult(claimed=0, processed=0, dead_lettered=0)

    async def process_notifications(*_: object, **__: object) -> int:
        return 0

    async def stop_after_sleep(seconds: int | float) -> None:
        sleep_calls.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(notification_worker, "_build_sender", build_sender)
    monkeypatch.setattr(
        notification_worker,
        "process_notification_request_events",
        process_intents,
    )
    monkeypatch.setattr(
        notification_worker,
        "process_pending_notifications",
        process_notifications,
    )
    monkeypatch.setattr(notification_worker.asyncio, "sleep", stop_after_sleep)

    with pytest.raises(asyncio.CancelledError):
        await notification_worker.main()

    assert heartbeats == [settings.notification_worker_heartbeat_path]
    assert sleep_calls == [2]
    assert client.closed is True
    assert FakeDatabase.instances[0].disposed is True
