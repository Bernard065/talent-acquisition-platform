"""Onboarding workflow enumerations."""

from enum import StrEnum


class OnboardingInstanceStatus(StrEnum):
    """Lifecycle states for onboarding generated from a hired application."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OnboardingTaskStatus(StrEnum):
    """Controlled lifecycle states for one onboarding task."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class OnboardingTaskWorklistView(StrEnum):
    """Saved operational slices available in the workspace task worklist."""

    OPEN = "open"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    COMPLETED = "completed"


class OnboardingTaskDocumentStatus(StrEnum):
    """Lifecycle states for a file attached to an employee onboarding task."""

    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    SCANNING = "scanning"
    AVAILABLE = "available"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class OnboardingTaskDocumentReviewStatus(StrEnum):
    """Human review state after a document passes its security scan."""

    NOT_REQUIRED = "not_required"
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes_requested"


class OnboardingTaskDocumentReviewDecision(StrEnum):
    """Allowed decisions a reviewer can make for a clean document."""

    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes_requested"


class OnboardingTaskResponsibility(StrEnum):
    """Identify whether the employee or workspace team owns a task."""

    WORKSPACE = "workspace"
    EMPLOYEE = "employee"


class OnboardingInstanceEventType(StrEnum):
    """Immutable lifecycle events for an onboarding instance."""

    STARTED = "started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OnboardingTaskEventType(StrEnum):
    """Immutable lifecycle events for one onboarding task."""

    CREATED = "created"
    ASSIGNED = "assigned"
    DUE_DATE_CHANGED = "due_date_changed"
    STATUS_CHANGED = "status_changed"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
