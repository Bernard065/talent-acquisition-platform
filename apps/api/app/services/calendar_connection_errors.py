"""Errors for calendar connection authorization workflows."""


class CalendarConnectionAccessDeniedError(PermissionError):
    """Raised when a caller cannot manage their calendar connection."""


class CalendarConnectionValidationError(ValueError):
    """Raised when server-owned OAuth connection input is invalid."""
