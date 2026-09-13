"""PostgreSQL integration tests for calendar OAuth connection authorization."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.calendar import CalendarConnection
from app.db.models.identity import Tenant, User
from app.domains.calendar.enums import CalendarProvider
from app.services import calendar_connections
from app.services.calendar_connection_errors import (
    CalendarConnectionValidationError,
)
from app.services.calendar_connections import (
    begin_calendar_authorization,
    complete_calendar_authorization,
)
from app.services.calendar_credentials import (
    CalendarCredentialVault,
    ResolvedCalendarCredentials,
)
from app.services.calendar_oauth import (
    CalendarAuthorizationRequest,
    CalendarOAuthCodeExchange,
    CalendarOAuthProvider,
    CalendarOAuthState,
    CalendarOAuthStateError,
    CalendarOAuthStateStore,
)

_NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
_REDIRECT_URI = "http://localhost:3000/oauth/calendar/callback"


@dataclass
class _FakeOAuthStateStore(CalendarOAuthStateStore):
    """In-memory one-time OAuth state store."""

    states: dict[str, CalendarOAuthState] = field(default_factory=dict)

    async def store(
        self,
        *,
        state_token: str,
        state: CalendarOAuthState,
    ) -> None:
        self.states[state_token] = state

    async def consume(self, *, state_token: str) -> CalendarOAuthState:
        state = self.states.pop(state_token, None)
        if state is None:
            raise CalendarOAuthStateError(
                "Calendar OAuth state is missing or already used."
            )
        return state


@dataclass
class _FakeOAuthProvider(CalendarOAuthProvider):
    """Provider fake that records PKCE requests and code exchanges."""

    provider: CalendarProvider = CalendarProvider.GOOGLE
    authorization_requests: list[CalendarAuthorizationRequest] = field(
        default_factory=list
    )
    exchanges: list[CalendarOAuthCodeExchange] = field(default_factory=list)

    async def create_authorization_url(
        self,
        *,
        request: CalendarAuthorizationRequest,
    ) -> str:
        self.authorization_requests.append(request)
        return f"https://provider.example.test/authorize?state={request.state_token}"

    async def exchange_code(
        self,
        *,
        exchange: CalendarOAuthCodeExchange,
    ) -> ResolvedCalendarCredentials:
        self.exchanges.append(exchange)
        return ResolvedCalendarCredentials(
            values={
                "access_token": SecretStr("test-access-token"),
                "refresh_token": SecretStr("test-refresh-token"),
            }
        )


@dataclass
class _FakeCredentialVault(CalendarCredentialVault):
    """External credential-vault fake that stores no data in PostgreSQL."""

    references: dict[str, ResolvedCalendarCredentials] = field(
        default_factory=dict
    )
    deleted_references: list[str] = field(default_factory=list)

    async def store(
        self,
        *,
        provider: str,
        tenant_id: str,
        owner_user_id: str,
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        reference = (
            f"vault://calendar/{provider}/{tenant_id}/{owner_user_id}/"
            f"{uuid4()}"
        )
        self.references[reference] = credentials
        return reference

    async def delete(self, *, credential_reference: str) -> None:
        self.deleted_references.append(credential_reference)
        self.references.pop(credential_reference, None)


def _context(
    tenant_id: UUID,
    *,
    subject: str,
) -> TenantContext:
    """Build a verified caller context for one calendar owner."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=frozenset({Role.INTERVIEWER}),
        request_id="calendar-oauth-test-request",
    )


async def _seed_user(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    subject: str,
    create_tenant: bool = True,
) -> User:
    """Create one internal tenant user corresponding to a JWT subject."""
    if create_tenant:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Calendar OAuth Tenant {tenant_id.hex[:12]}",
                slug=f"calendar-oauth-{tenant_id.hex[:12]}",
            )
        )

    user = User(
        tenant_id=tenant_id,
        external_subject=subject,
        email=f"{subject}-{tenant_id.hex[:8]}@example.test",
        display_name="Calendar Connection Owner",
    )
    session.add(user)
    await session.commit()
    return user


