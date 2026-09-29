"""PostgreSQL tests for durable processor-deletion dispatch and retries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_processor import (
    CandidateProcessorDeletionRequest,
    CandidateProcessorDisclosure,
)
from app.db.models.identity import Tenant
from app.db.models.offer import Offer
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
from app.domains.candidates.processor_data import CandidateProcessorDeletionStatus
from app.domains.offers.enums import OfferPayPeriod, OfferStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.signatures.enums import OfferSignatureStatus
from app.services.candidate_processor_deletion_dispatch import (
    CandidateProcessorDeletionPolicy,
    _Claim,
    _locked_request,
    dispatch_candidate_processor_deletions,
)
from app.services.candidate_processor_errors import (
    CandidateProcessorDeletionLeaseLostError,
)
from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionCommand,
    CandidateProcessorProviderError,
)


class FakeDeletionProvider:
    """Capture privacy-minimal commands and simulate classified outcomes."""

    processor_code = "signature.local"

    def __init__(self, failure: CandidateProcessorProviderError | None = None) -> None:
        self.failure = failure
        self.commands: list[CandidateProcessorDeletionCommand] = []

    async def delete_candidate_data(
        self,
        *,
        command: CandidateProcessorDeletionCommand,
    ) -> None:
        self.commands.append(command)
        if self.failure is not None:
            raise self.failure


async def _seed_request(
    session: AsyncSession,
    *,
    status: str = CandidateProcessorDeletionStatus.PENDING.value,
    locked_at: datetime | None = None,
    locked_by: str | None = None,
    attempt_count: int = 0,
    next_attempt_at: datetime | None = None,
) -> tuple[UUID, CandidateProcessorDeletionRequest, str]:
    """Create an erased profile and one local signature disclosure/request."""
    tenant_id = uuid4()
    now = datetime.now(UTC)
    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Erased candidate",
        email=f"erased+{tenant_id.hex}@privacy.invalid",
        normalized_email=f"erased+{tenant_id.hex}@privacy.invalid",
        source="privacy_erasure",
        source_metadata={},
        consent_status=CandidateConsentStatus.WITHDRAWN,
        created_by_subject="dispatch-test",
    )
    tenant = Tenant(
        id=tenant_id,
        name=f"Dispatch tenant {tenant_id.hex[:10]}",
        slug=f"dispatch-{tenant_id.hex[:10]}",
    )
    session.add(tenant)
    await session.flush()
    session.add(candidate)
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title="Erased role",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="dispatch-test",
    )
    session.add(requisition)
    await session.flush()
    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.OFFER,
        created_by_subject="dispatch-test",
    )
    session.add(application)
    await session.flush()
    offer = Offer(
        tenant_id=tenant_id,
        application_id=application.id,
        status=OfferStatus.APPROVED,
        currency="KES",
        base_salary=Decimal("100000.00"),
        pay_period=OfferPayPeriod.MONTHLY,
        proposed_start_date=now.date() + timedelta(days=14),
        expires_at=now + timedelta(days=14),
        approved_at=now,
        created_by_subject="dispatch-test",
    )
    session.add(offer)
    await session.flush()
    signature_request = OfferSignatureRequest(
        tenant_id=tenant_id,
        offer_id=offer.id,
        provider="local",
        document_reference="private-document-reference",
        status=OfferSignatureStatus.SENT,
        offer_version=offer.version,
        currency="KES",
        base_salary=Decimal("100000.00"),
        pay_period=OfferPayPeriod.MONTHLY,
        proposed_start_date=now.date() + timedelta(days=14),
        expires_at=now + timedelta(days=14),
        sent_at=now,
        created_by_subject="dispatch-test",
    )
    session.add(signature_request)
    await session.flush()

    external_reference = "opaque-local-envelope"
    disclosure = CandidateProcessorDisclosure(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        processor_code="signature.local",
        purpose_code="offer_signature",
        source_type="offer_signature",
        source_id=signature_request.id,
        external_record_reference=external_reference,
    )
    session.add(disclosure)
    await session.flush()
    request = CandidateProcessorDeletionRequest(
        tenant_id=tenant_id,
        disclosure_id=disclosure.id,
        status=status,
        attempt_count=attempt_count,
        next_attempt_at=next_attempt_at or now - timedelta(seconds=1),
        locked_at=locked_at,
        locked_by=locked_by,
        version=1,
    )
    session.add(request)
    await session.commit()
    return tenant_id, request, external_reference


def _policy(
    *,
    batch_size: int = 10,
    max_attempts: int = 4,
    lease_timeout: timedelta = timedelta(minutes=1),
    base_retry_delay: timedelta = timedelta(seconds=2),
    maximum_retry_delay: timedelta = timedelta(seconds=10),
) -> CandidateProcessorDeletionPolicy:
    return CandidateProcessorDeletionPolicy(
        batch_size=batch_size,
        max_attempts=max_attempts,
        lease_timeout=lease_timeout,
        base_retry_delay=base_retry_delay,
        maximum_retry_delay=maximum_retry_delay,
    )


@pytest.mark.asyncio
async def test_success_completes_request_and_clears_external_reference(
    session: AsyncSession,
) -> None:
    tenant_id, request, external_reference = await _seed_request(session)
    provider = FakeDeletionProvider()

    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-1",
        providers={provider.processor_code: provider},
        policy=_policy(),
    )

    await session.refresh(request)
    disclosure = await session.scalar(
        select(CandidateProcessorDisclosure).where(
            CandidateProcessorDisclosure.id == request.disclosure_id,
            CandidateProcessorDisclosure.tenant_id == tenant_id,
        )
    )
    assert result.claimed == result.completed == 1
    assert result.retried == result.exceptions == result.lease_lost == 0
    assert request.status == CandidateProcessorDeletionStatus.COMPLETED.value
    assert request.locked_at is None and request.locked_by is None
    assert disclosure is not None and disclosure.external_record_reference is None
    assert len(provider.commands) == 1
    assert provider.commands[0].external_record_reference == external_reference
    assert not hasattr(provider.commands[0], "candidate_email")

    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(request.id),
            )
        )
    )
    rendered_audits = str([event.details for event in audit_events])
    assert "private-document-reference" not in rendered_audits
    assert external_reference not in rendered_audits
    assert "Erased candidate" not in rendered_audits


@pytest.mark.asyncio
async def test_retryable_provider_failure_schedules_backoff_without_pii(
    session: AsyncSession,
) -> None:
    _, request, _ = await _seed_request(session)
    provider = FakeDeletionProvider(
        CandidateProcessorProviderError("temporary_unavailable", retryable=True)
    )

    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-1",
        providers={provider.processor_code: provider},
        policy=_policy(),
    )

    await session.refresh(request)
    assert result.claimed == result.retried == 1
    assert request.status == CandidateProcessorDeletionStatus.PENDING.value
    assert request.last_failure_code == "temporary_unavailable"
    assert request.locked_at is None and request.locked_by is None
    assert request.next_attempt_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_terminal_provider_failure_records_controlled_exception(
    session: AsyncSession,
) -> None:
    _, request, _ = await _seed_request(session)
    provider = FakeDeletionProvider(
        CandidateProcessorProviderError("permission_denied", retryable=False)
    )

    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-1",
        providers={provider.processor_code: provider},
        policy=_policy(),
    )

    await session.refresh(request)
    assert result.claimed == result.exceptions == 1
    assert request.status == CandidateProcessorDeletionStatus.EXCEPTION.value
    assert request.resolution_code == "provider_terminal_failure"
    assert request.status_changed_at is not None
    assert request.status_changed_by_subject == "system:processor-deletion:privacy-delete-1"
    assert request.locked_at is None and request.locked_by is None


@pytest.mark.asyncio
async def test_unknown_provider_fails_closed_without_provider_call(
    session: AsyncSession,
) -> None:
    _, request, _ = await _seed_request(session)
    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-1",
        providers={},
        policy=_policy(),
    )

    await session.refresh(request)
    assert result.claimed == result.exceptions == 1
    assert request.status == CandidateProcessorDeletionStatus.EXCEPTION.value
    assert request.resolution_code == "provider_not_configured"


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_and_replayed_with_same_idempotency_key(
    session: AsyncSession,
) -> None:
    old_lock = datetime.now(UTC) - timedelta(minutes=5)
    _, request, _ = await _seed_request(
        session,
        status=CandidateProcessorDeletionStatus.PROCESSING.value,
        locked_at=old_lock,
        locked_by="crashed-worker",
        attempt_count=1,
    )
    provider = FakeDeletionProvider()

    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-2",
        providers={provider.processor_code: provider},
        policy=_policy(),
    )

    await session.refresh(request)
    assert result.claimed == result.completed == 1
    assert request.status == CandidateProcessorDeletionStatus.COMPLETED.value
    assert request.attempt_count == 2
    assert provider.commands[0].idempotency_key == (f"candidate-processor-deletion:{request.id}")


@pytest.mark.asyncio
async def test_reclaimed_lease_fences_stale_worker_with_reused_worker_id(
    session: AsyncSession,
) -> None:
    tenant_id, request, _ = await _seed_request(
        session,
        status=CandidateProcessorDeletionStatus.PROCESSING.value,
        locked_at=datetime.now(UTC),
        locked_by="shared-worker-id",
        attempt_count=2,
    )
    request.attempt_count += 1
    await session.commit()
    assert request.version == 2

    with pytest.raises(CandidateProcessorDeletionLeaseLostError):
        await _locked_request(
            session,
            claim=_Claim(
                request_id=request.id,
                tenant_id=tenant_id,
                lease_version=1,
            ),
            worker_id="shared-worker-id",
        )

    await session.rollback()
    await session.refresh(request)
    assert request.status == CandidateProcessorDeletionStatus.PROCESSING.value
    assert request.locked_by == "shared-worker-id"


@pytest.mark.asyncio
async def test_future_retry_is_not_claimed(session: AsyncSession) -> None:
    _, request, _ = await _seed_request(
        session,
        next_attempt_at=datetime.now(UTC) + timedelta(hours=1),
    )
    provider = FakeDeletionProvider()

    result = await dispatch_candidate_processor_deletions(
        session,
        worker_id="privacy-delete-1",
        providers={provider.processor_code: provider},
        policy=_policy(),
    )

    await session.refresh(request)
    assert result.claimed == 0
    assert request.status == CandidateProcessorDeletionStatus.PENDING.value
    assert provider.commands == []
