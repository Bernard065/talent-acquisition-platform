"""Provider-neutral contracts for offer e-signature envelope dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class OfferSignatureProviderError(RuntimeError):
    """Classified external signature-provider failure."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class OfferSignatureRecipient:
    """
    Candidate identity required by an external signature provider.

    This data is used in memory only. It must never be written to audit events,
    outbox payloads, worker logs, or provider-envelope references.
    """

    full_name: str
    email: str

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValueError("Signature recipient name is required.")

        if not self.email.strip():
            raise ValueError("Signature recipient email is required.")


@dataclass(frozen=True, slots=True)
class CreateOfferSignatureEnvelopeCommand:
    """
    Provider-neutral request to create one candidate signature envelope.

    The idempotency key is the signature-request ID. Providers must return the
    same envelope when the worker retries after an uncertain outcome.
    """

    signature_request_id: UUID
    document_reference: str
    recipient: OfferSignatureRecipient
    expires_at: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.document_reference.strip():
            raise ValueError("Signature document reference is required.")

        if not self.idempotency_key.strip():
            raise ValueError("Signature provider idempotency key is required.")

        if self.expires_at.tzinfo is None:
            raise ValueError("Signature expiry must include a UTC offset.")


@dataclass(frozen=True, slots=True)
class CreatedOfferSignatureEnvelope:
    """Opaque provider result safe for database persistence."""

    provider_envelope_reference: str

    def __post_init__(self) -> None:
        if not self.provider_envelope_reference.strip():
            raise ValueError("Provider envelope reference is required.")


class OfferSignatureProvider(Protocol):
    """External e-signature provider boundary."""

    provider: str

    async def create_envelope(
        self,
        *,
        command: CreateOfferSignatureEnvelopeCommand,
    ) -> CreatedOfferSignatureEnvelope:
        """
        Create or recover an envelope idempotently.

        Implementations must not log candidate PII, document references,
        provider access tokens, signing URLs, or raw provider responses.
        """
