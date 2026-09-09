"""PostgreSQL integration tests for concurrent offer expiry processing."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.functions import count

from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.offer import Offer, OfferLifecycleHistory
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
from app.domains.offers.enums import (
    OfferLifecycleEventType,
    OfferPayPeriod,
    OfferStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.offer_expiry import SYSTEM_SUBJECT, expire_due_offers

_EXPIRY_TIME = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


async def _seed_sent_offers(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    offer_count: int,
    expires_at: datetime,
) -> list[Offer]:
    """Create sent offers on separate applications for expiry processing."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Offer Expiry Tenant {tenant_id.hex[:12]}",
            slug=f"offer-expiry-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    offers: list[Offer] = []

    for position in range(offer_count):
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name=f"Candidate {position}",
            email=f"candidate-{position}-{tenant_id.hex[:8]}@example.test",
            normalized_email=(
                f"candidate-{position}-{tenant_id.hex[:8]}@example.test"
            ),
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title=f"Backend Engineer {position}",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="seed",
        )
        session.add_all([candidate, requisition])
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.OFFER,
            created_by_subject="seed",
        )
        session.add(application)
        await session.flush()

        offer = Offer(
            tenant_id=tenant_id,
            application_id=application.id,
            status=OfferStatus.SENT,
            currency="KES",
            base_salary=Decimal("250000.00"),
            pay_period=OfferPayPeriod.MONTHLY,
            proposed_start_date=_EXPIRY_TIME.date() - timedelta(days=30),
            expires_at=expires_at,
            sent_at=expires_at - timedelta(days=7),
            created_by_subject="seed",
        )
        session.add(offer)
        offers.append(offer)

    await session.commit()
    return offers


@pytest.mark.asyncio
async def test_expires_only_bounded_due_offer_batch(
    session: AsyncSession,
) -> None:
    """Claim at most the requested number of due sent offers per run."""
    tenant_id = uuid4()
    due_offers = await _seed_sent_offers(
        session,
        tenant_id=tenant_id,
        offer_count=3,
        expires_at=_EXPIRY_TIME - timedelta(minutes=1),
    )

    result = await expire_due_offers(
        session,
        batch_size=2,
        now=_EXPIRY_TIME,
    )

    statuses = list(
        await session.scalars(
            select(Offer.status)
            .where(Offer.id.in_([offer.id for offer in due_offers]))
            .order_by(Offer.id)
        )
    )

    assert result.expired_count == 2
    assert len(set(result.expired_offer_ids)) == 2
    assert statuses.count(OfferStatus.EXPIRED) == 2
    assert statuses.count(OfferStatus.SENT) == 1


@pytest.mark.asyncio
async def test_leaves_non_due_sent_offers_unchanged(
    session: AsyncSession,
) -> None:
    """Never expire an offer before its configured expiry instant."""
    tenant_id = uuid4()
    offers = await _seed_sent_offers(
        session,
        tenant_id=tenant_id,
        offer_count=1,
        expires_at=_EXPIRY_TIME + timedelta(minutes=1),
    )

    result = await expire_due_offers(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )

    stored_offer = await session.get(Offer, offers[0].id)

    assert result.expired_count == 0
    assert stored_offer is not None
    assert stored_offer.status is OfferStatus.SENT
    assert stored_offer.expired_at is None


@pytest.mark.asyncio
async def test_concurrent_workers_expire_each_offer_once(
    database_engine: AsyncEngine,
) -> None:
    """Use SKIP LOCKED so concurrent workers process separate due offers."""
    setup_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    tenant_id = uuid4()

    async with setup_factory() as setup_session:
        offers = await _seed_sent_offers(
            setup_session,
            tenant_id=tenant_id,
            offer_count=4,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )

    worker_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async def run_worker(request_id: str) -> tuple[UUID, ...]:
        async with worker_factory() as worker_session:
            result = await expire_due_offers(
                worker_session,
                batch_size=2,
                now=_EXPIRY_TIME,
                request_id=request_id,
            )
            return result.expired_offer_ids

    first_claim, second_claim = await asyncio.gather(
        run_worker("offer-expiry-worker-one"),
        run_worker("offer-expiry-worker-two"),
    )

    claimed_offer_ids = (*first_claim, *second_claim)

    async with worker_factory() as verification_session:
        expired_count = await verification_session.scalar(
            select(count())
            .select_from(Offer)
            .where(
                Offer.id.in_([offer.id for offer in offers]),
                Offer.status == OfferStatus.EXPIRED,
            )
        )
        history_count = await verification_session.scalar(
            select(count())
            .select_from(OfferLifecycleHistory)
            .where(
                OfferLifecycleHistory.offer_id.in_(
                    [offer.id for offer in offers]
                ),
                OfferLifecycleHistory.event_type
                == OfferLifecycleEventType.EXPIRED,
            )
        )
        audit_count = await verification_session.scalar(
            select(count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_id.in_([str(offer.id) for offer in offers]),
                AuditEvent.action == "offer.expired",
            )
        )

    assert len(claimed_offer_ids) == 4
    assert len(set(claimed_offer_ids)) == 4
    assert expired_count == 4
    assert history_count == 4
    assert audit_count == 4


@pytest.mark.asyncio
async def test_repeat_run_is_safe_and_records_private_audit_data(
    session: AsyncSession,
) -> None:
    """A later run sees no terminal offers and does not duplicate audit rows."""
    tenant_id = uuid4()
    offers = await _seed_sent_offers(
        session,
        tenant_id=tenant_id,
        offer_count=1,
        expires_at=_EXPIRY_TIME - timedelta(minutes=1),
    )

    first = await expire_due_offers(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )
    second = await expire_due_offers(
        session,
        batch_size=10,
        now=_EXPIRY_TIME + timedelta(minutes=1),
    )

    stored_offer = await session.get(Offer, offers[0].id)
    history = await session.scalar(
        select(OfferLifecycleHistory).where(
            OfferLifecycleHistory.offer_id == offers[0].id,
            OfferLifecycleHistory.event_type
            == OfferLifecycleEventType.EXPIRED,
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(offers[0].id),
            AuditEvent.action == "offer.expired",
        )
    )

    assert first.expired_offer_ids == (offers[0].id,)
    assert second.expired_count == 0
    assert stored_offer is not None
    assert stored_offer.status is OfferStatus.EXPIRED
    assert stored_offer.expired_at == _EXPIRY_TIME
    assert history is not None
    assert history.occurred_by_subject == SYSTEM_SUBJECT
    assert audit is not None
    assert audit.actor_subject == SYSTEM_SUBJECT
    assert "base_salary" not in audit.details
    assert "bonus_amount" not in audit.details
    assert "equity_summary" not in audit.details


@pytest.mark.asyncio
async def test_rejects_invalid_batch_size(
    session: AsyncSession,
) -> None:
    """Keep individual expiry transactions bounded."""
    with pytest.raises(ValueError, match="batch size"):
        await expire_due_offers(session, batch_size=0, now=_EXPIRY_TIME)

    with pytest.raises(ValueError, match="batch size"):
        await expire_due_offers(session, batch_size=101, now=_EXPIRY_TIME)