async def _start_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    state_store: _FakeOAuthStateStore,
    provider: _FakeOAuthProvider,
) -> str:
    """Start one OAuth authorization and return its browser-safe state token."""
    request_count = len(provider.authorization_requests)
    authorization_url = await begin_calendar_authorization(
        session,
        context=context,
        provider=CalendarProvider.GOOGLE,
        redirect_uri=_REDIRECT_URI,
        oauth_state_store=state_store,
        oauth_providers={CalendarProvider.GOOGLE: provider},
        now=_NOW,
    )

    assert authorization_url.startswith(
        "https://provider.example.test/authorize?state="
    )
    assert len(provider.authorization_requests) == request_count + 1

    return provider.authorization_requests[-1].state_token


@pytest.mark.asyncio
async def test_authorizes_and_upserts_connection_with_privacy_safe_audit(
    session: AsyncSession,
) -> None:
    """Store credentials externally and upsert one tenant-user connection."""
    tenant_id = uuid4()
    subject = "interviewer-subject"
    await _seed_user(
        session,
        tenant_id=tenant_id,
        subject=subject,
    )

    context = _context(tenant_id, subject=subject)
    state_store = _FakeOAuthStateStore()
    provider = _FakeOAuthProvider()
    vault = _FakeCredentialVault()

    state_token = await _start_authorization(
        session,
        context=context,
        state_store=state_store,
        provider=provider,
    )

    first = await complete_calendar_authorization(
        session,
        provider=CalendarProvider.GOOGLE,
        state_token=state_token,
        authorization_code=SecretStr("first-provider-code"),
        request_id="calendar-oauth-test-request",
        oauth_state_store=state_store,
        oauth_providers={CalendarProvider.GOOGLE: provider},
        credential_vault=vault,
        now=_NOW,
    )
    first_credential_reference = first.credential_reference

    second_state_token = await _start_authorization(
        session,
        context=context,
        state_store=state_store,
        provider=provider,
    )
    second = await complete_calendar_authorization(
        session,
        provider=CalendarProvider.GOOGLE,
        state_token=second_state_token,
        authorization_code=SecretStr("second-provider-code"),
        request_id="calendar-oauth-test-request",
        oauth_state_store=state_store,
        oauth_providers={CalendarProvider.GOOGLE: provider},
        credential_vault=vault,
        now=_NOW,
    )

    connections = list(
        await session.scalars(
            select(CalendarConnection).where(
                CalendarConnection.tenant_id == tenant_id
            )
        )
    )
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "calendar_connection.authorized",
                AuditEvent.entity_id == str(first.id),
            )
        )
    )

    assert first.id == second.id
    assert first_credential_reference != second.credential_reference
    assert len(connections) == 1
    assert len(vault.references) == 2
    assert len(provider.exchanges) == 2

    assert len(audits) == 2
    rendered_audits = str([audit.details for audit in audits])
    for prohibited_value in (
        "first-provider-code",
        "second-provider-code",
        "test-access-token",
        "test-refresh-token",
        "vault://",
        _REDIRECT_URI,
    ):
        assert prohibited_value not in rendered_audits

    assert audits[0].details["provider"] == "google"


@pytest.mark.asyncio
async def test_state_is_consumed_once(
    session: AsyncSession,
) -> None:
    """A callback state cannot be replayed after a successful connection."""
    tenant_id = uuid4()
    subject = "recruiter-subject"
    await _seed_user(session, tenant_id=tenant_id, subject=subject)

    context = _context(tenant_id, subject=subject)
    state_store = _FakeOAuthStateStore()
    provider = _FakeOAuthProvider()
    vault = _FakeCredentialVault()
    state_token = await _start_authorization(
        session,
        context=context,
        state_store=state_store,
        provider=provider,
    )

    await complete_calendar_authorization(
        session,
        provider=CalendarProvider.GOOGLE,
        state_token=state_token,
        authorization_code=SecretStr("provider-code"),
        request_id="calendar-oauth-test-request",
        oauth_state_store=state_store,
        oauth_providers={CalendarProvider.GOOGLE: provider},
        credential_vault=vault,
        now=_NOW,
    )

    with pytest.raises(CalendarOAuthStateError):
        await complete_calendar_authorization(
            session,
            provider=CalendarProvider.GOOGLE,
            state_token=state_token,
            authorization_code=SecretStr("replayed-provider-code"),
            request_id="calendar-oauth-test-request",
            oauth_state_store=state_store,
            oauth_providers={CalendarProvider.GOOGLE: provider},
            credential_vault=vault,
            now=_NOW,
        )

    assert len(provider.exchanges) == 1
    assert len(vault.references) == 1


