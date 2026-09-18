"""Deterministic local-only offer signature provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from app.services.offer_signature_provider import (
    CreatedOfferSignatureEnvelope,
    CreateOfferSignatureEnvelopeCommand,
    OfferSignatureProvider,
)


@dataclass
class LocalOfferSignatureProvider(OfferSignatureProvider):
    """
    Development adapter with deterministic idempotent envelope references.

    It does not send email, create a signing URL, persist candidate data, or
    call any external system. Production providers belong in later adapters.
    """

    provider: str = "local"
    _envelopes: dict[str, CreatedOfferSignatureEnvelope] = field(
        default_factory=dict
    )

    async def create_envelope(
        self,
        *,
        command: CreateOfferSignatureEnvelopeCommand,
    ) -> CreatedOfferSignatureEnvelope:
        """Return one stable opaque envelope reference per idempotency key."""
        existing = self._envelopes.get(command.idempotency_key)
        if existing is not None:
            return existing

        digest = sha256(
            command.idempotency_key.encode("utf-8")
        ).hexdigest()

        envelope = CreatedOfferSignatureEnvelope(
            provider_envelope_reference=f"local-envelope-{digest}",
        )
        self._envelopes[command.idempotency_key] = envelope

        return envelope
