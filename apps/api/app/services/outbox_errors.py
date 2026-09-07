"""Exceptions raised by transactional outbox worker services."""


class OutboxEventNotFoundError(LookupError):
    """Raised when an outbox event does not exist."""


class OutboxEventLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns an outbox event lease."""
