"""Typed errors for purpose-specific talent-pool consent operations."""


class CandidateTalentPoolConsentAccessDeniedError(PermissionError):
    """Raised when the caller cannot record candidate purpose consent."""


class CandidateTalentPoolConsentNotFoundError(LookupError):
    """Raised when a candidate is absent from the caller's tenant."""


class CandidateTalentPoolConsentStateError(ValueError):
    """Raised when a grant, renewal, or withdrawal is invalid for current state."""


class CandidateTalentPoolConsentValidationError(ValueError):
    """Raised when consent provenance fields are invalid."""
