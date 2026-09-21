"""Transactional processing for verified offer-signature provider callbacks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.db.models.offer_signature_callback import (
    OfferSignatureCallbackReceipt,
)
from app.db.transactions import transactional
from app.domains.signatures.enums import (
    OfferSignatureCallbackEventType,
    OfferSignatureEventType,
    OfferSignatureStatus,
)
from app.domains.signatures.transitions import (
    InvalidOfferSignatureTransitionError,
    validate_offer_signature_transition,
)
from app.services.audit import record_audit_event
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerificationRequest,
    OfferSignatureCallbackVerifier,
    VerifiedOfferSignatureCallback,
)
from app.services.offer_signature_errors import (
    OfferSignatureCallbackEnvelopeNotFoundError,
    OfferSignatureCallbackReplayMismatchError,
    OfferSignatureCallbackVerificationError,
)

_MAX_PROVIDER_LENGTH = 50
_MAX_PROVIDER_EVENT_ID_LENGTH = 255
_MAX_ENVELOPE_REFERENCE_LENGTH = 255
_CALLBACK_ACTOR_PREFIX = "system:offer-signature-callback"


@dataclass(frozen=True, slots=True)
class OfferSignatureCallbackResult:
    """Outcome of accepting one verified provider callback."""

    receipt_id: UUID
    signature_request_id: UUID
    replayed: bool
    applied: bool


def _normalise_provider(provider: str) -> str:
    normalized = provider.strip().lower()

    if not normalized or len(normalized) > _MAX_PROVIDER_LENGTH:
        raise OfferSignatureCallbackVerificationError(
            "signature_callback_provider_invalid"
        )

    return normalized


def _validate_verified_callback(
    callback: VerifiedOfferSignatureCallback,
) -> None:
    """Validate safe provider facts before they reach persistence."""
    if (
        not callback.provider_event_id.strip()
        or len(callback.provider_event_id) > _MAX_PROVIDER_EVENT_ID_LENGTH
    ):
        raise OfferSignatureCallbackVerificationError(
            "signature_callback_event_id_invalid"
        )

    if (
        not callback.provider_envelope_reference.strip()
        or len(callback.provider_envelope_reference)
        > _MAX_ENVELOPE_REFERENCE_LENGTH
    ):
        raise OfferSignatureCallbackVerificationError(
            "signature_callback_envelope_reference_invalid"
        )

    if callback.occurred_at.tzinfo is None:
        raise OfferSignatureCallbackVerificationError(
            "signature_callback_occurred_at_invalid"
        )


def _callback_context(
    *,
    tenant_id: UUID,
    provider: str,
    request_id: str,
) -> TenantContext:
    """Build a trusted internal actor identity for callback audit events."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=f"{_CALLBACK_ACTOR_PREFIX}:{provider}",
        roles=frozenset({Role.TENANT_ADMIN}),
        request_id=request_id,
    )


def _target_lifecycle_event(
    event_type: OfferSignatureCallbackEventType,
) -> tuple[OfferSignatureStatus, OfferSignatureEventType]:
    """Map a verified provider event to the internal lifecycle."""
    match event_type:
        case OfferSignatureCallbackEventType.SIGNED:
            return OfferSignatureStatus.SIGNED, OfferSignatureEventType.SIGNED
        case OfferSignatureCallbackEventType.DECLINED:
            return OfferSignatureStatus.DECLINED, OfferSignatureEventType.DECLINED
        case OfferSignatureCallbackEventType.VOIDED:
            return OfferSignatureStatus.VOIDED, OfferSignatureEventType.VOIDED


def _receipt_matches(
    receipt: OfferSignatureCallbackReceipt,
    *,
    signature_request_id: UUID,
    callback: VerifiedOfferSignatureCallback,
    payload_sha256: str,
) -> bool:
    """Detect attempts to mutate an already accepted provider event ID."""
    return (
        receipt.offer_signature_request_id == signature_request_id
        and receipt.provider_envelope_reference
        == callback.provider_envelope_reference.strip()
        and receipt.event_type is callback.event_type
        and receipt.payload_sha256 == payload_sha256
    )


async def _find_existing_receipt(
    session: AsyncSession,
    *,
    provider: str,
    provider_event_id: str,
) -> OfferSignatureCallbackReceipt | None:
    """Load an existing receipt solely for durable callback idempotency."""
    result: OfferSignatureCallbackReceipt | None = await session.scalar(
        select(OfferSignatureCallbackReceipt).where(
            OfferSignatureCallbackReceipt.provider == provider,
            OfferSignatureCallbackReceipt.provider_event_id == provider_event_id,
        )
    )
    return result


