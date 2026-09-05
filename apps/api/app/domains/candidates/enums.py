"""Candidate and application workflow enumerations."""

from enum import StrEnum


class CandidateConsentStatus(StrEnum):
    """Candidate consent state for data-processing purposes."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class ApplicationStatus(StrEnum):
    """Initial applicant-tracking status values."""

    APPLIED = "applied"
