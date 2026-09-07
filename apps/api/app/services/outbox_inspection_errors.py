"""Exceptions raised by outbox operational-inspection services."""


class OutboxInspectionAccessDeniedError(PermissionError):
    """Raised when a caller is not a tenant administrator."""


class InvalidOutboxCursorError(ValueError):
    """Raised when an outbox pagination cursor is malformed."""
