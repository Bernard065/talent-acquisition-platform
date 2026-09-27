"""External processor disclosure and deletion workflow enumerations."""

from enum import StrEnum


class CandidateProcessorPurpose(StrEnum):
    """Purpose categories for candidate-linked external processing."""

    INTERVIEW_SCHEDULING = "interview_scheduling"
    OFFER_SIGNATURE = "offer_signature"
    ONBOARDING_HANDOFF = "onboarding_handoff"


class CandidateProcessorDisclosureSource(StrEnum):
    """Durable application record that caused a processor disclosure."""

    CALENDAR_SYNC = "calendar_sync"
    OFFER_SIGNATURE = "offer_signature"
    HRIS_HANDOFF = "hris_handoff"


class CandidateProcessorDeletionStatus(StrEnum):
    """Operational status of one downstream deletion request."""

    PENDING = "pending"
    COMPLETED = "completed"
    EXCEPTION = "exception"
    WAIVED = "waived"