async def process_offer_signature_callback(
    session: AsyncSession,
    *,
    provider: str,
    verifier: OfferSignatureCallbackVerifier,
    verification_request: OfferSignatureCallbackVerificationRequest,
    request_id: str,
) -> OfferSignatureCallbackResult:
    """
    Verify, receipt, and apply one provider callback atomically.

    The verifier handles provider-specific HMAC/public-key and timestamp
    validation. This service persists only a SHA-256 fingerprint of the raw
    body, deduplicates provider events, and appends state/history/audit data
    in the same transaction.
    """
    normalized_provider = _normalise_provider(provider)

    if verifier.provider.strip().lower() != normalized_provider:
        raise OfferSignatureCallbackVerificationError(
            "signature_callback_provider_mismatch"
        )

    callback = await verifier.verify(verification_request)
    _validate_verified_callback(callback)

    provider_event_id = callback.provider_event_id.strip()
    envelope_reference = callback.provider_envelope_reference.strip()
    payload_sha256 = hashlib.sha256(verification_request.raw_body).hexdigest()

    existing_receipt = await _find_existing_receipt(
        session,
        provider=normalized_provider,
        provider_event_id=provider_event_id,
    )
    if existing_receipt is not None:
        if not _receipt_matches(
            existing_receipt,
            signature_request_id=existing_receipt.offer_signature_request_id,
            callback=callback,
            payload_sha256=payload_sha256,
        ):
            raise OfferSignatureCallbackReplayMismatchError(
                "signature_callback_replay_mismatch"
            )

        return OfferSignatureCallbackResult(
            receipt_id=existing_receipt.id,
            signature_request_id=existing_receipt.offer_signature_request_id,
            replayed=True,
            applied=False,
        )

    try:
        async with transactional(session):
            signature_request = await session.scalar(
                select(OfferSignatureRequest)
                .where(
                    OfferSignatureRequest.provider == normalized_provider,
                    OfferSignatureRequest.provider_envelope_reference
                    == envelope_reference,
                )
                .with_for_update()
            )
            if signature_request is None:
                raise OfferSignatureCallbackEnvelopeNotFoundError(
                    "Signature provider envelope was not found."
                )

            existing_receipt = await _find_existing_receipt(
                session,
                provider=normalized_provider,
                provider_event_id=provider_event_id,
            )
            if existing_receipt is not None:
                if not _receipt_matches(
                    existing_receipt,
                    signature_request_id=signature_request.id,
                    callback=callback,
                    payload_sha256=payload_sha256,
                ):
                    raise OfferSignatureCallbackReplayMismatchError(
                        "signature_callback_replay_mismatch"
                    )

                return OfferSignatureCallbackResult(
                    receipt_id=existing_receipt.id,
                    signature_request_id=existing_receipt.offer_signature_request_id,
                    replayed=True,
                    applied=False,
                )

            receipt = OfferSignatureCallbackReceipt(
                tenant_id=signature_request.tenant_id,
                offer_signature_request_id=signature_request.id,
                provider=normalized_provider,
                provider_event_id=provider_event_id,
                provider_envelope_reference=envelope_reference,
                event_type=callback.event_type,
                payload_sha256=payload_sha256,
                occurred_at=callback.occurred_at.astimezone(UTC),
            )
            session.add(receipt)

            target_status, lifecycle_event = _target_lifecycle_event(
                callback.event_type
            )
            previous_status = signature_request.status
            applied = True

            try:
                validate_offer_signature_transition(
                    previous_status,
                    target_status,
                )
            except InvalidOfferSignatureTransitionError:
                # A valid late callback is retained to suppress future provider
                # retries, but cannot overwrite a completed local lifecycle.
                applied = False
            else:
                now = datetime.now(UTC)
                signature_request.status = target_status

                if target_status is OfferSignatureStatus.SIGNED:
                    signature_request.signed_at = now
                elif target_status is OfferSignatureStatus.DECLINED:
                    signature_request.declined_at = now
                elif target_status is OfferSignatureStatus.VOIDED:
                    signature_request.voided_at = now

                callback_context = _callback_context(
                    tenant_id=signature_request.tenant_id,
                    provider=normalized_provider,
                    request_id=request_id,
                )
                session.add(
                    OfferSignatureHistory(
                        tenant_id=signature_request.tenant_id,
                        offer_signature_request_id=signature_request.id,
                        event_type=lifecycle_event,
                        from_status=previous_status,
                        to_status=target_status,
                        occurred_by_subject=callback_context.subject,
                        occurred_at=callback.occurred_at.astimezone(UTC),
                    )
                )
                record_audit_event(
                    session,
                    context=callback_context,
                    action=f"offer_signature.{lifecycle_event.value}",
                    entity_type="offer_signature_request",
                    entity_id=str(signature_request.id),
                    details={
                        "signature_request_version": signature_request.version,
                        "source": "provider_callback",
                    },
                )

            await session.flush()
            await session.refresh(receipt)

            return OfferSignatureCallbackResult(
                receipt_id=receipt.id,
                signature_request_id=signature_request.id,
                replayed=False,
                applied=applied,
            )

    except IntegrityError:
        # Handles a concurrent delivery that inserted the same provider event
        # immediately before this transaction committed.
        existing_receipt = await _find_existing_receipt(
            session,
            provider=normalized_provider,
            provider_event_id=provider_event_id,
        )
        if existing_receipt is None:
            raise

        if (
            existing_receipt.provider_envelope_reference != envelope_reference
            or existing_receipt.event_type is not callback.event_type
            or existing_receipt.payload_sha256 != payload_sha256
        ):
            raise OfferSignatureCallbackReplayMismatchError(
                "signature_callback_replay_mismatch"
            ) from None

        return OfferSignatureCallbackResult(
            receipt_id=existing_receipt.id,
            signature_request_id=existing_receipt.offer_signature_request_id,
            replayed=True,
            applied=False,
        )
