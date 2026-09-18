"""PostgreSQL tests for offer-signature outbox dispatch."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.offer import Offer
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.offers.enums import OfferPayPeriod, OfferStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.signatures.enums import OfferSignatureStatus
from app.services.offer_signature_dispatch import dispatch_offer_signature_requests
from app.services.offer_signature_provider import (
    CreatedOfferSignatureEnvelope,
    CreateOfferSignatureEnvelopeCommand,
    OfferSignatureProviderError,
)
from app.services.outbox_worker import OutboxWorkerPolicy


@dataclass
class FakeOfferSignatureProvider:
    """In-memory provider that makes request idempotency observable."""

    provider: str = "local"
    fail_with: Exception | None = None
    commands: list[CreateOfferSignatureEnvelopeCommand] = field(default_factory=list)

    async def create_envelope(
        self,
        *,
        command: CreateOfferSignatureEnvelopeCommand,
    ) -> CreatedOfferSignatureEnvelope:
        """Record the command and return a deterministic test envelope."""
        self.commands.append(command)

        if self.fail_with is not None:
            raise self.fail_with

        return CreatedOfferSignatureEnvelope(
            provider_envelope_reference=f"envelope-{command.signature_request_id}"
        )


def _policy() -> OutboxWorkerPolicy:
    return OutboxWorkerPolicy(
        batch_size=10,
        max_attempts=3,
        visibility_timeout=timedelta(minutes=5),
        base_retry_delay=timedelta(seconds=1),
        maximum_retry_delay=timedelta(minutes=1),
    )


@pytest_asyncio.fixture(name="signature_request_with_outbox_event")
async def signature_request_with_outbox_event_fixture(
    session: AsyncSession,
) -> tuple[TenantContext, OfferSignatureRequest, OutboxEvent]:
    """Create one dispatchable signature request and its pending event."""
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Offer Signature Dispatch Tenant",
        slug=f"offer-signature-dispatch-{tenant_id.hex[:12]}",
    )
    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email="ada.lovelace@example.test",
        normalized_email="ada.lovelace@example.test",
        source="test",
        source_metadata={},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="test",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="test",
    )
    session.add(tenant)
    await session.flush()

    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.OFFER,
        created_by_subject="test",
    )
    session.add(application)
    await session.flush()

    expires_at = datetime.now(UTC) + timedelta(days=7)
    offer = Offer(
        tenant_id=tenant_id,
        application_id=application.id,
        status=OfferStatus.APPROVED,
        currency="KES",
        base_salary=Decimal("250000.00"),
        pay_period=OfferPayPeriod.MONTHLY,
        bonus_amount=Decimal("0.00"),
        proposed_start_date=datetime.now(UTC).date(),
        expires_at=expires_at,
        approved_at=datetime.now(UTC),
        created_by_subject="test",
    )
    session.add(offer)
    await session.flush()

    signature_request = OfferSignatureRequest(
        tenant_id=tenant_id,
        offer_id=offer.id,
        provider="local",
        document_reference="offer-document-1",
        status=OfferSignatureStatus.DRAFT,
        offer_version=offer.version,
        currency=offer.currency,
        base_salary=offer.base_salary,
        pay_period=offer.pay_period,
        bonus_amount=offer.bonus_amount,
        proposed_start_date=offer.proposed_start_date,
        expires_at=expires_at,
        created_by_subject="test",
    )
    session.add(signature_request)
    await session.flush()

    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="offer_signature.requested",
        aggregate_type="offer_signature_request",
        aggregate_id=str(signature_request.id),
        deduplication_key=f"offer-signature-requested:{signature_request.id}",
        payload={
            "offer_signature_request_id": str(signature_request.id),
            "provider": "local",
        },
    )
    session.add(event)
    await session.flush()

    context = TenantContext(
        tenant_id=tenant_id,
        subject="test-worker",
        roles=frozenset(),
        request_id="test-request",
    )
    return context, signature_request, event


@pytest.mark.asyncio
async def test_dispatch_sends_request_and_processes_outbox_event(
    session: AsyncSession,
    signature_request_with_outbox_event: tuple[
        TenantContext,
        OfferSignatureRequest,
        OutboxEvent,
    ],
) -> None:
    """The candidate is loaded privately and the event is acknowledged."""

    _, signature_request, event = signature_request_with_outbox_event
    provider = FakeOfferSignatureProvider()

    result = await dispatch_offer_signature_requests(
        session,
        worker_id="test-worker",
        providers={"local": provider},
        policy=_policy(),
    )

    refreshed_signature_request = await session.get(
        OfferSignatureRequest,
        signature_request.id,
    )
    refreshed_event = await session.get(OutboxEvent, event.id)
    assert refreshed_signature_request is not None
    assert refreshed_event is not None
    signature_request = refreshed_signature_request
    event = refreshed_event

    assert result.claimed == 1
    assert result.processed == 1
    assert result.retried == 0
    assert result.dead_lettered == 0

    assert signature_request.status is OfferSignatureStatus.SENT
    assert signature_request.provider_envelope_reference == (
        f"envelope-{signature_request.id}"
    )
    assert event.processed_at is not None

    assert len(provider.commands) == 1
    assert provider.commands[0].signature_request_id == signature_request.id
    assert provider.commands[0].idempotency_key == str(signature_request.id)

    # PII remains in-memory between the service and provider only.
    assert "email" not in event.payload
    assert "full_name" not in event.payload
    assert "document_reference" not in event.payload


@pytest.mark.asyncio
async def test_dispatch_retries_retryable_provider_failures(
    session: AsyncSession,
    signature_request_with_outbox_event: tuple[
        TenantContext,
        OfferSignatureRequest,
        OutboxEvent,
    ],
) -> None:
    """Temporary provider failures retain the event for safe retry."""

    _, signature_request, event = signature_request_with_outbox_event
    provider = FakeOfferSignatureProvider(
        fail_with=OfferSignatureProviderError(
            "provider_unavailable",
            retryable=True,
        )
    )

    result = await dispatch_offer_signature_requests(
        session,
        worker_id="test-worker",
        providers={"local": provider},
        policy=_policy(),
    )

    refreshed_signature_request = await session.get(
        OfferSignatureRequest,
        signature_request.id,
    )
    refreshed_event = await session.get(OutboxEvent, event.id)
    assert refreshed_signature_request is not None
    assert refreshed_event is not None
    signature_request = refreshed_signature_request
    event = refreshed_event

    assert result.retried == 1
    assert signature_request.status is OfferSignatureStatus.DRAFT
    assert event.processed_at is None
    assert event.next_attempt_at > datetime.now(UTC)
    assert event.last_error == "signature_provider_retryable_error"


@pytest.mark.asyncio
async def test_dispatch_dead_letters_terminal_provider_failures(
    session: AsyncSession,
    signature_request_with_outbox_event: tuple[
        TenantContext,
        OfferSignatureRequest,
        OutboxEvent,
    ],
) -> None:
    """Permanent provider failures do not loop indefinitely."""

    _, signature_request, event = signature_request_with_outbox_event
    provider = FakeOfferSignatureProvider(
        fail_with=OfferSignatureProviderError(
            "recipient_rejected",
            retryable=False,
        )
    )

    result = await dispatch_offer_signature_requests(
        session,
        worker_id="test-worker",
        providers={"local": provider},
        policy=_policy(),
    )

    refreshed_signature_request = await session.get(
        OfferSignatureRequest,
        signature_request.id,
    )
    refreshed_event = await session.get(OutboxEvent, event.id)
    assert refreshed_signature_request is not None
    assert refreshed_event is not None
    signature_request = refreshed_signature_request
    event = refreshed_event

    assert result.dead_lettered == 1
    assert signature_request.status is OfferSignatureStatus.DRAFT
    assert event.dead_lettered_at is not None
    assert event.last_error == "signature_provider_terminal_error"
