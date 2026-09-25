"""Candidate and application workflow enumerations."""

from enum import StrEnum


class CandidateConsentStatus(StrEnum):
    """Candidate consent state for data-processing purposes."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class CandidatePrivacyStatus(StrEnum):
    """Lifecycle state for candidate personal data and erasure processing."""

    ACTIVE = "active"
    ERASURE_PENDING = "erasure_pending"
    ERASED = "erased"


class ApplicationStatus(StrEnum):
    """Applicant-tracking pipeline stages."""

    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationRejectionReason(StrEnum):
    """Controlled reasons for rejecting an application."""

    NOT_QUALIFIED = "not_qualified"
    BETTER_MATCHED_CANDIDATE = "better_matched_candidate"
    FAILED_ASSESSMENT = "failed_assessment"
    COMPENSATION_MISMATCH = "compensation_mismatch"
    ROLE_CLOSED = "role_closed"
    OTHER = "other"
