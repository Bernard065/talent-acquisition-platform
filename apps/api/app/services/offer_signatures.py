"""Transactional, tenant-safe offer e-signature workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.offer import Offer
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.db.transactions import transactional
from app.domains.offers.enums import OfferStatus
from app.domains.signatures.enums import (
    OfferSignatureEventType,
    OfferSignatureStatus,
)
from app.domains.signatures.transitions import (
    validate_offer_signature_transition,
)
from app.services.audit import record_audit_event
from app.services.offer_errors import OfferNotFoundError, OfferVersionConflictError
from app.services.offer_signature_errors import (
    OfferSignatureAccessDeniedError,
    OfferSignatureAlreadyExistsError,
    OfferSignatureNotFoundError,
    OfferSignatureValidationError,
    OfferSignatureVersionConflictError,
)
from app.services.outbox import enqueue_outbox_event

_SIGNATURE_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)

_MAX_PROVIDER_LENGTH = 50
_MAX_DOCUMENT_REFERENCE_LENGTH = 255
_MAX_ENVELOPE_REFERENCE_LENGTH = 255


@dataclass(frozen=True, slots=True)
class CreateOfferSignatureRequestCommand:
    """Provider-neutral input for a signature request snapshot."""

    provider: str
    document_reference: str

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        document_reference = self.document_reference.strip()

        if not provider or len(provider) > _MAX_PROVIDER_LENGTH:
            raise OfferSignatureValidationError("Signature provider is invalid.")

        if (
            not document_reference
            or len(document_reference) > _MAX_DOCUMENT_REFERENCE_LENGTH
        ):
            raise OfferSignatureValidationError(
                "Signature document reference is invalid."
            )

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "document_reference", document_reference)


def _require_signature_write_access(context: TenantContext) -> None:
    """Restrict signature administration to offer operations roles."""
    if context.roles.isdisjoint(_SIGNATURE_WRITE_ROLES):
        raise OfferSignatureAccessDeniedError(
            "Caller is not permitted to perform this signature operation."
        )


def _validate_expected_version(
    signature_request: OfferSignatureRequest,
    expected_version: int,
) -> None:
    """Reject stale writes before changing a locked signature request."""
    if expected_version < 1:
        raise OfferSignatureValidationError(
            "Expected signature request version must be at least 1."
        )

    if signature_request.version != expected_version:
        raise OfferSignatureVersionConflictError(
            "Signature request has changed; retrieve it and retry."
        )


async def _reload_signature_request(
    session: AsyncSession,
    *,
    signature_request_id: UUID,
) -> OfferSignatureRequest:
    """Return a fully loaded detached row so callers can access attributes safely."""
    signature_request = await session.get(OfferSignatureRequest, signature_request_id)
    if signature_request is None:
        raise OfferSignatureNotFoundError("Offer signature request was not found.")

    await session.refresh(signature_request)
    session.expunge(signature_request)
    return signature_request


async def _load_signature_request_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
) -> OfferSignatureRequest:
    """Load and lock one signature request within the caller tenant."""
    signature_request = await session.scalar(
        select(OfferSignatureRequest)
        .where(
            OfferSignatureRequest.id == signature_request_id,
            OfferSignatureRequest.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if signature_request is None:
        raise OfferSignatureNotFoundError("Offer signature request was not found.")

    return signature_request


def _append_history(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request: OfferSignatureRequest,
    event_type: OfferSignatureEventType,
    from_status: OfferSignatureStatus | None,
    to_status: OfferSignatureStatus,
) -> None:
    """Append one immutable signature lifecycle history record."""
    session.add(
        OfferSignatureHistory(
            tenant_id=context.tenant_id,
            offer_signature_request_id=signature_request.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            occurred_by_subject=context.subject,
        )
    )


async def create_offer_signature_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
    command: CreateOfferSignatureRequestCommand,
) -> OfferSignatureRequest:
    """Create a draft signature request from an approved offer snapshot."""
    _require_signature_write_access(context)

    async with transactional(session):
        offer = await session.scalar(
            select(Offer)
            .where(
                Offer.id == offer_id,
                Offer.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if offer is None:
            raise OfferNotFoundError("Offer was not found.")

        if offer.version != expected_offer_version:
            raise OfferVersionConflictError(
                "Offer has changed; retrieve it and retry."
            )

        if offer.status is not OfferStatus.APPROVED:
            raise OfferSignatureValidationError(
                "Only approved offers may receive a signature request."
            )

        if offer.expires_at <= datetime.now(UTC):
            raise OfferSignatureValidationError(
                "An expired offer cannot receive a signature request."
            )

        existing_request_id = await session.scalar(
            select(OfferSignatureRequest.id).where(
                OfferSignatureRequest.tenant_id == context.tenant_id,
                OfferSignatureRequest.offer_id == offer.id,
                OfferSignatureRequest.offer_version == offer.version,
            )
        )
        if existing_request_id is not None:
            raise OfferSignatureAlreadyExistsError(
                "This offer version already has a signature request."
            )

        signature_request = OfferSignatureRequest(
            tenant_id=context.tenant_id,
            offer_id=offer.id,
            provider=command.provider,
            document_reference=command.document_reference,
            status=OfferSignatureStatus.DRAFT,
            offer_version=offer.version,
            currency=offer.currency,
            base_salary=offer.base_salary,
            pay_period=offer.pay_period,
            bonus_amount=offer.bonus_amount,
            proposed_start_date=offer.proposed_start_date,
            expires_at=offer.expires_at,
            created_by_subject=context.subject,
        )
        session.add(signature_request)
        await session.flush()

        _append_history(
            session,
            context=context,
            signature_request=signature_request,
            event_type=OfferSignatureEventType.CREATED,
            from_status=None,
            to_status=OfferSignatureStatus.DRAFT,
        )
        record_audit_event(
            session,
            context=context,
            action="offer_signature.created",
            entity_type="offer_signature_request",
            entity_id=str(signature_request.id),
            details={
                "offer_id": str(offer.id),
                "offer_version": offer.version,
                "signature_request_version": signature_request.version,
            },
        )
        enqueue_outbox_event(
            session,
            context=context,
            event_type="offer_signature.requested",
            aggregate_type="offer_signature_request",
            aggregate_id=str(signature_request.id),
            deduplication_key=(
                f"offer-signature-requested:{signature_request.id}:"
                f"{signature_request.version}"
            ),
            payload={
                "offer_signature_request_id": str(signature_request.id),
                "provider": signature_request.provider,
            },
        )

        await session.flush()
        await session.refresh(signature_request)

    return await _reload_signature_request(
        session,
        signature_request_id=signature_request.id,
    )


async def send_offer_signature_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
    provider_envelope_reference: str,
) -> OfferSignatureRequest:
    """Record successful provider submission using an opaque envelope reference."""
    _require_signature_write_access(context)

    envelope_reference = provider_envelope_reference.strip()
    if not envelope_reference or len(envelope_reference) > _MAX_ENVELOPE_REFERENCE_LENGTH:
        raise OfferSignatureValidationError(
            "Provider envelope reference is invalid."
        )

    async with transactional(session):
        signature_request = await _load_signature_request_for_update(
            session,
            context=context,
            signature_request_id=signature_request_id,
        )
        _validate_expected_version(signature_request, expected_version)

        previous_status = signature_request.status
        validate_offer_signature_transition(
            previous_status,
            OfferSignatureStatus.SENT,
        )

        if signature_request.expires_at <= datetime.now(UTC):
            raise OfferSignatureValidationError(
                "An expired offer signature request cannot be sent."
            )

        signature_request.status = OfferSignatureStatus.SENT
        signature_request.sent_at = datetime.now(UTC)
        signature_request.provider_envelope_reference = envelope_reference

        _append_history(
            session,
            context=context,
            signature_request=signature_request,
            event_type=OfferSignatureEventType.SENT,
            from_status=previous_status,
            to_status=signature_request.status,
        )
        record_audit_event(
            session,
            context=context,
            action="offer_signature.sent",
            entity_type="offer_signature_request",
            entity_id=str(signature_request.id),
            details={
                "offer_id": str(signature_request.offer_id),
                "signature_request_version": signature_request.version,
            },
        )

        await session.flush()
        await session.refresh(signature_request)

    return await _reload_signature_request(
        session,
        signature_request_id=signature_request.id,
    )


async def _transition_signature_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
    target_status: OfferSignatureStatus,
    event_type: OfferSignatureEventType,
) -> OfferSignatureRequest:
    """Transition one locked request and record privacy-safe audit metadata."""
    _require_signature_write_access(context)

    async with transactional(session):
        signature_request = await _load_signature_request_for_update(
            session,
            context=context,
            signature_request_id=signature_request_id,
        )
        _validate_expected_version(signature_request, expected_version)

        previous_status = signature_request.status
        validate_offer_signature_transition(previous_status, target_status)

        now = datetime.now(UTC)
        signature_request.status = target_status

        if target_status is OfferSignatureStatus.SIGNED:
            signature_request.signed_at = now
        elif target_status is OfferSignatureStatus.DECLINED:
            signature_request.declined_at = now
        elif target_status is OfferSignatureStatus.VOIDED:
            signature_request.voided_at = now
        elif target_status is OfferSignatureStatus.EXPIRED:
            signature_request.expired_at = now

        _append_history(
            session,
            context=context,
            signature_request=signature_request,
            event_type=event_type,
            from_status=previous_status,
            to_status=target_status,
        )
        record_audit_event(
            session,
            context=context,
            action=f"offer_signature.{event_type.value}",
            entity_type="offer_signature_request",
            entity_id=str(signature_request.id),
            details={
                "offer_id": str(signature_request.offer_id),
                "signature_request_version": signature_request.version,
            },
        )

        await session.flush()
        await session.refresh(signature_request)

    return await _reload_signature_request(
        session,
        signature_request_id=signature_request.id,
    )


async def mark_offer_signature_signed(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
) -> OfferSignatureRequest:
    """Mark a sent signature request as signed after provider verification."""
    return await _transition_signature_request(
        session,
        context=context,
        signature_request_id=signature_request_id,
        expected_version=expected_version,
        target_status=OfferSignatureStatus.SIGNED,
        event_type=OfferSignatureEventType.SIGNED,
    )


async def decline_offer_signature(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
) -> OfferSignatureRequest:
    """Mark a sent signature request as declined."""
    return await _transition_signature_request(
        session,
        context=context,
        signature_request_id=signature_request_id,
        expected_version=expected_version,
        target_status=OfferSignatureStatus.DECLINED,
        event_type=OfferSignatureEventType.DECLINED,
    )


async def void_offer_signature(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
) -> OfferSignatureRequest:
    """Void a draft or sent signature request."""
    return await _transition_signature_request(
        session,
        context=context,
        signature_request_id=signature_request_id,
        expected_version=expected_version,
        target_status=OfferSignatureStatus.VOIDED,
        event_type=OfferSignatureEventType.VOIDED,
    )


async def expire_offer_signature(
    session: AsyncSession,
    *,
    context: TenantContext,
    signature_request_id: UUID,
    expected_version: int,
) -> OfferSignatureRequest:
    """Expire a sent signature request only after its configured deadline."""
    _require_signature_write_access(context)

    async with transactional(session):
        signature_request = await _load_signature_request_for_update(
            session,
            context=context,
            signature_request_id=signature_request_id,
        )
        _validate_expected_version(signature_request, expected_version)

        if signature_request.expires_at > datetime.now(UTC):
            raise OfferSignatureValidationError(
                "Offer signature request expiry has not been reached."
            )

        previous_status = signature_request.status
        validate_offer_signature_transition(
            previous_status,
            OfferSignatureStatus.EXPIRED,
        )

        signature_request.status = OfferSignatureStatus.EXPIRED
        signature_request.expired_at = datetime.now(UTC)

        _append_history(
            session,
            context=context,
            signature_request=signature_request,
            event_type=OfferSignatureEventType.EXPIRED,
            from_status=previous_status,
            to_status=signature_request.status,
        )
        record_audit_event(
            session,
            context=context,
            action="offer_signature.expired",
            entity_type="offer_signature_request",
            entity_id=str(signature_request.id),
            details={
                "offer_id": str(signature_request.offer_id),
                "signature_request_version": signature_request.version,
            },
        )

        await session.flush()
        await session.refresh(signature_request)

    return await _reload_signature_request(
        session,
        signature_request_id=signature_request.id,
    )
