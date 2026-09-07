"""PostgreSQL integration tests for candidate document malware scan lifecycle."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.models.identity import Tenant
from app.domains.documents.enums import (
    CandidateDocumentScanStatus,
    CandidateDocumentStatus,
    MalwareScanVerdict,
)
from app.services.candidate_document_errors import CandidateDocumentNotFoundError
from app.services.candidates import CreateCandidateCommand, create_candidate
from app.services.document_scan_errors import (
    CandidateDocumentNotScannableError,
    CandidateDocumentScanAlreadyCompletedError,
)
from app.services.document_scanning import (
    begin_candidate_document_scan,
    complete_candidate_document_scan,
)
from app.services.malware_scanner import MalwareScanResult


def _context(tenant_id: UUID) -> TenantContext:
    """Build the trusted identity used by a background malware-scan worker."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="system:malware-scanner:test-worker",
        roles=frozenset({Role.TENANT_ADMIN}),
        request_id="scan-worker-test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Create the tenant required by candidate-document foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


async def _create_candidate(
    session: AsyncSession,
    tenant_id: UUID,
) -> Candidate:
    """Create one candidate using the production candidate service."""
    return await create_candidate(
        session,
        context=_context(tenant_id),
        command=CreateCandidateCommand(
            full_name="Ada Lovelace",
            email=f"ada-{uuid4().hex[:10]}@candidate-tests.com",
            source="employee_referral",
        ),
    )


async def _create_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    status: CandidateDocumentStatus,
) -> CandidateDocument:
    """Persist one document in the exact state needed by a lifecycle test."""
    candidate = await _create_candidate(session, tenant_id)
    document_id = uuid4()

    document = CandidateDocument(
        id=document_id,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        storage_key=(
            f"v1/tenants/{tenant_id}/candidates/{candidate.id}/"
            f"documents/{document_id}/content"
        ),
        original_filename="resume.pdf",
        declared_content_type="application/pdf",
        expected_byte_size=512_000,
        checksum_sha256="a" * 64,
        status=status,
        created_by_subject="recruiter-subject",
    )
    session.add(document)
    await session.commit()

    return document


@pytest.mark.asyncio
async def test_starts_scan_for_uploaded_document_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Transition one uploaded document into scanning exactly once."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(
        session,
        tenant_id=tenant_id,
        status=CandidateDocumentStatus.UPLOADED,
    )

    scan = await begin_candidate_document_scan(
        session,
        context=_context(tenant_id),
        document_id=document.id,
    )
    await session.refresh(document)

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(document.id),
            AuditEvent.action == "candidate_document.scan_started",
        )
    )

    assert scan.status is CandidateDocumentScanStatus.SCANNING
    assert scan.candidate_document_id == document.id
    assert document.status is CandidateDocumentStatus.SCANNING
    assert document.scan_started_at is not None
    assert audit_event is not None
    assert audit_event.details == {"scan_id": str(scan.id)}


@pytest.mark.asyncio
async def test_clean_scan_makes_document_available_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Make a verified clean document eligible for a future download endpoint."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(
        session,
        tenant_id=tenant_id,
        status=CandidateDocumentStatus.UPLOADED,
    )
    scan = await begin_candidate_document_scan(
        session,
        context=_context(tenant_id),
        document_id=document.id,
    )

    completed_scan = await complete_candidate_document_scan(
        session,
        context=_context(tenant_id),
        scan_id=scan.id,
        result=MalwareScanResult(
            verdict=MalwareScanVerdict.CLEAN,
            scanner_name="clamav",
        ),
    )
    await session.refresh(document)

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(document.id),
            AuditEvent.action == "candidate_document.scan_clean",
        )
    )

    assert completed_scan.status is CandidateDocumentScanStatus.CLEAN
    assert completed_scan.scanner_name == "clamav"
    assert completed_scan.detected_signature is None
    assert completed_scan.completed_at is not None
    assert document.status is CandidateDocumentStatus.AVAILABLE
    assert document.scan_completed_at is not None
    assert audit_event is not None
    assert audit_event.details == {
        "scan_id": str(scan.id),
        "scanner_name": "clamav",
        "verdict": "clean",
    }


@pytest.mark.asyncio
async def test_infected_scan_quarantines_document_without_auditing_signature(
    session: AsyncSession,
) -> None:
    """Quarantine infected content and retain the signature internally only."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(
        session,
        tenant_id=tenant_id,
        status=CandidateDocumentStatus.UPLOADED,
    )
    scan = await begin_candidate_document_scan(
        session,
        context=_context(tenant_id),
        document_id=document.id,
    )

    completed_scan = await complete_candidate_document_scan(
        session,
        context=_context(tenant_id),
        scan_id=scan.id,
        result=MalwareScanResult(
            verdict=MalwareScanVerdict.INFECTED,
            scanner_name="clamav",
            detected_signature="Eicar-Test-Signature",
        ),
    )
    await session.refresh(document)

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(document.id),
            AuditEvent.action == "candidate_document.scan_infected",
        )
    )

    assert completed_scan.status is CandidateDocumentScanStatus.INFECTED
    assert completed_scan.detected_signature == "Eicar-Test-Signature"
    assert document.status is CandidateDocumentStatus.QUARANTINED
    assert audit_event is not None
    assert audit_event.details == {
        "scan_id": str(scan.id),
        "scanner_name": "clamav",
        "verdict": "infected",
    }
    assert "Eicar-Test-Signature" not in str(audit_event.details)


@pytest.mark.asyncio
async def test_rejects_invalid_scan_state_transitions(
    session: AsyncSession,
) -> None:
    """Reject scan starts before upload and duplicate scan completion."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)

    pending_document = await _create_document(
        session,
        tenant_id=tenant_id,
        status=CandidateDocumentStatus.PENDING_UPLOAD,
    )

    with pytest.raises(CandidateDocumentNotScannableError):
        await begin_candidate_document_scan(
            session,
            context=_context(tenant_id),
            document_id=pending_document.id,
        )

    uploaded_document = await _create_document(
        session,
        tenant_id=tenant_id,
        status=CandidateDocumentStatus.UPLOADED,
    )
    scan = await begin_candidate_document_scan(
        session,
        context=_context(tenant_id),
        document_id=uploaded_document.id,
    )

    result = MalwareScanResult(
        verdict=MalwareScanVerdict.CLEAN,
        scanner_name="clamav",
    )
    await complete_candidate_document_scan(
        session,
        context=_context(tenant_id),
        scan_id=scan.id,
        result=result,
    )

    with pytest.raises(CandidateDocumentScanAlreadyCompletedError):
        await complete_candidate_document_scan(
            session,
            context=_context(tenant_id),
            scan_id=scan.id,
            result=result,
        )


@pytest.mark.asyncio
async def test_hides_document_from_worker_in_another_tenant(
    session: AsyncSession,
) -> None:
    """Prevent a worker context from scanning a document in another tenant."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, owner_tenant_id)
    await _create_tenant(session, other_tenant_id)

    document = await _create_document(
        session,
        tenant_id=owner_tenant_id,
        status=CandidateDocumentStatus.UPLOADED,
    )

    with pytest.raises(CandidateDocumentNotFoundError):
        await begin_candidate_document_scan(
            session,
            context=_context(other_tenant_id),
            document_id=document.id,
        )

    scans = list(await session.scalars(select(CandidateDocumentScan)))
    assert not scans
