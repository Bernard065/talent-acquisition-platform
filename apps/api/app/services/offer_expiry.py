"""Database-safe scheduled expiry of sent offers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.offer import Offer, OfferLifecycleHistory
from app.db.transactions import transactional
from app.domains.offers.enums import OfferLifecycleEventType, OfferStatus
from app.domains.offers.transitions import validate_offer_transition
from app.services.audit import record_audit_event

SYSTEM_SUBJECT = "system:offer-expiry-worker"


@dataclass(frozen=True, slots=True)
class OfferExpiryResult:
    """Outcome of one bounded offer-expiry database batch."""

    expired_offer_ids: tuple[UUID, ...]

    @property
    def expired_count(self) -> int:
        """Return the number of offers expired by this batch."""
        return len(self.expired_offer_ids)


def _validate_batch_size(batch_size: int) -> None:
    """Keep one expiry transaction bounded and predictable."""
    if not 1 <= batch_size <= 100:
        raise ValueError("Offer expiry batch size must be between 1 and 100.")


def _resolve_now(now: datetime | None) -> datetime:
    """Return an aware UTC timestamp, accepting an injected test clock."""
    resolved_now = now or datetime.now(UTC)

    if resolved_now.tzinfo is None:
        raise ValueError("Offer expiry time must include a UTC offset.")

    return resolved_now


async def expire_due_offers(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
    request_id: str = "offer-expiry-worker",
) -> OfferExpiryResult:
    """
    Expire one locked batch of due sent offers.

    The claim, status transition, lifecycle history, and audit events commit
    together. PostgreSQL `SKIP LOCKED` permits concurrent worker instances to
    process separate offers without waiting or duplicate processing.
    """
    _validate_batch_size(batch_size)
    expiry_time = _resolve_now(now)

    async with transactional(session):
        offers = list(
            await session.scalars(
                select(Offer)
                .where(
                    Offer.status == OfferStatus.SENT,
                    Offer.expires_at <= expiry_time,
                )
                .order_by(Offer.expires_at, Offer.id)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )

        for offer in offers:
            previous_status = offer.status
            validate_offer_transition(previous_status, OfferStatus.EXPIRED)

            offer.status = OfferStatus.EXPIRED
            offer.expired_at = expiry_time

            session.add(
                OfferLifecycleHistory(
                    tenant_id=offer.tenant_id,
                    offer_id=offer.id,
                    event_type=OfferLifecycleEventType.EXPIRED,
                    from_status=previous_status,
                    to_status=OfferStatus.EXPIRED,
                    occurred_by_subject=SYSTEM_SUBJECT,
                    occurred_at=expiry_time,
                )
            )

        # Flush first so SQLAlchemy increments optimistic-lock versions.
        await session.flush()

        for offer in offers:
            context = TenantContext(
                tenant_id=offer.tenant_id,
                subject=SYSTEM_SUBJECT,
                roles=frozenset(),
                request_id=request_id,
            )
            record_audit_event(
                session,
                context=context,
                action="offer.expired",
                entity_type="offer",
                entity_id=str(offer.id),
                details={
                    "offer_version": offer.version,
                    "expired_at": expiry_time.isoformat(),
                },
            )

        await session.flush()

    return OfferExpiryResult(
        expired_offer_ids=tuple(offer.id for offer in offers),
    )
