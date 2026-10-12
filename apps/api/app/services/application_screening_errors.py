"""Errors raised by recruiter screening assessments."""


class ApplicationScreeningAccessDeniedError(PermissionError):
    """Raised when the caller cannot read or submit screening assessments."""


class ApplicationScreeningConflictError(ValueError):
    """Raised when screening is unavailable or already submitted by the caller."""


class ApplicationScreeningValidationError(ValueError):
    """Raised when scorecard criteria are invalid after normalization."""
