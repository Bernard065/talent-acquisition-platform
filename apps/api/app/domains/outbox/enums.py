"""Transactional outbox lifecycle enumerations."""

from enum import StrEnum


class OutboxEventStatus(StrEnum):
    """Delivery state for a reliably persisted integration event."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    DEAD_LETTERED = "dead_lettered"
