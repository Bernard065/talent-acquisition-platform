"""Notification delivery enumerations."""

from enum import StrEnum


class NotificationChannel(StrEnum):
    """Supported notification delivery channels."""

    EMAIL = "email"


class NotificationStatus(StrEnum):
    """Lifecycle state of one notification delivery intent."""

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
