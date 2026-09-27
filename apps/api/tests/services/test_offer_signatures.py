"""PostgreSQL integration tests for the offer signature workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_processor import CandidateProcessorDisclosure
from app.db.models.identity import Tenant
from app.db.models.offer import Offer
from app.db.models.offer_signature import OfferSignatureHistory
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.offers.enums import OfferPayPeriod, OfferStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.signatures.enums import OfferSignatureStatus
from app.services.offer_errors import OfferSignatureRequiredError
from app.services.offer_signature_errors import (
    OfferSignatureAccessDeniedError,
    OfferSignatureNotFoundError,
    OfferSignatureVersionConflictError,
)
from app.services.offer_signatures import (
    CreateOfferSignatureRequestCommand,
    create_offer_signature_request,
    mark_offer_signature_signed,
    send_offer_signature_request,
)
from app.services.offers import accept_offer, send_offer


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for offer signature tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="offer-signature-service-test-request",
    )


async def _seed_approved_offer(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> Offer:
    """Create one tenant-owned approved offer ready for signature."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Signature Tenant {tenant_id.hex[:12]}",
            slug=f"signature-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
        source="employee_referral",
        source_metadata={},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="recruiter-subject",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="recruiter-subject",
    )
    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.OFFER,
        created_by_subject="recruiter-subject",
    )
    session.add(application)
    await session.flush()

    offer = Offer(
        tenant_id=tenant_id,
        application_id=application.id,
        status=OfferStatus.APPROVED,
        currency="KES",
        base_salary=Decimal("250000.00"),
        bonus_amount=Decimal("20000.00"),
        pay_period=OfferPayPeriod.MONTHLY,
        proposed_start_date=datetime.now(UTC).date() + timedelta(days=30),
        expires_at=datetime.now(UTC) + timedelta(days=14),
        approved_at=datetime.now(UTC),
        created_by_subject="recruiter-subject",
    )
    session.add(offer)
    await session.commit()

    return offer


async def _install_history_immutability_trigger(
    session: AsyncSession,
) -> None:
    """Install the production trigger in metadata-based integration tests."""
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION
            prevent_offer_signature_history_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'offer signature history is immutable';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER trg_prevent_offer_signature_history_mutation
            BEFORE UPDATE OR DELETE ON offer_signature_history
            FOR EACH ROW
            EXECUTE FUNCTION prevent_offer_signature_history_mutation();
            """
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_creates_immutable_offer_snapshot_and_safe_outbox_event(
    session: AsyncSession,
) -> None:
    """Snapshot terms privately while keeping audit and outbox data safe."""
    tenant_id = uuid4()
    offer = await _seed_approved_offer(session, tenant_id=tenant_id)

    signature_request = await create_offer_signature_request(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="example-sign",
            document_reference="offer-document-opaque-reference",
        ),
    )

    history = await session.scalar(
        select(OfferSignatureHistory).where(
            OfferSignatureHistory.offer_signature_request_id
            == signature_request.id
        )
    )
    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "offer_signature.created",
            AuditEvent.entity_id == str(signature_request.id),
        )
    )
    outbox_event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(signature_request.id),
            OutboxEvent.event_type == "offer_signature.requested",
        )
    )

    assert signature_request.status is OfferSignatureStatus.DRAFT
    assert signature_request.offer_version == offer.version
    assert signature_request.currency == offer.currency
    assert signature_request.base_salary == offer.base_salary
    assert signature_request.bonus_amount == offer.bonus_amount
    assert signature_request.proposed_start_date == offer.proposed_start_date

    assert history is not None
    assert history.from_status is None
    assert history.to_status is OfferSignatureStatus.DRAFT

    assert audit_event is not None
    assert outbox_event is not None

    rendered_audit = str(audit_event.details)
    rendered_outbox = str(outbox_event.payload)

    for prohibited_value in (
        "250000",
        "20000",
        "offer-document-opaque-reference",
    ):
        assert prohibited_value not in rendered_audit
        assert prohibited_value not in rendered_outbox


@pytest.mark.asyncio
async def test_requires_signed_request_before_offer_acceptance(
    session: AsyncSession,
) -> None:
    """An offer cannot hire an application until its signature is complete."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    offer = await _seed_approved_offer(session, tenant_id=tenant_id)

    signature_request = await create_offer_signature_request(
        session,
        context=context,
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="example-sign",
            document_reference="offer-document-reference",
        ),
    )

    sent_offer = await send_offer(
        session,
        context=context,
        offer_id=offer.id,
        expected_offer_version=offer.version,
    )

    with pytest.raises(OfferSignatureRequiredError):
        await accept_offer(
            session,
            context=context,
            offer_id=offer.id,
            expected_offer_version=sent_offer.version,
        )

    sent_signature = await send_offer_signature_request(
        session,
        context=context,
        signature_request_id=signature_request.id,
        expected_version=signature_request.version,
        provider_envelope_reference="provider-envelope-opaque-reference",
    )
    disclosure = await session.scalar(
        select(CandidateProcessorDisclosure).where(
            CandidateProcessorDisclosure.source_type == "offer_signature",
            CandidateProcessorDisclosure.source_id == sent_signature.id,
        )
    )

    signed_signature = await mark_offer_signature_signed(
        session,
        context=context,
        signature_request_id=sent_signature.id,
        expected_version=sent_signature.version,
    )

    accepted_offer = await accept_offer(
        session,
        context=context,
        offer_id=offer.id,
        expected_offer_version=sent_offer.version,
    )

    assert signed_signature.status is OfferSignatureStatus.SIGNED
    assert signed_signature.signed_at is not None
    assert disclosure is not None
    assert disclosure.processor_code == "signature.example-sign"
    assert disclosure.purpose_code == "offer_signature"
    assert disclosure.external_record_reference == (
        "provider-envelope-opaque-reference"
    )
    assert accepted_offer.status is OfferStatus.ACCEPTED


