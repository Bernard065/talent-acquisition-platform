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


class NotificationEventType(StrEnum):
    """Workflow events that may create internal notifications."""

    OFFER_APPROVAL_REQUESTED = "offer.approval_requested"
    OFFER_APPROVED = "offer.approved"
    OFFER_SENT = "offer.sent"
    OFFER_ACCEPTED = "offer.accepted"
    ONBOARDING_STARTED = "onboarding.started"
    ONBOARDING_TASK_ASSIGNED = "onboarding.task_assigned"
    ONBOARDING_TASK_BLOCKED = "onboarding.task_blocked"
    ONBOARDING_TASK_COMPLETED = "onboarding.task_completed"
