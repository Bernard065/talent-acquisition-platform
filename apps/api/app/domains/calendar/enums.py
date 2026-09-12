"""Provider-neutral calendar integration enumerations."""

from enum import StrEnum


class CalendarProvider(StrEnum):
    """Calendar providers supported by the integration boundary."""

    GOOGLE = "google"
    MICROSOFT = "microsoft"


class CalendarConnectionStatus(StrEnum):
    """Lifecycle state for a tenant user's calendar connection."""

    ACTIVE = "active"
    DISABLED = "disabled"


class InterviewCalendarSyncStatus(StrEnum):
    """Asynchronous synchronization state for one interview calendar event."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    DISABLED = "disabled"
