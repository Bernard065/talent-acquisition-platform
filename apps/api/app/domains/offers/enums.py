"""Offer workflow enumerations."""

from enum import StrEnum


class OfferStatus(StrEnum):
    """Lifecycle states for a candidate offer."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OfferPayPeriod(StrEnum):
    """Frequency used to interpret the base compensation amount."""

    MONTHLY = "monthly"
    ANNUALLY = "annually"


class OfferLifecycleEventType(StrEnum):
    """Immutable events that record the offer lifecycle."""

    CREATED = "created"
    SUBMITTED_FOR_APPROVAL = "submitted_for_approval"
    APPROVED = "approved"
    APPROVAL_REJECTED = "approval_rejected"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
