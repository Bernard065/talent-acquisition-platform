"""HRIS integration lifecycle enumerations."""

from enum import StrEnum


class HrisProvider(StrEnum):
    """
    Provider identity for an HRIS connection.

    These labels do not imply that an adapter exists yet. The eventual worker
    uses a provider-neutral port and selects an adapter at runtime.
    """

    BAMBOOHR = "bamboohr"
    HIBOB = "hibob"
    WORKDAY = "workday"
    CUSTOM = "custom"


class HrisConnectionStatus(StrEnum):
    """Administrative availability of one tenant-owned HRIS connection."""

    ACTIVE = "active"
    DISABLED = "disabled"


class HrisHandoffStatus(StrEnum):
    """Retry-safe lifecycle state for one onboarding-to-HRIS handoff."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    FAILED = "failed"