@pytest.mark.asyncio
async def test_rejects_expired_and_provider_mismatched_state(
    session: AsyncSession,
) -> None:
    """State expiry and provider binding are enforced before code exchange."""
    tenant_id = uuid4()
    first_subject = "first-user"

    await _seed_user(
        session,
        tenant_id=tenant_id,
        subject=first_subject,
    )

    state_store = _FakeOAuthStateStore()
    provider = _FakeOAuthProvider()
    vault = _FakeCredentialVault()

    first_context = _context(tenant_id, subject=first_subject)
    state_token = await _start_authorization(
        session,
        context=first_context,
        state_store=state_store,
        provider=provider,
    )

    with pytest.raises(CalendarOAuthStateError, match="expired"):
        await complete_calendar_authorization(
            session,
            provider=CalendarProvider.GOOGLE,
            state_token=state_token,
            authorization_code=SecretStr("provider-code"),
            request_id="calendar-oauth-test-request",
            oauth_state_store=state_store,
            oauth_providers={CalendarProvider.GOOGLE: provider},
            credential_vault=vault,
            now=_NOW + timedelta(minutes=11),
        )

    provider_state_token = await _start_authorization(
        session,
        context=first_context,
        state_store=state_store,
        provider=provider,
    )
    with pytest.raises(CalendarOAuthStateError, match="invalid"):
        await complete_calendar_authorization(
            session,
            provider=CalendarProvider.MICROSOFT,
            state_token=provider_state_token,
            authorization_code=SecretStr("provider-code"),
            request_id="calendar-oauth-test-request",
            oauth_state_store=state_store,
            oauth_providers={
                CalendarProvider.MICROSOFT: provider,
            },
            credential_vault=vault,
            now=_NOW,
        )

    assert not provider.exchanges
    assert not vault.references


@pytest.mark.asyncio
async def test_deletes_new_vault_secret_when_database_persistence_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid orphaned credentials if the connection transaction rolls back."""
    tenant_id = uuid4()
    subject = "people-ops-subject"
    await _seed_user(session, tenant_id=tenant_id, subject=subject)

    context = _context(tenant_id, subject=subject)
    state_store = _FakeOAuthStateStore()
    provider = _FakeOAuthProvider()
    vault = _FakeCredentialVault()
    state_token = await _start_authorization(
        session,
        context=context,
        state_store=state_store,
        provider=provider,
    )

    def fail_audit(*_: object, **__: object) -> None:
        raise RuntimeError("simulated database persistence failure")

    monkeypatch.setattr(
        calendar_connections,
        "record_audit_event",
        fail_audit,
    )

    with pytest.raises(RuntimeError, match="simulated"):
        await complete_calendar_authorization(
            session,
            provider=CalendarProvider.GOOGLE,
            state_token=state_token,
            authorization_code=SecretStr("provider-code"),
            request_id="calendar-oauth-test-request",
            oauth_state_store=state_store,
            oauth_providers={CalendarProvider.GOOGLE: provider},
            credential_vault=vault,
            now=_NOW,
        )

    connections = list(
        await session.scalars(
            select(CalendarConnection).where(
                CalendarConnection.tenant_id == tenant_id
            )
        )
    )

    assert not connections
    assert not vault.references
    assert len(vault.deleted_references) == 1


@pytest.mark.asyncio
async def test_rejects_untrusted_remote_http_redirect_uri(
    session: AsyncSession,
) -> None:
    """Only server-configured HTTPS or localhost development callbacks are valid."""
    tenant_id = uuid4()
    subject = "calendar-owner"
    await _seed_user(session, tenant_id=tenant_id, subject=subject)

    with pytest.raises(CalendarConnectionValidationError):
        await begin_calendar_authorization(
            session,
            context=_context(tenant_id, subject=subject),
            provider=CalendarProvider.GOOGLE,
            redirect_uri="http://untrusted.example.test/callback",
            oauth_state_store=_FakeOAuthStateStore(),
            oauth_providers={
                CalendarProvider.GOOGLE: _FakeOAuthProvider()
            },
            now=_NOW,
        )
