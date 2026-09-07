"""Transactional lifecycle services for candidate document malware scanning."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.transactions import transactional
from app.domains.documents.enums import (
    CandidateDocumentScanStatus,
    CandidateDocumentStatus,
    MalwareScanVerdict,
)
from app.services.audit import record_audit_event
from app.services.candidate_document_errors import CandidateDocumentNotFoundError
from app.services.document_scan_errors import (
    CandidateDocumentNotScannableError,
    CandidateDocumentScanAlreadyCompletedError,
    CandidateDocumentScanNotFoundError,
)
from app.services.malware_scanner import MalwareScanResult


async def begin_candidate_document_scan(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
) -> CandidateDocumentScan:
    """Move an uploaded document into scanning and create one scan attempt."""
    async with transactional(session):
        document = await session.scalar(
            select(CandidateDocument)
            .where(
                CandidateDocument.id == document_id,
                CandidateDocument.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if document is None:
            raise CandidateDocumentNotFoundError("Candidate document was not found.")

        if document.status is CandidateDocumentStatus.SCANNING:
            existing_scan = await session.scalar(
                select(CandidateDocumentScan)
                .where(
                    CandidateDocumentScan.candidate_document_id == document.id,
                    CandidateDocumentScan.status
                    == CandidateDocumentScanStatus.SCANNING,
                )
                .order_by(CandidateDocumentScan.started_at.desc())
                .with_for_update()
            )
            if existing_scan is None:
                raise CandidateDocumentNotScannableError(
                    "Document scan state is inconsistent."
                )

            return existing_scan

        if document.status is not CandidateDocumentStatus.UPLOADED:
            raise CandidateDocumentNotScannableError(
                "Document is not ready for malware scanning."
            )

        now = datetime.now(UTC)
        document.status = CandidateDocumentStatus.SCANNING
        document.scan_started_at = now

        scan = CandidateDocumentScan(
            tenant_id=context.tenant_id,
            candidate_document_id=document.id,
            status=CandidateDocumentScanStatus.SCANNING,
            started_at=now,
        )
        session.add(scan)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="candidate_document.scan_started",
            entity_type="candidate_document",
            entity_id=str(document.id),
            details={"scan_id": str(scan.id)},
        )

    return scan


async def complete_candidate_document_scan(
    session: AsyncSession,
    *,
    context: TenantContext,
    scan_id: UUID,
    result: MalwareScanResult,
) -> CandidateDocumentScan:
    """Persist a verified scan result and update document availability."""
    async with transactional(session):
        scan = await session.scalar(
            select(CandidateDocumentScan)
            .where(
                CandidateDocumentScan.id == scan_id,
                CandidateDocumentScan.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if scan is None:
            raise CandidateDocumentScanNotFoundError("Document scan was not found.")

        if scan.status is not CandidateDocumentScanStatus.SCANNING:
            raise CandidateDocumentScanAlreadyCompletedError(
                "Document scan has already completed."
            )

        document = await session.scalar(
            select(CandidateDocument)
            .where(
                CandidateDocument.id == scan.candidate_document_id,
                CandidateDocument.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if document is None:
            raise CandidateDocumentNotFoundError("Candidate document was not found.")

        now = datetime.now(UTC)
        scan.scanner_name = result.scanner_name.strip()
        scan.detected_signature = result.detected_signature
        scan.completed_at = now
        document.scan_completed_at = now

        if result.verdict is MalwareScanVerdict.CLEAN:
            scan.status = CandidateDocumentScanStatus.CLEAN
            document.status = CandidateDocumentStatus.AVAILABLE
            audit_action = "candidate_document.scan_clean"
        else:
            scan.status = CandidateDocumentScanStatus.INFECTED
            document.status = CandidateDocumentStatus.QUARANTINED
            audit_action = "candidate_document.scan_infected"

        record_audit_event(
            session,
            context=context,
            action=audit_action,
            entity_type="candidate_document",
            entity_id=str(document.id),
            details={
                "scan_id": str(scan.id),
                "scanner_name": scan.scanner_name,
                "verdict": result.verdict.value,
            },
        )

        await session.flush()

    return scan
