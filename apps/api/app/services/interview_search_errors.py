"""Errors for tenant-scoped interview schedule read models."""


class InterviewSearchAccessDeniedError(PermissionError):
    """Raised when a caller cannot view the requested interview schedule."""


class InvalidInterviewSearchCursorError(ValueError):
    """Raised when interview-search keyset pagination state is invalid."""


class InterviewSearchValidationError(ValueError):
    """Raised when interview calendar search filters are semantically invalid."""
