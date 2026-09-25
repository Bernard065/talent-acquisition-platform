"""Purpose-specific candidate consent for future-role talent-pool use."""

from enum import StrEnum


class CandidateTalentPoolConsentEventType(StrEnum):
    """Append-only events that define whether talent-pool consent is active."""

    GRANTED = "granted"
    RENEWED = "renewed"
    WITHDRAWN = "withdrawn"


class CandidateTalentPoolCaptureMethod(StrEnum):
    """Controlled provenance for a consent event; never store narrative text."""

    CANDIDATE_PORTAL = "candidate_portal"
    SIGNED_FORM = "signed_form"
    EMAIL_CONFIRMATION = "email_confirmation"
    RECRUITER_RECORDED = "recruiter_recorded"
    ERASURE_REQUEST = "erasure_request"


def consent_is_active(event_type: CandidateTalentPoolConsentEventType) -> bool:
    """Return whether the latest event establishes current explicit consent."""
    return event_type in {
        CandidateTalentPoolConsentEventType.GRANTED,
        CandidateTalentPoolConsentEventType.RENEWED,
    }
