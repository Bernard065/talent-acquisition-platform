"""Retry-safe removal of candidate document objects after erasure requests."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate_document import CandidateDocument
from app.db.models.idempotency import IdempotencyRecord
from app.db.transactions import transactional
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.candidate_privacy import complete_candidate_erasure_if_no_documents_remain
from app.services.object_storage import (
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    public_application_resume_scan_object_key,
)
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

_PRIVACY_DELETE_EVENT = "candidate_document.privacy_delete_requested"
_PUBLIC_RESUME_CLEANUP_EVENT = "public_application_resume.cleanup_requested"


@dataclass(frozen=True, slots=True)
class CandidateDocumentErasureResult:
    """Outcome counters for one bounded privacy cleanup poll."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


def _worker_context(
    *,
    tenant_id: UUID,
    event_id: UUID,
    worker_id: str,
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=f"system:candidate-privacy:{worker_id}",
        roles=frozenset({Role.TENANT_ADMIN}),
        request_id=f"outbox:{event_id}",
    )


def _event_identifiers(
    *,
    aggregate_type: str,
    payload: dict[str, object],
) -> tuple[UUID, UUID] | None:
    if aggregate_type != "candidate_document":
        return None
    document_id = payload.get("document_id")
    candidate_id = payload.get("candidate_id")
    if not isinstance(document_id, str) or not isinstance(candidate_id, str):
        return None
    try:
        return UUID(document_id), UUID(candidate_id)
    except ValueError:
        return None


async def process_candidate_document_erasure_events(
    session: AsyncSession,
    *,
    worker_id: str,
    storage: ObjectStorage,
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> CandidateDocumentErasureResult:
    """Claim and process one bounded batch of document erasure events."""
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({_PRIVACY_DELETE_EVENT, _PUBLIC_RESUME_CLEANUP_EVENT}),
    )
    processed = retried = dead_lettered = 0

    event_snapshots = [
        (
            event.id,
            event.tenant_id,
            event.event_type,
            event.aggregate_type,
            dict(event.payload),
        )
        for event in events
    ]
    for event_id, tenant_id, event_type, aggregate_type, payload in event_snapshots:
        if event_type == _PUBLIC_RESUME_CLEANUP_EVENT:
            outcome = await _process_public_resume_cleanup_event(
                session,
                event_id=event_id,
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                payload=payload,
                worker_id=worker_id,
                storage=storage,
                policy=policy,
            )
        else:
            outcome = await _process_event(
                session,
                event_id=event_id,
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                payload=payload,
                worker_id=worker_id,
                storage=storage,
                policy=policy,
            )
        if outcome == "processed":
            processed += 1
        elif outcome == "retried":
            retried += 1
        else:
            dead_lettered += 1

    return CandidateDocumentErasureResult(
        claimed=len(events),
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
    )


async def _process_event(
    session: AsyncSession,
    *,
    event_id: UUID,
    tenant_id: UUID,
    aggregate_type: str,
    payload: dict[str, object],
    worker_id: str,
    storage: ObjectStorage,
    policy: OutboxWorkerPolicy,
) -> str:
    identifiers = _event_identifiers(
        aggregate_type=aggregate_type,
        payload=payload,
    )
    if identifiers is None:
        await dead_letter_outbox_event(
            session,
            event_id=event_id,
            worker_id=worker_id,
            failure_code="invalid_candidate_erasure_event",
        )
        return "dead_lettered"

    document_id, candidate_id = identifiers
    document = await session.scalar(
        select(CandidateDocument)
        .where(
            CandidateDocument.id == document_id,
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.tenant_id == tenant_id,
        )
    )
    if document is not None and document.status is not CandidateDocumentStatus.DELETED:
        await session.rollback()
        await dead_letter_outbox_event(
            session,
            event_id=event_id,
            worker_id=worker_id,
            failure_code="candidate_document_not_erasure_marked",
        )
        return "dead_lettered"

    object_key = document.storage_key if document is not None else None
    # End the read transaction before network I/O. The storage key is immutable;
    # the metadata row is locked and revalidated after object deletion.
    await session.rollback()

    if object_key is not None:
        try:
            await storage.delete_object(object_key=object_key)
        except ObjectStorageError:
            await schedule_outbox_event_retry(
                session,
                event_id=event_id,
                worker_id=worker_id,
                failure_code="candidate_document_delete_unavailable",
                policy=policy,
            )
            return "retried"

    context = _worker_context(
        tenant_id=tenant_id,
        event_id=event_id,
        worker_id=worker_id,
    )
    async with transactional(session):
        current_document = await session.scalar(
            select(CandidateDocument)
            .where(
                CandidateDocument.id == document_id,
                CandidateDocument.candidate_id == candidate_id,
                CandidateDocument.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if current_document is not None:
            await session.delete(current_document)
            await session.flush()

        await complete_candidate_erasure_if_no_documents_remain(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            context=context,
        )
        await mark_outbox_event_processed(
            session,
            event_id=event_id,
            worker_id=worker_id,
        )

    return "processed"


async def _process_public_resume_cleanup_event(
    session: AsyncSession,
    *,
    event_id: UUID,
    tenant_id: UUID,
    aggregate_type: str,
    payload: dict[str, object],
    worker_id: str,
    storage: ObjectStorage,
    policy: OutboxWorkerPolicy,
) -> str:
    """Delete abandoned scan-key objects without touching attached résumés."""
    scan_id_value = payload.get("scan_id")
    proof_key_hash = payload.get("scan_token_hash")
    try:
        if aggregate_type != "public_application_resume_scan" or not isinstance(
            scan_id_value, str
        ) or not isinstance(proof_key_hash, str) or len(proof_key_hash) != 64:
            raise ValueError
        scan_id = UUID(scan_id_value)
    except ValueError:
        await dead_letter_outbox_event(
            session,
            event_id=event_id,
            worker_id=worker_id,
            failure_code="invalid_public_resume_cleanup_event",
        )
        return "dead_lettered"

    object_key = public_application_resume_scan_object_key(
        tenant_id=tenant_id,
        scan_id=scan_id,
    )
    proof = await session.scalar(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.key_hash == proof_key_hash,
        )
        .with_for_update()
    )
    # A successful application atomically consumes the proof and creates a
    # CandidateDocument using this same storage key. Keep that attached object.
    attached_document = await session.scalar(
        select(CandidateDocument.id).where(
            CandidateDocument.tenant_id == tenant_id,
            CandidateDocument.storage_key == object_key,
            CandidateDocument.status != CandidateDocumentStatus.DELETED,
        )
    )
    if attached_document is None:
        try:
            await storage.delete_object(object_key=object_key)
        except ObjectNotFoundError:
            pass
        except ObjectStorageError:
            await schedule_outbox_event_retry(
                session,
                event_id=event_id,
                worker_id=worker_id,
                failure_code="public_resume_delete_unavailable",
                policy=policy,
            )
            return "retried"

    async with transactional(session):
        if proof is not None:
            await session.delete(proof)
        await mark_outbox_event_processed(
            session,
            event_id=event_id,
            worker_id=worker_id,
        )
    return "processed"
