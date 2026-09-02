"""Enumerations for the requisition domain."""

from enum import StrEnum


class RequisitionStatus(StrEnum):
    """Lifecycle states for a job requisition."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    OPEN = "open"
    ON_HOLD = "on_hold"
    CLOSED = "closed"
    CANCELLED = "cancelled"
