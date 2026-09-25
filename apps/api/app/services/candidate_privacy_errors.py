"""Exceptions raised by candidate consent and privacy lifecycle services."""

from app.services.candidate_errors import CandidateAccessDeniedError


class CandidatePrivacyAccessDeniedError(CandidateAccessDeniedError):
    """Raised when the caller cannot manage candidate privacy state."""


class CandidatePrivacyNotFoundError(LookupError):
    """Raised when a candidate is not active in the caller's tenant."""
