"""PostgreSQL integration tests for outbox-driven document scan workers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.documents.enums import (
    CandidateDocumentScanStatus,
    CandidateDocumentStatus,
    MalwareScanVerdict,
)
from app.domains.outbox.enums import OutboxEventStatus
from app.services.document_scan_worker import (
    process_candidate_document_scan_events,
)
from app.services.malware_scanner import (
    MalwareScannerError,
    MalwareScanResult,
)
from app.services.outbox_worker import OutboxWorkerPolicy


class FakeMalwareScanner:
    """Controllable scanner implementation that never reads object storage."""

    def __init__(
        self,
        *,
        result: MalwareScanResult | None = None,
        error: MalwareScannerError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def scan(
        self,
        *,
        document_id: UUID,
        object_key: str,
        content_type: str,
    ) -> MalwareScanResult:
        """Record scanner input and return the configured outcome."""
        self.calls.append(
            {
                "document_id": document_id,
                "object_key": object_key,
                "content_type": content_type,
            }
        )

        if self.error is not None:
            raise self.error

        assert self.result is not None
        return self.result


async def _seed_document_and_scan_event(
    session: AsyncSession,
    *,
    document_status: CandidateDocumentStatus = CandidateDocumentStatus.UPLOADED,
    payload: dict[str, Any] | None = None,
) -> tuple[UUID, CandidateDocument, OutboxEvent]:
    """Create a tenant, candidate, document, and pending scan-request event."""
    tenant_id = uuid4()
    candidate_id = uuid4()
    document_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name=f"Scan Worker Tenant {tenant_id.hex[:12]}",
        slug=f"scan-worker-{tenant_id.hex[:12]}",
    )
    candidate = Candidate(
        id=candidate_id,
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:10]}@candidate-tests.com",
        normalized_email=f"ada-{tenant_id.hex[:10]}@candidate-tests.com",
        source="employee_referral",
        source_metadata={},
        consent_status=CandidateConsentStatus.UNKNOWN,
        created_by_subject="recruiter-subject",
    )
    document = CandidateDocument(
        id=document_id,
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        storage_key=(
            f"v1/tenants/{tenant_id}/candidates/{candidate_id}/"
            f"documents/{document_id}/content"
        ),
        original_filename="resume.pdf",
        declared_content_type="application/pdf",
        expected_byte_size=512_000,
        checksum_sha256="a" * 64,
        status=document_status,
        created_by_subject="recruiter-subject",
    )
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="candidate_document.scan_requested",
        aggregate_type="candidate_document",
        aggregate_id=str(document_id),
        deduplication_key=f"candidate_document.scan_requested:{document_id}",
        payload=payload if payload is not None else {"document_id": str(document_id)},
    )

    session.add(tenant)
    await session.flush()
    session.add_all([candidate, document, event])
    await session.commit()

    return tenant_id, document, event


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_document_status", "expected_scan_status", "audit_action"),
    [
        (
            MalwareScanResult(
                verdict=MalwareScanVerdict.CLEAN,
                scanner_name="clamav",
            ),
            CandidateDocumentStatus.AVAILABLE,
            CandidateDocumentScanStatus.CLEAN,
            "candidate_document.scan_clean",
        ),
        (
            MalwareScanResult(
                verdict=MalwareScanVerdict.INFECTED,
                scanner_name="clamav",
                detected_signature="Eicar-Test-Signature",
            ),
            CandidateDocumentStatus.QUARANTINED,
            CandidateDocumentScanStatus.INFECTED,
            "candidate_document.scan_infected",
        ),
    ],
)
async def test_processes_clean_and_infected_scan_results(
    session: AsyncSession,
    result: MalwareScanResult,
    expected_document_status: CandidateDocumentStatus,
    expected_scan_status: CandidateDocumentScanStatus,
    audit_action: str,
) -> None:
    """Persist scanner outcomes and complete the corresponding outbox event."""
    _, document, event = await _seed_document_and_scan_event(session)
    scanner = FakeMalwareScanner(result=result)

    worker_result = await process_candidate_document_scan_events(
        session,
        worker_id="scanner-worker-one",
        scanner=scanner,
    )
    await session.refresh(document)
    await session.refresh(event)

    scan = await session.scalar(
        select(CandidateDocumentScan).where(
            CandidateDocumentScan.candidate_document_id == document.id
        )
    )
    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(document.id),
            AuditEvent.action == audit_action,
        )
    )

    assert worker_result.claimed == 1
    assert worker_result.processed == 1
    assert worker_result.retried == 0
    assert worker_result.dead_lettered == 0
    assert document.status is expected_document_status
    assert event.status is OutboxEventStatus.PROCESSED
    assert len(scanner.calls) == 1

    assert scan is not None
    assert scan.status is expected_scan_status
    assert scan.scanner_name == "clamav"

    assert audit_event is not None
    assert "Eicar-Test-Signature" not in str(audit_event.details)


@pytest.mark.asyncio
async def test_retries_scanner_outage_and_resumes_existing_scan_attempt(
    session: AsyncSession,
) -> None:
    """Keep work retryable when the scanner is unavailable after scan start."""
    _, document, event = await _seed_document_and_scan_event(session)
    retry_policy = OutboxWorkerPolicy(
        batch_size=1,
        max_attempts=3,
        base_retry_delay=timedelta(seconds=1),
        maximum_retry_delay=timedelta(seconds=10),
    )

    unavailable_scanner = FakeMalwareScanner(
        error=MalwareScannerError("scanner temporarily unavailable")
    )
    first_result = await process_candidate_document_scan_events(
        session,
        worker_id="scanner-worker-one",
        scanner=unavailable_scanner,
        policy=retry_policy,
    )
    await session.refresh(document)
    await session.refresh(event)

    assert first_result.retried == 1
    assert document.status is CandidateDocumentStatus.SCANNING
    assert event.status is OutboxEventStatus.PENDING
    assert event.attempts == 1
    assert event.last_error == "malware_scanner_unavailable"

    event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    clean_scanner = FakeMalwareScanner(
        result=MalwareScanResult(
            verdict=MalwareScanVerdict.CLEAN,
            scanner_name="clamav",
        )
    )
    second_result = await process_candidate_document_scan_events(
        session,
        worker_id="scanner-worker-two",
        scanner=clean_scanner,
        policy=retry_policy,
    )
    await session.refresh(document)
    await session.refresh(event)

    scans = list(
        await session.scalars(
            select(CandidateDocumentScan).where(
                CandidateDocumentScan.candidate_document_id == document.id
            )
        )
    )

    assert second_result.processed == 1
    assert document.status is CandidateDocumentStatus.AVAILABLE
    assert event.status is OutboxEventStatus.PROCESSED
    assert event.attempts == 2
    assert len(scans) == 1
    assert scans[0].status is CandidateDocumentScanStatus.CLEAN


@pytest.mark.asyncio
async def test_dead_letters_event_with_invalid_payload(
    session: AsyncSession,
) -> None:
    """Terminally reject corrupt events instead of endlessly retrying them."""
    _, _, event = await _seed_document_and_scan_event(
        session,
        payload={"unexpected": "payload"},
    )
    scanner = FakeMalwareScanner(
        result=MalwareScanResult(
            verdict=MalwareScanVerdict.CLEAN,
            scanner_name="clamav",
        )
    )

    worker_result = await process_candidate_document_scan_events(
        session,
        worker_id="scanner-worker-one",
        scanner=scanner,
    )
    await session.refresh(event)

    assert worker_result.claimed == 1
    assert worker_result.dead_lettered == 1
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "invalid_scan_event_payload"
    assert not scanner.calls


@pytest.mark.asyncio
async def test_marks_terminal_document_replay_as_processed_without_scanning(
    session: AsyncSession,
) -> None:
    """Treat a duplicate event for an already scanned document as harmless."""
    _, document, event = await _seed_document_and_scan_event(
        session,
        document_status=CandidateDocumentStatus.AVAILABLE,
    )
    scanner = FakeMalwareScanner(
        result=MalwareScanResult(
            verdict=MalwareScanVerdict.CLEAN,
            scanner_name="clamav",
        )
    )

    worker_result = await process_candidate_document_scan_events(
        session,
        worker_id="scanner-worker-one",
        scanner=scanner,
    )
    await session.refresh(document)
    await session.refresh(event)

    assert worker_result.processed == 1
    assert worker_result.retried == 0
    assert worker_result.dead_lettered == 0
    assert document.status is CandidateDocumentStatus.AVAILABLE
    assert event.status is OutboxEventStatus.PROCESSED
    assert not scanner.calls
