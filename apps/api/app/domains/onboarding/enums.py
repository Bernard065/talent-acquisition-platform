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
