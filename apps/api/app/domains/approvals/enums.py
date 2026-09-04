"""Approval workflow enumerations."""

from enum import StrEnum


class ApprovalStatus(StrEnum):
    """Overall lifecycle state of a requisition approval instance."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecisionStatus(StrEnum):
    """State of one assigned approver decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
