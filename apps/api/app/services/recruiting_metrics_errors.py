"""Errors for privacy-safe recruiting analytics queries."""


class RecruitingMetricsAccessDeniedError(PermissionError):
    """Raised when a caller lacks access to recruiting analytics."""


class RecruitingMetricsValidationError(ValueError):
    """Raised when an analytics query window is invalid."""
