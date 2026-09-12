"""Provider-neutral calendar event synchronization contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_credentials import ResolvedCalendarCredentials


class CalendarProviderError(RuntimeError):
    """A classified calendar-provider failure safe for worker retry handling."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CalendarEventUpsert:
    """
    Minimal, privacy-safe external calendar event representation.

    This deliberately has no candidate name, email, phone, resume link,
    feedback, decision, or compensation data. Provider-specific adapters may
    later add explicitly approved attendee and content policies at their own
    boundary.
    """

    calendar_connection_id: UUID
    interview_session_id: UUID
    external_calendar_id: str | None
    external_event_id: str | None
    idempotency_key: str
    starts_at: datetime
    ends_at: datetime
    title: str = "Interview"


@dataclass(frozen=True, slots=True)
class CalendarEventReference:
    """Opaque provider reference returned after a successful event upsert."""

    external_event_id: str


@dataclass(frozen=True, slots=True)
class CalendarEventDeletion:
    """Idempotent request to remove an external calendar event."""

    calendar_connection_id: UUID
    interview_session_id: UUID
    external_calendar_id: str | None
    external_event_id: str
    idempotency_key: str


class CalendarEventProvider(Protocol):
    """
    Port implemented by Google and Microsoft adapters.

    Adapters must use `idempotency_key` on every request where the provider
    supports it. When the provider does not expose native idempotency, the
    adapter must implement equivalent deduplication using the stable key.
    """

    provider: CalendarProvider

    async def upsert_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventUpsert,
    ) -> CalendarEventReference:
        """Create or update one provider event idempotently."""

    async def delete_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventDeletion,
    ) -> None:
        """Delete one provider event idempotently."""
