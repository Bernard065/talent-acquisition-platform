"""Errors for notification preference operations."""


class NotificationPreferenceAccessDeniedError(PermissionError):
    """Raised when the verified caller has no internal tenant user identity."""


class NotificationPreferenceVersionConflictError(ValueError):
    """Raised when a preference was changed after the caller last read it."""
