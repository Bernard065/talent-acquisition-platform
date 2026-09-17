"""HTTP integration tests for private calendar OAuth authorization endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_calendar_credential_vault,
    get_calendar_oauth_providers,
    get_calendar_oauth_state_store,
    get_db_session,
    get_tenant_context,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.audit import AuditEvent
from app.db.models.calendar import CalendarConnection
from app.db.models.identity import Tenant, User
from app.domains.calendar.enums import CalendarProvider
from app.main import create_app
from app.services.calendar_credentials import (
    CalendarCredentialVault,
    ResolvedCalendarCredentials,
)
from app.services.calendar_oauth import (
    CalendarAuthorizationRequest,
    CalendarOAuthCodeExchange,
    CalendarOAuthError,
    CalendarOAuthProvider,
    CalendarOAuthState,
    CalendarOAuthStateError,
    CalendarOAuthStateStore,
)


class FakeCalendarOAuthStateStore:
    """In-memory one-time state store used only by HTTP integration tests."""

    def __init__(self) -> None:
        self.states: dict[str, CalendarOAuthState] = {}

    async def store(
        self,
        *,
        state_token: str,
        state: CalendarOAuthState,
    ) -> None:
        """Store an OAuth state record in memory."""
        self.states[state_token] = state

    async def consume(self, *, state_token: str) -> CalendarOAuthState:
        """Consume and remove one OAuth state record."""
        state = self.states.pop(state_token, None)
        if state is None:
            raise CalendarOAuthStateError("Calendar OAuth state is invalid.")

        return state


class FakeCalendarOAuthProvider:
    """Deterministic provider adapter that never contacts an external service."""

    def __init__(self, provider: CalendarProvider) -> None:
        self.provider = provider
        self.authorization_requests: list[CalendarAuthorizationRequest] = []
        self.code_exchanges: list[CalendarOAuthCodeExchange] = []

    async def create_authorization_url(
        self,
        *,
        request: CalendarAuthorizationRequest,
    ) -> str:
        """Return a deterministic provider authorization URL."""
        self.authorization_requests.append(request)
        return (
            "https://calendar-provider.example.test/authorize"
            f"?state={request.state_token}"
        )

    async def exchange_code(
        self,
        *,
        exchange: CalendarOAuthCodeExchange,
    ) -> ResolvedCalendarCredentials:
        """Return deterministic credentials without contacting a provider."""
        self.code_exchanges.append(exchange)
        return ResolvedCalendarCredentials(
            values={
                "access_token": SecretStr("test-access-token"),
                "refresh_token": SecretStr("test-refresh-token"),
            }
        )


class FailingCalendarOAuthProvider(FakeCalendarOAuthProvider):
    """Provider fake that returns a classified exchange failure."""

    def __init__(
        self,
        provider: CalendarProvider,
        *,
        error: CalendarOAuthError,
    ) -> None:
        super().__init__(provider)
        self.error = error

    async def exchange_code(
        self,
        *,
        exchange: CalendarOAuthCodeExchange,
    ) -> ResolvedCalendarCredentials:
        """Raise a controlled provider failure without external I/O."""
        self.code_exchanges.append(exchange)
        raise self.error


class FakeCalendarCredentialVault:
    """In-memory vault that returns opaque references only."""

    def __init__(self) -> None:
        self.stored_references: list[str] = []
        self.deleted_references: list[str] = []

    async def store(
        self,
        *,
        provider: str,
        tenant_id: str,
        owner_user_id: str,
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        """Return an opaque reference without retaining credential values."""
        del credentials
        reference = (
            f"test-vault://calendar/{provider}/{tenant_id}/{owner_user_id}"
        )
        self.stored_references.append(reference)
        return reference

    async def delete(self, *, credential_reference: str) -> None:
        """Record deletion of an opaque credential reference."""
        self.deleted_references.append(credential_reference)


def _test_settings() -> Settings:
    """Build API settings without loading developer environment variables."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
        calendar_google_oauth_redirect_uri=(
            "http://localhost:8000/api/v1/calendar-connections/google/callback"
        ),
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _context_dependency(
    tenant_id: UUID,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return a verified tenant context for one API test."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="calendar-owner-subject",
            roles=roles,
            request_id="calendar-oauth-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide request-scoped sessions for API integration tests."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    return override


async def _create_tenant_and_owner(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    subject: str = "calendar-owner-subject",
) -> User:
    """Create one tenant and a user matching the test JWT subject."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        tenant = Tenant(
            id=tenant_id,
            name=f"Calendar API Tenant {tenant_id.hex[:12]}",
            slug=f"calendar-api-{tenant_id.hex[:12]}",
        )
        owner = User(
            tenant_id=tenant_id,
            external_subject=subject,
            email=f"calendar-owner-{tenant_id.hex[:12]}@example.test",
            display_name="Calendar Owner",
        )
        session.add_all([tenant, owner])
        await session.flush()
        return owner


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    roles: frozenset[Role],
) -> None:
    """Set the authenticated caller for a start-authorization request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


def _extract_state(authorization_url: str) -> str:
    """Extract the opaque state token from a fake provider URL."""
    values = parse_qs(urlparse(authorization_url).query)
    return values["state"][0]


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant for calendar OAuth endpoint tests."""
    tenant_id = uuid4()
    await _create_tenant_and_owner(database_engine, tenant_id=tenant_id)
    return tenant_id


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create an API configured with deterministic calendar integration fakes."""
    state_store = FakeCalendarOAuthStateStore()
    google_provider = FakeCalendarOAuthProvider(CalendarProvider.GOOGLE)
    microsoft_provider = FakeCalendarOAuthProvider(CalendarProvider.MICROSOFT)
    credential_vault = FakeCalendarCredentialVault()

    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.dependency_overrides[
        get_calendar_oauth_state_store
    ] = lambda: cast(CalendarOAuthStateStore, state_store)
    application.dependency_overrides[
        get_calendar_oauth_providers
    ] = lambda: cast(
        Mapping[CalendarProvider, CalendarOAuthProvider],
        {
            CalendarProvider.GOOGLE: google_provider,
            CalendarProvider.MICROSOFT: microsoft_provider,
        },
    )
    application.dependency_overrides[
        get_calendar_credential_vault
    ] = lambda: cast(CalendarCredentialVault, credential_vault)

    _set_context(
        application,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    yield application

    application.dependency_overrides.clear()

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, calendar_connections, users, tenants CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_starts_authorization_for_an_allowed_role(
    api_app: FastAPI,
) -> None:
    """Return one private authorization URL without exposing PKCE material."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/calendar-connections/google/authorization"
        )

    body = response.json()

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert body["expires_in_seconds"] == 600
    assert body["authorization_url"].startswith(
        "https://calendar-provider.example.test/authorize?"
    )
    assert "code_verifier" not in body
    assert "access_token" not in body
    assert "refresh_token" not in body


@pytest.mark.asyncio
async def test_rejects_roles_without_calendar_connection_access(
    api_app: FastAPI,
    tenant_id: UUID,
) -> None:
    """Hiring managers cannot authorize a personal calendar connection."""
    _set_context(
        api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.HIRING_MANAGER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/calendar-connections/google/authorization"
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_completes_callback_once_without_bearer_token(
    api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Use the one-time state capability, not a JWT, for the provider callback."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        start = await client.post(
            "/api/v1/calendar-connections/google/authorization"
        )
        state = _extract_state(start.json()["authorization_url"])

        callback = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "provider-one-time-code",
                "state": state,
            },
        )
        replay = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "provider-one-time-code",
                "state": state,
            },
        )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        connection_count = len(
            list(await session.scalars(select(CalendarConnection)))
        )
        audit_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "calendar_connection.authorized"
            )
        )

    callback_body = callback.json()

    assert start.status_code == 200
    assert callback.status_code == 200
    assert replay.status_code == 400
    assert callback.headers["Cache-Control"] == "private, no-store"
    assert connection_count == 1
    assert audit_event is not None
    assert audit_event.details == {
        "provider": "google",
        "connection_version": 1,
    }

    assert "credential_reference" not in callback_body
    assert "tenant_id" not in callback_body
    assert "owner_user_id" not in callback_body
    assert "provider-one-time-code" not in str(callback_body)
    assert "test-access-token" not in str(callback_body)
    assert "test-refresh-token" not in str(callback_body)


@pytest.mark.asyncio
async def test_rejects_expired_and_provider_mismatched_states(
    api_app: FastAPI,
    tenant_id: UUID,
    database_engine: AsyncEngine,
) -> None:
    """Reject expired or wrong-provider state without creating connections."""
    state_store = FakeCalendarOAuthStateStore()

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        owner = await session.scalar(
            select(User).where(User.tenant_id == tenant_id)
        )

    assert owner is not None

    await state_store.store(
        state_token="expired-state-token-" + "a" * 32,
        state=CalendarOAuthState(
            tenant_id=tenant_id,
            owner_user_id=owner.id,
            provider=CalendarProvider.GOOGLE,
            redirect_uri=(
                "http://localhost:8000/api/v1/"
                "calendar-connections/google/callback"
            ),
            code_verifier=SecretStr("verifier"),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )
    await state_store.store(
        state_token="mismatched-state-token-" + "b" * 32,
        state=CalendarOAuthState(
            tenant_id=tenant_id,
            owner_user_id=owner.id,
            provider=CalendarProvider.MICROSOFT,
            redirect_uri=(
                "http://localhost:8000/api/v1/"
                "calendar-connections/microsoft/callback"
            ),
            code_verifier=SecretStr("verifier"),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )

    api_app.dependency_overrides[
        get_calendar_oauth_state_store
    ] = lambda: cast(CalendarOAuthStateStore, state_store)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        expired = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "code",
                "state": "expired-state-token-" + "a" * 32,
            },
        )
        mismatched = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "code",
                "state": "mismatched-state-token-" + "b" * 32,
            },
        )

    assert expired.status_code == 400
    assert mismatched.status_code == 400
    assert expired.headers["Cache-Control"] == "private, no-store"
    assert mismatched.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_callback_persists_only_to_the_state_bound_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """The callback accepts no tenant input and uses only stored state scope."""
    other_tenant_id = uuid4()
    other_owner = await _create_tenant_and_owner(
        database_engine,
        tenant_id=other_tenant_id,
        subject="other-calendar-owner",
    )

    state_store = FakeCalendarOAuthStateStore()
    state_token = "other-tenant-state-" + "c" * 32
    await state_store.store(
        state_token=state_token,
        state=CalendarOAuthState(
            tenant_id=other_tenant_id,
            owner_user_id=other_owner.id,
            provider=CalendarProvider.GOOGLE,
            redirect_uri=(
                "http://localhost:8000/api/v1/"
                "calendar-connections/google/callback"
            ),
            code_verifier=SecretStr("verifier"),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )
    api_app.dependency_overrides[
        get_calendar_oauth_state_store
    ] = lambda: cast(CalendarOAuthStateStore, state_store)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "other-tenant-code",
                "state": state_token,
            },
        )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        connection = await session.scalar(select(CalendarConnection))

    assert response.status_code == 200
    assert connection is not None
    assert connection.tenant_id == other_tenant_id
    assert connection.owner_user_id == other_owner.id


@pytest.mark.asyncio
async def test_returns_private_service_unavailable_when_state_store_missing(
    api_app: FastAPI,
) -> None:
    """Fail closed when the OAuth state store is not configured."""
    del api_app.dependency_overrides[get_calendar_oauth_state_store]

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/calendar-connections/google/authorization"
        )

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Retry-After"] == "5"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            CalendarOAuthError(
                "invalid_grant",
                retryable=False,
            ),
            400,
        ),
        (
            CalendarOAuthError(
                "provider_temporarily_unavailable",
                retryable=True,
            ),
            503,
        ),
    ],
)
async def test_callback_maps_provider_failures_without_leaking_details(
    api_app: FastAPI,
    error: CalendarOAuthError,
    expected_status: int,
) -> None:
    """Classify provider failures without exposing codes or credential data."""
    failing_provider = FailingCalendarOAuthProvider(
        CalendarProvider.GOOGLE,
        error=error,
    )

    api_app.dependency_overrides[
        get_calendar_oauth_providers
    ] = lambda: cast(
        Mapping[CalendarProvider, CalendarOAuthProvider],
        {CalendarProvider.GOOGLE: failing_provider},
    )

    state_store = FakeCalendarOAuthStateStore()
    api_app.dependency_overrides[
        get_calendar_oauth_state_store
    ] = lambda: cast(CalendarOAuthStateStore, state_store)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        start = await client.post(
            "/api/v1/calendar-connections/google/authorization"
        )
        state = _extract_state(start.json()["authorization_url"])

        response = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "provider-one-time-code",
                "state": state,
            },
        )

    body = response.json()

    assert response.status_code == expected_status
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "provider_temporarily_unavailable" not in str(body)
    assert "invalid_grant" not in str(body)
    assert "provider-one-time-code" not in str(body)
    assert "access_token" not in str(body)
    assert "refresh_token" not in str(body)

    if expected_status == 503:
        assert response.headers["Retry-After"] == "5"
        assert body["detail"] == (
            "Calendar authorization service is temporarily unavailable."
        )
    else:
        assert body["detail"] == "Calendar authorization could not be completed."


@pytest.mark.asyncio
async def test_callback_rejects_unknown_state_without_leaking_state_value(
    api_app: FastAPI,
) -> None:
    """An unrecognised state is rejected with the generic private error."""
    unknown_state = "unknown-state-" + "x" * 40

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "provider-one-time-code",
                "state": unknown_state,
            },
        )

    body = response.json()

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "private, no-store"
    assert body["detail"] == "Calendar authorization could not be completed."
    assert unknown_state not in str(body)
    assert "provider-one-time-code" not in str(body)


@pytest.mark.asyncio
async def test_callback_requires_well_formed_query_parameters(
    api_app: FastAPI,
) -> None:
    """FastAPI rejects absent, empty, and undersized callback parameters."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        missing_code = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={"state": "s" * 32},
        )
        empty_code = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "",
                "state": "s" * 32,
            },
        )
        short_state = await client.get(
            "/api/v1/calendar-connections/google/callback",
            params={
                "code": "provider-one-time-code",
                "state": "too-short",
            },
        )

    assert missing_code.status_code == 422
    assert empty_code.status_code == 422
    assert short_state.status_code == 422
