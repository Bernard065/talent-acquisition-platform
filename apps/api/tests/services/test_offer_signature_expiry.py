"""PostgreSQL integration tests for offer-signature expiry processing."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.functions import count

from app.db.models.audit import AuditEvent
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.domains.signatures.enums import (
    OfferSignatureEventType,
    OfferSignatureStatus,
)
from app.services.offer_signature_expiry import (
    SYSTEM_SUBJECT,
    expire_due_offer_signature_requests,
)
from app.services.offer_signatures import (
    CreateOfferSignatureRequestCommand,
    create_offer_signature_request,
    send_offer_signature_request,
)
from tests.services.test_offer_signatures import _context, _seed_approved_offer

_EXPIRY_TIME = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


async def _seed_sent_signature_requests(
    session: AsyncSession,
    *,
    request_count: int,
    expires_at: datetime,
) -> list[OfferSignatureRequest]:
    """Create independently tenant-owned sent requests with a controlled expiry."""
    signature_requests: list[OfferSignatureRequest] = []

    for _ in range(request_count):
        tenant_id = uuid4()
        offer = await _seed_approved_offer(session, tenant_id=tenant_id)
        context = _context(tenant_id)

        draft_request = await create_offer_signature_request(
            session,
            context=context,
            offer_id=offer.id,
            expected_offer_version=offer.version,
            command=CreateOfferSignatureRequestCommand(
                provider="local",
                document_reference="private-document-reference",
            ),
        )
        sent_request = await send_offer_signature_request(
            session,
            context=context,
            signature_request_id=draft_request.id,
            expected_version=draft_request.version,
            provider_envelope_reference=f"envelope-{draft_request.id}",
        )

        stored_request = await session.get(
            OfferSignatureRequest,
            sent_request.id,
        )
        assert stored_request is not None

        # Sending requires a future deadline. Set the controlled test deadline
        # only after the valid sent lifecycle transition has completed.
        stored_request.expires_at = expires_at
        await session.commit()
        await session.refresh(stored_request)

        signature_requests.append(stored_request)

    return signature_requests


@pytest.mark.asyncio
async def test_expires_only_bounded_due_signature_request_batch(
    session: AsyncSession,
) -> None:
    """Expire no more than the requested number of due sent requests."""
    due_requests = await _seed_sent_signature_requests(
        session,
        request_count=3,
        expires_at=_EXPIRY_TIME - timedelta(minutes=1),
    )

    result = await expire_due_offer_signature_requests(
        session,
        batch_size=2,
        now=_EXPIRY_TIME,
    )

    statuses = list(
        await session.scalars(
            select(OfferSignatureRequest.status)
            .where(
                OfferSignatureRequest.id.in_(
                    [request.id for request in due_requests]
                )
            )
            .order_by(OfferSignatureRequest.id)
        )
    )

    assert result.expired_count == 2
    assert len(set(result.expired_signature_request_ids)) == 2
    assert statuses.count(OfferSignatureStatus.EXPIRED) == 2
    assert statuses.count(OfferSignatureStatus.SENT) == 1


@pytest.mark.asyncio
async def test_leaves_non_due_signature_requests_unchanged(
    session: AsyncSession,
) -> None:
    """A sent request remains usable until its exact expiry instant."""
    future_request = (
        await _seed_sent_signature_requests(
            session,
            request_count=1,
            expires_at=_EXPIRY_TIME + timedelta(minutes=1),
        )
    )[0]

    result = await expire_due_offer_signature_requests(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )

    stored_request = await session.get(
        OfferSignatureRequest,
        future_request.id,
    )

    assert result.expired_count == 0
    assert stored_request is not None
    assert stored_request.status is OfferSignatureStatus.SENT
    assert stored_request.expired_at is None


@pytest.mark.asyncio
async def test_concurrent_workers_expire_each_signature_request_once(
    database_engine: AsyncEngine,
) -> None:
    """PostgreSQL SKIP LOCKED divides due work without duplicate processing."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as setup_session:
        due_requests = await _seed_sent_signature_requests(
            setup_session,
            request_count=4,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )

    async def run_worker(request_id: str) -> tuple[UUID, ...]:
        async with session_factory() as worker_session:
            result = await expire_due_offer_signature_requests(
                worker_session,
                batch_size=2,
                now=_EXPIRY_TIME,
                request_id=request_id,
            )
            return result.expired_signature_request_ids

    first_claim, second_claim = await asyncio.gather(
        run_worker("offer-signature-expiry-worker-one"),
        run_worker("offer-signature-expiry-worker-two"),
    )
    claimed_ids = (*first_claim, *second_claim)
    request_ids = [request.id for request in due_requests]

    async with session_factory() as verification_session:
        expired_count = await verification_session.scalar(
            select(count())
            .select_from(OfferSignatureRequest)
            .where(
                OfferSignatureRequest.id.in_(request_ids),
                OfferSignatureRequest.status == OfferSignatureStatus.EXPIRED,
            )
        )
        history_count = await verification_session.scalar(
            select(count())
            .select_from(OfferSignatureHistory)
            .where(
                OfferSignatureHistory.offer_signature_request_id.in_(
                    request_ids
                ),
                OfferSignatureHistory.event_type
                == OfferSignatureEventType.EXPIRED,
            )
        )
        audit_count = await verification_session.scalar(
            select(count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_id.in_([str(request_id) for request_id in request_ids]),
                AuditEvent.action == "offer_signature.expired",
            )
        )

    assert len(claimed_ids) == 4
    assert len(set(claimed_ids)) == 4
    assert expired_count == 4
    assert history_count == 4
    assert audit_count == 4


