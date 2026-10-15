"""Employee lifecycle values owned by MindHire."""

from enum import StrEnum


class EmployeeStatus(StrEnum):
    """Lifecycle state for a person hired through a workspace."""

    PREBOARDING = "preboarding"
    ACTIVE = "active"
    INACTIVE = "inactive"

