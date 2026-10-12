"""Errors raised by application follow-up services."""


class ApplicationFollowUpAccessDeniedError(PermissionError):
    """Raised when a caller cannot manage follow-ups for an application."""


class ApplicationFollowUpNotFoundError(LookupError):
    """Raised when an application or follow-up is outside the tenant scope."""


class ActiveApplicationFollowUpExistsError(RuntimeError):
    """Raised when an application already has a pending follow-up."""


class ApplicationFollowUpVersionConflictError(RuntimeError):
    """Raised when a follow-up changed since it was loaded."""


class ApplicationFollowUpValidationError(ValueError):
    """Raised when follow-up action details are invalid."""
