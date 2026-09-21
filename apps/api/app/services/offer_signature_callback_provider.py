"""Provider-neutral contracts for verified offer-signature callbacks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domains.signatures.enums import OfferSignatureCallbackEventType


@dataclass(frozen=True, slots=True)
class OfferSignatureCallbackVerificationRequest:
    """
    Untrusted inbound callback data supplied to a provider-specific verifier.

    The API must pass the exact raw body and headers. Neither is persisted,
    logged, or copied into audit events.
    """

    raw_body: bytes
    headers: Mapping[str, str]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class VerifiedOfferSignatureCallback:
    """
    Safe callback facts returned only after cryptographic verification.

    `provider_event_id` and `provider_envelope_reference` must be opaque
    provider identifiers. Signer identity, signing URLs, documents, and
    raw provider payload fields must not be returned here.
    """

    provider_event_id: str
    provider_envelope_reference: str
    event_type: OfferSignatureCallbackEventType
    occurred_at: datetime


class OfferSignatureCallbackVerifier(Protocol):
    """
    Verifies callbacks from exactly one configured signature provider.

    Implementations must validate the provider signature, timestamp/replay
    window, and event schema before returning verified callback data.
    """

    provider: str

    async def verify(
        self,
        request: OfferSignatureCallbackVerificationRequest,
    ) -> VerifiedOfferSignatureCallback:
        """Verify raw provider callback data and return safe event metadata."""
