"""Provider-neutral OAuth and PKCE contracts for calendar connections."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import SecretStr

from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_credentials import ResolvedCalendarCredentials


class CalendarOAuthError(RuntimeError):
    """A classified OAuth-provider error safe for retry and audit handling."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class CalendarOAuthStateError(ValueError):
    """Raised when OAuth state is missing, expired, invalid, or already used."""


@dataclass(frozen=True, slots=True)
class CalendarOAuthState:
    """
    Server-side state for one short-lived OAuth authorization attempt.

    The PKCE verifier remains server-side only. The browser receives the opaque
    state token and provider authorization URL, never the verifier or tokens.
    """

    tenant_id: UUID
    owner_user_id: UUID
    provider: CalendarProvider
    redirect_uri: str
    code_verifier: SecretStr
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarAuthorizationRequest:
    """Input required to create a provider authorization URL."""

    state_token: str
    redirect_uri: str
    code_challenge: str


@dataclass(frozen=True, slots=True)
class CalendarOAuthCodeExchange:
    """One callback code exchange protected by the original PKCE verifier."""

    authorization_code: SecretStr
    redirect_uri: str
    code_verifier: SecretStr


class CalendarOAuthStateStore(Protocol):
    """
    One-time server-side OAuth state storage.

    Implementations must atomically consume state: a state token may succeed
    once only, must expire automatically, and must not be logged.
    """

    async def store(
        self,
        *,
        state_token: str,
        state: CalendarOAuthState,
    ) -> None:
        """Store a short-lived authorization state record."""

    async def consume(
        self,
        *,
        state_token: str,
    ) -> CalendarOAuthState:
        """Atomically return and invalidate one unexpired state record."""


class CalendarOAuthProvider(Protocol):
    """
    Provider-specific OAuth adapter implemented later for Google or Microsoft.

    Client secrets belong to adapter configuration or a secret manager, never
    to API requests, database rows, outbox payloads, or audit events.
    """

    provider: CalendarProvider

    async def create_authorization_url(
        self,
        *,
        request: CalendarAuthorizationRequest,
    ) -> str:
        """Return a provider authorization URL using authorization-code PKCE."""

    async def exchange_code(
        self,
        *,
        exchange: CalendarOAuthCodeExchange,
    ) -> ResolvedCalendarCredentials:
        """Exchange one authorization code for in-memory credentials only."""