@pytest.mark.asyncio
async def test_repeat_run_is_safe_and_records_privacy_safe_history_and_audit(
    session: AsyncSession,
) -> None:
    """A terminal request is never expired again or given duplicate records."""
    signature_request = (
        await _seed_sent_signature_requests(
            session,
            request_count=1,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )
    )[0]

    first = await expire_due_offer_signature_requests(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )
    second = await expire_due_offer_signature_requests(
        session,
        batch_size=10,
        now=_EXPIRY_TIME + timedelta(minutes=1),
    )

    stored_request = await session.get(
        OfferSignatureRequest,
        signature_request.id,
    )
    history = await session.scalar(
        select(OfferSignatureHistory).where(
            OfferSignatureHistory.offer_signature_request_id
            == signature_request.id,
            OfferSignatureHistory.event_type
            == OfferSignatureEventType.EXPIRED,
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(signature_request.id),
            AuditEvent.action == "offer_signature.expired",
        )
    )

    assert first.expired_signature_request_ids == (signature_request.id,)
    assert second.expired_count == 0

    assert stored_request is not None
    assert stored_request.status is OfferSignatureStatus.EXPIRED
    assert stored_request.expired_at == _EXPIRY_TIME

    assert history is not None
    assert history.from_status is OfferSignatureStatus.SENT
    assert history.to_status is OfferSignatureStatus.EXPIRED
    assert history.occurred_by_subject == SYSTEM_SUBJECT

    assert audit is not None
    assert audit.actor_subject == SYSTEM_SUBJECT
    assert audit.details["expired_at"] == _EXPIRY_TIME.isoformat()

    rendered_audit = str(audit.details)
    assert "document_reference" not in rendered_audit
    assert "provider_envelope_reference" not in rendered_audit
    assert "base_salary" not in rendered_audit
    assert "bonus_amount" not in rendered_audit


@pytest.mark.asyncio
async def test_rejects_invalid_batch_sizes(session: AsyncSession) -> None:
    """Bound work per transaction to protect database capacity."""
    with pytest.raises(ValueError, match="batch size"):
        await expire_due_offer_signature_requests(
            session,
            batch_size=0,
            now=_EXPIRY_TIME,
        )

    with pytest.raises(ValueError, match="batch size"):
        await expire_due_offer_signature_requests(
            session,
            batch_size=101,
            now=_EXPIRY_TIME,
        )
