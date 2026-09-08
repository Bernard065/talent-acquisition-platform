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


class InterviewCancellationReason(StrEnum):
    """Controlled reason for cancelling a scheduled interview."""

    CANDIDATE_WITHDREW = "candidate_withdrew"
    CANDIDATE_UNAVAILABLE = "candidate_unavailable"
    INTERVIEWER_UNAVAILABLE = "interviewer_unavailable"
    REQUISITION_CLOSED = "requisition_closed"
    SCHEDULING_CONFLICT = "scheduling_conflict"
    OTHER = "other"


class InterviewLifecycleEventType(StrEnum):
    """Append-only events that change an interview session's lifecycle."""

    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterviewFeedbackStatus(StrEnum):
    """Lifecycle state for interviewer feedback."""

    DRAFT = "draft"
    SUBMITTED = "submitted"


class InterviewRecommendation(StrEnum):
    """A controlled hiring recommendation from an interviewer."""

    STRONG_NO = "strong_no"
    NO = "no"
    YES = "yes"
    STRONG_YES = "strong_yes"
