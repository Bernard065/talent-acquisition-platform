"""Reliable outbox-driven orchestration for candidate document malware scans."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.outbox import OutboxEvent
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.candidate_document_errors import CandidateDocumentNotFoundError
from app.services.candidate_documents import get_candidate_document
from app.services.document_scan_errors import CandidateDocumentNotScannableError
from app.services.document_scanning import (
    begin_candidate_document_scan,
    complete_candidate_document_scan,
)
from app.services.malware_scanner import MalwareScanner, MalwareScannerError
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

_SCAN_REQUESTED_EVENT = "candidate_document.scan_requested"
_TERMINAL_DOCUMENT_STATUSES = frozenset(
    {
        CandidateDocumentStatus.AVAILABLE,
        CandidateDocumentStatus.QUARANTINED,
    }
)


@dataclass(frozen=True, slots=True)
class DocumentScanWorkerResult:
    """Aggregate outcome for one worker polling cycle."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


def _worker_context(event: OutboxEvent, worker_id: str) -> TenantContext:
    """Create a trusted internal identity for tenant-scoped worker operations."""
    return TenantContext(
        tenant_id=event.tenant_id,
        subject=f"system:malware-scanner:{worker_id}",
        roles=frozenset({Role.TENANT_ADMIN}),
        request_id=f"outbox:{event.id}",
    )


def _document_id_from_event(event: OutboxEvent) -> UUID:
    """Extract and validate the only payload field required by this worker."""
    value = event.payload.get("document_id")

    if not isinstance(value, str):
        raise ValueError("document_id is missing from scan request event.")

    return UUID(value)


async def process_candidate_document_scan_events(
    session: AsyncSession,
    *,
    worker_id: str,
    scanner: MalwareScanner,
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> DocumentScanWorkerResult:
    """Claim and process a bounded batch of candidate document scan requests."""
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({_SCAN_REQUESTED_EVENT}),
    )

    processed = 0
    retried = 0
    dead_lettered = 0

    for event in events:
        outcome = await _process_scan_event(
            session,
            event=event,
            worker_id=worker_id,
            scanner=scanner,
            policy=policy,
        )

        if outcome == "processed":
            processed += 1
        elif outcome == "retried":
            retried += 1
        else:
            dead_lettered += 1

    return DocumentScanWorkerResult(
        claimed=len(events),
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
    )


async def _process_scan_event(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    worker_id: str,
    scanner: MalwareScanner,
    policy: OutboxWorkerPolicy,
) -> str:
    """Process one leased scan request without exposing provider details."""
    context = _worker_context(event, worker_id)

    try:
        document_id = _document_id_from_event(event)
    except (TypeError, ValueError):
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="invalid_scan_event_payload",
        )
        return "dead_lettered"

    try:
        scan = await begin_candidate_document_scan(
            session,
            context=context,
            document_id=document_id,
        )
        document = await get_candidate_document(
            session,
            context=context,
            document_id=document_id,
        )
    except CandidateDocumentNotFoundError:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="document_not_found",
        )
        return "dead_lettered"
    except CandidateDocumentNotScannableError:
        document = await get_candidate_document(
            session,
            context=context,
            document_id=document_id,
        )

        if document.status in _TERMINAL_DOCUMENT_STATUSES:
            await mark_outbox_event_processed(
                session,
                event_id=event.id,
                worker_id=worker_id,
            )
            return "processed"

        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="document_not_scannable",
        )
        return "dead_lettered"

    try:
        result = await scanner.scan(
            document_id=document.id,
            object_key=document.storage_key,
            content_type=document.declared_content_type,
        )
    except MalwareScannerError:
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="malware_scanner_unavailable",
            policy=policy,
        )
        return "retried"

    await complete_candidate_document_scan(
        session,
        context=context,
        scan_id=scan.id,
        result=result,
    )
    await mark_outbox_event_processed(
        session,
        event_id=event.id,
        worker_id=worker_id,
    )

    return "processed"