@pytest.mark.asyncio
async def test_enforces_authorization_tenant_isolation_and_versions(
    session: AsyncSession,
) -> None:
    """Signature requests remain tenant-scoped and use optimistic concurrency."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    offer = await _seed_approved_offer(session, tenant_id=owner_tenant_id)

    with pytest.raises(OfferSignatureAccessDeniedError):
        await create_offer_signature_request(
            session,
            context=_context(
                owner_tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            offer_id=offer.id,
            expected_offer_version=offer.version,
            command=CreateOfferSignatureRequestCommand(
                provider="example-sign",
                document_reference="offer-document-reference",
            ),
        )

    signature_request = await create_offer_signature_request(
        session,
        context=_context(owner_tenant_id),
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="example-sign",
            document_reference="offer-document-reference",
        ),
    )

    with pytest.raises(OfferSignatureNotFoundError):
        await send_offer_signature_request(
            session,
            context=_context(other_tenant_id),
            signature_request_id=signature_request.id,
            expected_version=signature_request.version,
            provider_envelope_reference="provider-envelope-reference",
        )

    with pytest.raises(OfferSignatureVersionConflictError):
        await send_offer_signature_request(
            session,
            context=_context(owner_tenant_id),
            signature_request_id=signature_request.id,
            expected_version=signature_request.version + 1,
            provider_envelope_reference="provider-envelope-reference",
        )


@pytest.mark.asyncio
async def test_database_trigger_rejects_signature_history_mutation(
    session: AsyncSession,
) -> None:
    """Production trigger prevents bypassing append-only history."""
    tenant_id = uuid4()
    offer = await _seed_approved_offer(session, tenant_id=tenant_id)

    signature_request = await create_offer_signature_request(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="example-sign",
            document_reference="offer-document-reference",
        ),
    )
    await _install_history_immutability_trigger(session)

    history = await session.scalar(
        select(OfferSignatureHistory).where(
            OfferSignatureHistory.offer_signature_request_id
            == signature_request.id
        )
    )
    assert history is not None

    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                """
                UPDATE offer_signature_history
                SET event_type = 'sent'
                WHERE id = :history_id
                """
            ),
            {"history_id": history.id},
        )
        await session.commit()

    await session.rollback()
