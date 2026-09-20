"""Provider-neutral contracts for private HRIS employee handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID


class HrisProviderError(RuntimeError):
    """Classified failure returned by an external HRIS provider."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class HrisEmployeeHandoffCommand:
    """
    Private in-memory payload sent to an HRIS provider.

    This data must never be written to outbox payloads, audit events, logs,
    exception messages, or database integration-reference fields.
    """

    hris_handoff_id: UUID
    application_id: UUID
    onboarding_instance_id: UUID
    full_name: str
    email: str
    proposed_start_date: date | None
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValueError("Employee name is required.")

        if not self.email.strip():
            raise ValueError("Employee email is required.")

        if not self.idempotency_key.strip():
            raise ValueError("HRIS provider idempotency key is required.")


@dataclass(frozen=True, slots=True)
class HrisEmployeeHandoffResult:
    """Opaque successful provider result safe to persist."""

    external_employee_reference: str

    def __post_init__(self) -> None:
        if not self.external_employee_reference.strip():
            raise ValueError("External employee reference is required.")


class HrisProviderAdapter(Protocol):
    """
    Provider-specific HRIS boundary.

    Implementations must use the stable idempotency key to create-or-recover
    an employee record after a timeout or process crash.
    """

    provider: str

    async def create_or_update_employee(
        self,
        *,
        command: HrisEmployeeHandoffCommand,
    ) -> HrisEmployeeHandoffResult:
        """Create or recover the employee record idempotently."""
