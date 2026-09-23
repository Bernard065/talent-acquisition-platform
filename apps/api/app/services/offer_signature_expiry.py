"""Database-safe scheduled expiry of sent offer signature requests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.db.transactions import transactional
from app.domains.signatures.enums import (
    OfferSignatureEventType,
    OfferSignatureStatus,
)
from app.domains.signatures.transitions import (
    validate_offer_signature_transition,
)
from app.services.audit import record_audit_event

SYSTEM_SUBJECT = "system:offer-signature-expiry-worker"


@dataclass(frozen=True, slots=True)
class OfferSignatureExpiryResult:
    """Outcome of one bounded offer-signature expiry batch."""

    expired_signature_request_ids: tuple[UUID, ...]

    @property
    def expired_count(self) -> int:
        """Return the number of requests expired by this batch."""
        return len(self.expired_signature_request_ids)


def _validate_batch_size(batch_size: int) -> None:
    """Keep one expiry transaction bounded and predictable."""
    if not 1 <= batch_size <= 100:
        raise ValueError(
            "Offer signature expiry batch size must be between 1 and 100."
        )


def _resolve_now(now: datetime | None) -> datetime:
    """Return an aware UTC timestamp, accepting an injected test clock."""
    resolved_now = now or datetime.now(UTC)

    if resolved_now.tzinfo is None:
        raise ValueError(
            "Offer signature expiry time must include a UTC offset."
        )

    return resolved_now.astimezone(UTC)


async def expire_due_offer_signature_requests(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
    request_id: str = "offer-signature-expiry-worker",
) -> OfferSignatureExpiryResult:
    """
    Expire one locked batch of due sent signature requests.

    PostgreSQL `FOR UPDATE SKIP LOCKED` permits concurrent workers to claim
    separate rows without blocking each other. Status, immutable history, and
    audit records are committed atomically.
    """
    _validate_batch_size(batch_size)
    expiry_time = _resolve_now(now)

    async with transactional(session):
        signature_requests = list(
            await session.scalars(
                select(OfferSignatureRequest)
                .where(
                    OfferSignatureRequest.status == OfferSignatureStatus.SENT,
                    OfferSignatureRequest.expires_at <= expiry_time,
                )
                .order_by(
                    OfferSignatureRequest.expires_at,
                    OfferSignatureRequest.id,
                )
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )

        for signature_request in signature_requests:
            previous_status = signature_request.status
            validate_offer_signature_transition(
                previous_status,
                OfferSignatureStatus.EXPIRED,
            )

            signature_request.status = OfferSignatureStatus.EXPIRED
            signature_request.expired_at = expiry_time

            session.add(
                OfferSignatureHistory(
                    tenant_id=signature_request.tenant_id,
                    offer_signature_request_id=signature_request.id,
                    event_type=OfferSignatureEventType.EXPIRED,
                    from_status=previous_status,
                    to_status=OfferSignatureStatus.EXPIRED,
                    occurred_by_subject=SYSTEM_SUBJECT,
                    occurred_at=expiry_time,
                )
            )

        # Flush first so optimistic-lock versions are incremented before audit.
        await session.flush()

        for signature_request in signature_requests:
            record_audit_event(
                session,
                context=TenantContext(
                    tenant_id=signature_request.tenant_id,
                    subject=SYSTEM_SUBJECT,
                    roles=frozenset(),
                    request_id=request_id,
                ),
                action="offer_signature.expired",
                entity_type="offer_signature_request",
                entity_id=str(signature_request.id),
                details={
                    "offer_id": str(signature_request.offer_id),
                    "signature_request_version": signature_request.version,
                    "expired_at": expiry_time.isoformat(),
                },
            )

        await session.flush()

    return OfferSignatureExpiryResult(
        expired_signature_request_ids=tuple(
            signature_request.id for signature_request in signature_requests
        )
    )
