"""Runtime wiring tests for the Google Calendar OAuth provider."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import SecretStr

import app.main as app_main
from app.core.config import Settings
from app.domains.calendar.enums import CalendarProvider

_CLIENT_ID_SECRET_NAME = "tap_google_calendar_client_id"  # noqa: S105
_CLIENT_SECRET_SECRET_NAME = "tap_google_calendar_client_secret"  # noqa: S105


@dataclass
class FakeVault:
    """In-memory fake for startup configuration tests."""

    secrets: Mapping[str, SecretStr]
    requested_secret_names: list[str] = field(default_factory=list)

    async def read_runtime_secret(self, *, secret_name: str) -> SecretStr:
        """Return a configured runtime secret and record its name."""
        self.requested_secret_names.append(secret_name)

        try:
            return self.secrets[secret_name]
        except KeyError as error:
            raise RuntimeError("runtime secret unavailable") from error


class FakeDatabase:
    """Avoid real database connections while exercising application lifespan."""

    def __init__(self, *_: object, **__: object) -> None:
        """Initialize an undisposed fake database."""
        self.disposed = False

    async def dispose(self) -> None:
        """Record that database resources were disposed."""
        self.disposed = True


class FakeHttpClient:
    """Records lifecycle ownership without making network calls."""

    instances: list["FakeHttpClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        """Record client construction without opening a network connection."""
        self.kwargs = kwargs
        self.closed = False
        self.__class__.instances.append(self)

    async def aclose(self) -> None:
        """Record that the client was closed."""
        self.closed = True


@dataclass
class FakeGoogleCalendarOAuthProvider:
    """Captures construction inputs without contacting Google."""

    client_id: str
    client_secret: SecretStr
    http_client: FakeHttpClient


def _settings() -> Settings:
    """Return minimal valid settings for the Google OAuth runtime path."""
    return Settings(
        app_env="test",
        app_name="tap-api-test",
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
        infisical_client_secret=SecretStr("test-machine-secret"),
        infisical_project_id="test-project-id",
        infisical_environment="test",
        calendar_oauth_provider="google",
        google_calendar_oauth_client_id_secret_name=_CLIENT_ID_SECRET_NAME,
        google_calendar_oauth_client_secret_secret_name=_CLIENT_SECRET_SECRET_NAME,
    )


@pytest.fixture(autouse=True)
def _reset_fake_http_clients() -> None:
    """Prevent lifecycle assertions leaking between tests."""
    FakeHttpClient.instances.clear()


@pytest.mark.asyncio
async def test_lifespan_wires_google_oauth_from_infisical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup resolves named secrets and shutdown closes the HTTP client."""
    settings = _settings()
    vault = FakeVault(
        secrets={
            _CLIENT_ID_SECRET_NAME: SecretStr("google-client-id"),
            _CLIENT_SECRET_SECRET_NAME: SecretStr(
                "google-client-secret"
            ),
        }
    )

    async def create_vault(**_: object) -> FakeVault:
        return vault

    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "Database", FakeDatabase)
    monkeypatch.setattr(
        app_main.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        app_main.InfisicalHrisCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(app_main.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(
        app_main,
        "GoogleCalendarOAuthProvider",
        FakeGoogleCalendarOAuthProvider,
    )

    application = FastAPI()
    application.state.settings = settings

    async with app_main.lifespan(application):
        provider = application.state.calendar_oauth_providers[
            CalendarProvider.GOOGLE
        ]

        assert isinstance(provider, FakeGoogleCalendarOAuthProvider)
        assert provider.client_id == "google-client-id"
        assert (
            provider.client_secret.get_secret_value()
            == "google-client-secret"
        )
        assert application.state.calendar_credential_vault is vault
        assert application.state.calendar_credential_resolver is vault
        assert vault.requested_secret_names == [
            "tap_google_calendar_client_id",
            "tap_google_calendar_client_secret",
        ]
        assert len(FakeHttpClient.instances) == 1
        assert FakeHttpClient.instances[0].closed is False

    assert FakeHttpClient.instances[0].closed is True


@pytest.mark.asyncio
async def test_lifespan_fails_before_google_client_when_secret_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup fails closed when required OAuth configuration is unavailable."""
    settings = _settings()
    vault = FakeVault(
        secrets={
            _CLIENT_ID_SECRET_NAME: SecretStr("google-client-id"),
        }
    )

    async def create_vault(**_: object) -> FakeVault:
        return vault

    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "Database", FakeDatabase)
    monkeypatch.setattr(
        app_main.InfisicalCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(
        app_main.InfisicalHrisCredentialVault,
        "from_universal_auth",
        create_vault,
    )
    monkeypatch.setattr(app_main.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(
        app_main,
        "GoogleCalendarOAuthProvider",
        FakeGoogleCalendarOAuthProvider,
    )

    application = FastAPI()
    application.state.settings = settings

    with pytest.raises(RuntimeError, match="runtime secret unavailable"):
        async with app_main.lifespan(application):
            pass

    assert vault.requested_secret_names == [
        "tap_google_calendar_client_id",
        "tap_google_calendar_client_secret",
    ]
    assert not FakeHttpClient.instances


@pytest.mark.asyncio
async def test_lifespan_does_not_create_google_client_when_provider_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local and non-calendar deployments do not require Google configuration."""
    settings = _settings().model_copy(
        update={
            "calendar_oauth_provider": "none",
            "credential_vault_provider": "none",
            "infisical_client_id": None,
            "infisical_client_secret": None,
            "infisical_project_id": None,
        }
    )

    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "Database", FakeDatabase)
    monkeypatch.setattr(app_main.httpx, "AsyncClient", FakeHttpClient)

    application = FastAPI()
    application.state.settings = settings

    async with app_main.lifespan(application):
        assert application.state.calendar_oauth_providers == {}
        assert application.state.calendar_credential_vault is None
        assert application.state.calendar_credential_resolver is None

    assert not FakeHttpClient.instances
