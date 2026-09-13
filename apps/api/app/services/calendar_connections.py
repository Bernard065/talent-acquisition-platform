"""Secure, tenant-scoped OAuth authorization service for calendar connections."""

import base64
import hashlib
import secrets
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.calendar import CalendarConnection
from app.db.models.identity import User
from app.db.transactions import transactional
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
)
from app.services.audit import record_audit_event
from app.services.calendar_connection_errors import (
    CalendarConnectionAccessDeniedError,
    CalendarConnectionValidationError,
)
from app.services.calendar_credentials import CalendarCredentialVault
from app.services.calendar_oauth import (
    CalendarAuthorizationRequest,
    CalendarOAuthCodeExchange,
    CalendarOAuthError,
    CalendarOAuthProvider,
    CalendarOAuthState,
    CalendarOAuthStateError,
    CalendarOAuthStateStore,
)

_CONNECTION_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
        Role.INTERVIEWER,
    }
)
_OAUTH_STATE_TTL = timedelta(minutes=10)


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _require_connection_access(context: TenantContext) -> None:
    """Allow eligible users to connect only their own calendar."""
    if context.roles.isdisjoint(_CONNECTION_ROLES):
        raise CalendarConnectionAccessDeniedError(
            "Caller is not permitted to manage calendar connections."
        )


