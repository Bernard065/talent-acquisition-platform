"""PostgreSQL tests for consent withdrawal and candidate erasure requests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.candidates.enums import (
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.candidate_privacy import (
    request_candidate_erasure,
    withdraw_candidate_consent,
)
from app.services.candidate_privacy_errors import (
    CandidatePrivacyAccessDeniedError,
    CandidatePrivacyNotFoundError,
)
from app.services.candidates import CreateCandidateCommand, create_candidate


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject="privacy-admin-subject",
        roles=roles,
        request_id="privacy-test-request",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()


async def _create_candidate(session: AsyncSession, tenant_id: UUID) -> Candidate:
    return await create_candidate(
        session,
        context=_context(tenant_id, frozenset({Role.RECRUITER})),
        command=CreateCandidateCommand(
            full_name="Ada Lovelace",
            email="ada.lovelace@example.com",
            phone="+254700000000",
            location="Nairobi",
            source="employee_referral",
            source_metadata={"referrer": "Grace Hopper"},
            consent_status=CandidateConsentStatus.GRANTED,
        ),
    )


@pytest.mark.asyncio
async def test_withdraws_consent_once_and_preserves_candidate_profile(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)

    await withdraw_candidate_consent(
        session,
        context=_context(tenant_id, frozenset({Role.PEOPLE_OPERATIONS})),
        candidate_id=candidate.id,
    )
    await withdraw_candidate_consent(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    assert candidate.consent_status is CandidateConsentStatus.WITHDRAWN
    assert candidate.consent_updated_at is not None
    assert candidate.privacy_status is CandidatePrivacyStatus.ACTIVE
    events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.consent_withdrawn",
                AuditEvent.entity_id == str(candidate.id),
            )
        )
    )
    assert len(events) == 1
    assert events[0].details == {
        "previous_status": CandidateConsentStatus.GRANTED.value,
        "consent_status": CandidateConsentStatus.WITHDRAWN.value,
    }


@pytest.mark.asyncio
async def test_erasure_anonymizes_candidate_and_queues_document_deletion(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    upload_expiry = datetime.now(UTC) + timedelta(minutes=10)
    documents = [
        CandidateDocument(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            storage_key=(
                f"v1/tenants/{tenant_id}/candidates/{candidate.id}/"
                f"documents/{uuid4()}/content"
            ),
            original_filename="Ada-Lovelace-Resume.pdf",
            declared_content_type="application/pdf",
            expected_byte_size=4096,
            checksum_sha256="a" * 64,
            status=CandidateDocumentStatus.AVAILABLE,
            upload_authorization_expires_at=upload_expiry,
            created_by_subject="privacy-test-subject",
        ),
        CandidateDocument(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            storage_key=(
                f"v1/tenants/{tenant_id}/candidates/{candidate.id}/"
                f"documents/{uuid4()}/content"
            ),
            original_filename="cover-letter.pdf",
            declared_content_type="application/pdf",
            expected_byte_size=1024,
            checksum_sha256="b" * 64,
            status=CandidateDocumentStatus.PENDING_UPLOAD,
            created_by_subject="privacy-test-subject",
        ),
    ]
    session.add_all(documents)
    await session.flush()

    result = await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    assert result.privacy_status is CandidatePrivacyStatus.ERASURE_PENDING
    assert result.consent_status is CandidateConsentStatus.WITHDRAWN
    assert result.full_name == "Erased candidate"
    assert result.email.endswith("@privacy.invalid")
    assert result.normalized_email == result.email.casefold()
    assert result.phone is None
    assert result.location is None
    assert result.source == "privacy_erasure"
    assert result.source_metadata == {}
    assert "ada.lovelace" not in result.email

    queued_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "candidate_document.privacy_delete_requested"
            )
        )
    )
    assert len(queued_events) == len(documents)
    assert all(
        event.payload.keys() == {"candidate_id", "document_id"}
        for event in queued_events
    )
    assert all("Ada-Lovelace" not in str(event.payload) for event in queued_events)
    assert all(event.next_attempt_at >= upload_expiry for event in queued_events)

    stored_documents = list(
        await session.scalars(
            select(CandidateDocument).where(
                CandidateDocument.candidate_id == candidate.id
            )
        )
    )
    assert all(document.status is CandidateDocumentStatus.DELETED for document in stored_documents)
    assert all(document.original_filename == "erased" for document in stored_documents)
    assert all(document.checksum_sha256 is None for document in stored_documents)

    erasure_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate.erasure_requested",
            AuditEvent.entity_id == str(candidate.id),
        )
    )
    assert erasure_audit is not None
    assert erasure_audit.details == {
        "document_count": 2,
        "privacy_status": CandidatePrivacyStatus.ERASURE_PENDING.value,
    }
    assert "ada.lovelace@example.test" not in str(erasure_audit.details)
    assert "Ada Lovelace" not in str(erasure_audit.details)


@pytest.mark.asyncio
async def test_erasure_without_documents_completes_immediately(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)

    result = await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    assert result.privacy_status is CandidatePrivacyStatus.ERASED
    assert result.erasure_requested_at is not None
    assert result.erased_at is not None
    assert not list(await session.scalars(select(OutboxEvent)))


@pytest.mark.asyncio
async def test_erasure_request_is_idempotent_and_tenant_scoped(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    await _create_tenant(session, other_tenant_id)
    candidate = await _create_candidate(session, tenant_id)

    with pytest.raises(CandidatePrivacyNotFoundError):
        await request_candidate_erasure(
            session,
            context=_context(other_tenant_id),
            candidate_id=candidate.id,
        )

    with pytest.raises(CandidatePrivacyAccessDeniedError):
        await request_candidate_erasure(
            session,
            context=_context(tenant_id, frozenset({Role.RECRUITER})),
            candidate_id=candidate.id,
        )

    first = await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )
    requested_at = first.erasure_requested_at
    second = await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    assert second.erasure_requested_at == requested_at
    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.erasure_requested"
            )
        )
    )
    assert len(audit_events) == 1
