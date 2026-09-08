"""Errors raised by interview session lifecycle services."""


class InterviewLifecycleAccessDeniedError(PermissionError):
    """Raised when a caller cannot manage interview session lifecycle."""


class InterviewSessionNotFoundError(LookupError):
    """Raised when a tenant-scoped interview session cannot be found."""


class InterviewSessionVersionConflictError(ValueError):
    """Raised when an interview changed since the caller last read it."""


class InterviewRescheduleConflictError(ValueError):
    """Raised when rescheduling would double-book a participant."""


class InterviewLifecycleValidationError(ValueError):
    """Raised when lifecycle command input is invalid."""
