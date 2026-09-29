"""Provider-neutral contract for downstream candidate-data deletion."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class CandidateProcessorProviderError(RuntimeError):
    """Classified deletion-provider failure safe for retry handling."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CandidateProcessorDeletionCommand:
    """Minimum in-memory metadata needed to delete one remote record.

    No candidate profile data is included. Opaque references and secret-vault
    references must never be logged or copied into audit/outbox payloads.
    """

    deletion_request_id: UUID
    tenant_id: UUID
    processor_code: str
    purpose_code: str
    source_type: str
    source_id: UUID
    external_record_reference: str
    idempotency_key: str
    credential_reference: str | None = None
    calendar_connection_id: UUID | None = None
    interview_session_id: UUID | None = None
    external_calendar_id: str | None = None


class CandidateProcessorDeletionProvider(Protocol):
    """Idempotently delete an opaque record at one named processor."""

    processor_code: str

    async def delete_candidate_data(
        self,
        *,
        command: CandidateProcessorDeletionCommand,
    ) -> None:
        """Delete the referenced record or report a classified failure."""
