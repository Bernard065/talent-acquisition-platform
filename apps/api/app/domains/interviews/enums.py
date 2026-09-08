"""Interview workflow enumerations."""

from enum import StrEnum


class InterviewSessionStatus(StrEnum):
    """Lifecycle state for an interview session."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterviewParticipantRole(StrEnum):
    """Internal role played by a user in an interview session."""

    INTERVIEWER = "interviewer"
    COORDINATOR = "coordinator"
