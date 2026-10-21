"""Employee lifecycle values owned by MindHire."""

from enum import StrEnum


class EmployeeStatus(StrEnum):
    """Lifecycle state for a person hired through a workspace."""

    PREBOARDING = "preboarding"
    ACTIVE = "active"
    OFFBOARDING = "offboarding"
    INACTIVE = "inactive"


class EmployeeOffboardingReason(StrEnum):
    """Structured reason for a planned employee departure."""

    RESIGNATION = "resignation"
    RETIREMENT = "retirement"
    REDUNDANCY = "redundancy"
    CONTRACT_END = "contract_end"
    TERMINATION = "termination"
    OTHER = "other"