def _validate_redirect_uri(redirect_uri: str) -> str:
    """
    Validate a server-configured callback URI.

    API routes must obtain this value from trusted configuration, never from a
    browser request. HTTP is allowed only for local development callbacks.
    """
    normalized = redirect_uri.strip()
    parsed = urlparse(normalized)

    if parsed.scheme == "https" and parsed.netloc:
        return normalized

    if (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        return normalized

    raise CalendarConnectionValidationError(
        "Calendar OAuth redirect URI must use HTTPS."
    )


def _generate_pkce_verifier() -> SecretStr:
    """Generate a high-entropy PKCE verifier held only server-side."""
    return SecretStr(secrets.token_urlsafe(64))


def _pkce_challenge(code_verifier: SecretStr) -> str:
    """Derive the RFC 7636 S256 challenge for a PKCE verifier."""
    digest = hashlib.sha256(
        code_verifier.get_secret_value().encode("ascii")
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _generate_state_token() -> str:
    """Generate an opaque browser-safe state token."""
    return secrets.token_urlsafe(32)


async def _current_tenant_user(
    session: AsyncSession,
    *,
    context: TenantContext,
    lock: bool = False,
) -> User:
    """Load the caller's internal tenant user record from verified subject."""
    statement = select(User).where(
        User.tenant_id == context.tenant_id,
        User.external_subject == context.subject,
    )
    if lock:
        statement = statement.with_for_update()

    user = await session.scalar(statement)
    if user is None:
        raise CalendarConnectionAccessDeniedError(
            "Caller is not available for calendar connection management."
        )

    return user


async def _state_owner(
    session: AsyncSession,
    *,
    state: CalendarOAuthState,
    lock: bool = False,
) -> User:
    """Load the tenant user bound to a consumed OAuth state record."""
    statement = select(User).where(
        User.tenant_id == state.tenant_id,
        User.id == state.owner_user_id,
    )
    if lock:
        statement = statement.with_for_update()

    owner = await session.scalar(statement)
    if owner is None:
        raise CalendarOAuthStateError("Calendar OAuth state is invalid.")

    return owner


async def begin_calendar_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    provider: CalendarProvider,
    redirect_uri: str,
    oauth_state_store: CalendarOAuthStateStore,
    oauth_providers: Mapping[CalendarProvider, CalendarOAuthProvider],
    now: datetime | None = None,
) -> str:
    """
    Create a one-time PKCE authorization URL for the authenticated user.

    The resulting URL can be returned to the browser. State and verifier stay
    server-side in the OAuth state store.
    """
    _require_connection_access(context)
    trusted_redirect_uri = _validate_redirect_uri(redirect_uri)
    owner = await _current_tenant_user(session, context=context)

    oauth_provider = oauth_providers.get(provider)
    if oauth_provider is None:
        raise CalendarOAuthError(
            "calendar_oauth_provider_not_configured",
            retryable=False,
        )

    authorization_time = now or _now()
    if authorization_time.tzinfo is None:
        raise CalendarConnectionValidationError(
            "Calendar authorization time must include a UTC offset."
        )

    state_token = _generate_state_token()
    code_verifier = _generate_pkce_verifier()

    await oauth_state_store.store(
        state_token=state_token,
        state=CalendarOAuthState(
            tenant_id=context.tenant_id,
            owner_user_id=owner.id,
            provider=provider,
            redirect_uri=trusted_redirect_uri,
            code_verifier=code_verifier,
            expires_at=authorization_time.astimezone(UTC) + _OAUTH_STATE_TTL,
        ),
    )

    return await oauth_provider.create_authorization_url(
        request=CalendarAuthorizationRequest(
            state_token=state_token,
            redirect_uri=trusted_redirect_uri,
            code_challenge=_pkce_challenge(code_verifier),
        )
    )


async def complete_calendar_authorization(
    session: AsyncSession,
    *,
    provider: CalendarProvider,
    state_token: str,
    authorization_code: SecretStr,
    request_id: str,
    oauth_state_store: CalendarOAuthStateStore,
    oauth_providers: Mapping[CalendarProvider, CalendarOAuthProvider],
    credential_vault: CalendarCredentialVault,
    now: datetime | None = None,
) -> CalendarConnection:
    """
    Consume one OAuth callback and activate its state-bound calendar connection.

    The one-time state token acts as a short-lived capability created by an
    authenticated caller. A provider callback must not require a bearer token.
    """
    oauth_provider = oauth_providers.get(provider)
    if oauth_provider is None:
        raise CalendarOAuthError(
            "calendar_oauth_provider_not_configured",
            retryable=False,
        )

    callback_time = now or _now()
    if (
        callback_time.tzinfo is None
        or callback_time.utcoffset() is None
    ):
        raise CalendarConnectionValidationError(
            "Calendar authorization time must include a UTC offset."
        )

    state = await oauth_state_store.consume(state_token=state_token)

    if (
        state.expires_at <= callback_time.astimezone(UTC)
        or state.provider != provider
    ):
        raise CalendarOAuthStateError("Calendar OAuth state is invalid.")

    credentials = await oauth_provider.exchange_code(
        exchange=CalendarOAuthCodeExchange(
            authorization_code=authorization_code,
            redirect_uri=state.redirect_uri,
            code_verifier=state.code_verifier,
        )
    )

    new_credential_reference = await credential_vault.store(
        provider=provider.value,
        tenant_id=str(state.tenant_id),
        owner_user_id=str(state.owner_user_id),
        credentials=credentials,
    )

    try:
        async with transactional(session):
            locked_owner = await _state_owner(
                session,
                state=state,
                lock=True,
            )

            connection = await session.scalar(
                select(CalendarConnection)
                .where(
                    CalendarConnection.tenant_id == state.tenant_id,
                    CalendarConnection.owner_user_id == locked_owner.id,
                    CalendarConnection.provider == provider,
                )
                .with_for_update()
            )

            if connection is None:
                connection = CalendarConnection(
                    tenant_id=state.tenant_id,
                    owner_user_id=locked_owner.id,
                    provider=provider,
                    status=CalendarConnectionStatus.ACTIVE,
                    credential_reference=new_credential_reference,
                )
                session.add(connection)
            else:
                connection.credential_reference = new_credential_reference
                connection.status = CalendarConnectionStatus.ACTIVE

            await session.flush()

            record_audit_event(
                session,
                context=TenantContext(
                    tenant_id=state.tenant_id,
                    subject=locked_owner.external_subject,
                    roles=frozenset(),
                    request_id=request_id,
                ),
                action="calendar_connection.authorized",
                entity_type="calendar_connection",
                entity_id=str(connection.id),
                details={
                    "provider": provider.value,
                    "connection_version": connection.version,
                },
            )
            await session.flush()
            await session.refresh(connection)

    except Exception:
        with suppress(Exception):
            await credential_vault.delete(
                credential_reference=new_credential_reference
            )
        raise

    return connection
