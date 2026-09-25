"""PostgreSQL tests for retry-safe removal of candidate document objects."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.candidates.enums import CandidateConsentStatus, CandidatePrivacyStatus
from app.domains.documents.enums import CandidateDocumentStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.candidate_document_erasure_worker import (
    process_candidate_document_erasure_events,
)
from app.services.object_storage import ObjectStorageError
from app.services.outbox_worker import OutboxWorkerPolicy


class FakeObjectStorage:
    """Record deletion calls and optionally simulate a provider outage."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted_keys: list[str] = []

    async def delete_object(self, *, object_key: str) -> None:
        self.deleted_keys.append(object_key)
        if self.fail:
            raise ObjectStorageError("provider failure details must not be persisted")


async def _seed_deletion_event(
    session: AsyncSession,
) -> tuple[UUID, UUID, OutboxEvent, str]:
    tenant_id = uuid4()
    candidate_id = uuid4()
    document_id = uuid4()
    document_key = (
        f"v1/tenants/{tenant_id}/candidates/{candidate_id}/"
        f"documents/{document_id}/content"
    )
    now = datetime.now(UTC)
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Privacy Worker {tenant_id.hex[:10]}",
            slug=f"privacy-worker-{tenant_id.hex[:10]}",
        )
    )
    await session.flush()
    session.add_all(
        [
            Candidate(
                id=candidate_id,
                tenant_id=tenant_id,
                full_name="Erased candidate",
                email=f"erased+{candidate_id.hex}@privacy.invalid",
                normalized_email=f"erased+{candidate_id.hex}@privacy.invalid",
                source="privacy_erasure",
                source_metadata={},
                consent_status=CandidateConsentStatus.WITHDRAWN,
                privacy_status=CandidatePrivacyStatus.ERASURE_PENDING,
                erasure_requested_at=now - timedelta(minutes=20),
                erased_at=None,
                created_by_subject="privacy-subject",
            ),
            CandidateDocument(
                id=document_id,
                tenant_id=tenant_id,
                candidate_id=candidate_id,
                storage_key=document_key,
                original_filename="erased",
                declared_content_type="application/octet-stream",
                expected_byte_size=0,
                checksum_sha256=None,
                status=CandidateDocumentStatus.DELETED,
                deleted_at=now - timedelta(minutes=10),
                created_by_subject="privacy-subject",
            ),
        ]
    )
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="candidate_document.privacy_delete_requested",
        aggregate_type="candidate_document",
        aggregate_id=str(document_id),
        deduplication_key=f"candidate_document.privacy_delete:{document_id}",
        payload={
            "candidate_id": str(candidate_id),
            "document_id": str(document_id),
        },
        next_attempt_at=now - timedelta(seconds=1),
    )
    session.add(event)
    await session.commit()
    return tenant_id, candidate_id, event, document_key


@pytest.mark.asyncio
async def test_removes_object_and_completes_candidate_erasure(
    session: AsyncSession,
) -> None:
    tenant_id, candidate_id, event, document_key = await _seed_deletion_event(session)
    event_id = event.id
    document_id = UUID(event.payload["document_id"])
    storage = FakeObjectStorage()

    result = await process_candidate_document_erasure_events(
        session,
        worker_id="privacy-worker-1",
        storage=storage,
        policy=OutboxWorkerPolicy(batch_size=10),
    )

    assert result.claimed == result.processed == 1
    assert result.retried == result.dead_lettered == 0
    assert storage.deleted_keys == [document_key]
    assert await session.get(CandidateDocument, document_id) is None

    candidate = await session.get(Candidate, candidate_id)
    assert candidate is not None
    assert candidate.tenant_id == tenant_id
    assert candidate.privacy_status is CandidatePrivacyStatus.ERASED
    assert candidate.erased_at is not None

    processed_event = await session.get(OutboxEvent, event_id)
    assert processed_event is not None
    assert processed_event.status is OutboxEventStatus.PROCESSED
    assert processed_event.last_error is None

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate.erasure_completed",
            AuditEvent.entity_id == str(candidate_id),
        )
    )
    assert audit is not None
    assert "@privacy.invalid" not in str(audit.details)


@pytest.mark.asyncio
async def test_retries_storage_failure_without_dropping_database_metadata(
    session: AsyncSession,
) -> None:
    _, _, event, document_key = await _seed_deletion_event(session)
    event_id = event.id
    document_id = UUID(event.payload["document_id"])
    storage = FakeObjectStorage(fail=True)

    result = await process_candidate_document_erasure_events(
        session,
        worker_id="privacy-worker-1",
        storage=storage,
        policy=OutboxWorkerPolicy(batch_size=10),
    )

    assert result.claimed == result.retried == 1
    assert result.processed == result.dead_lettered == 0
    assert storage.deleted_keys == [document_key]

    stored_event = await session.get(OutboxEvent, event_id)
    assert stored_event is not None
    assert stored_event.status is OutboxEventStatus.PENDING
    assert stored_event.last_error == "candidate_document_delete_unavailable"
    assert "provider failure details" not in str(stored_event.last_error)

    document = await session.scalar(
            select(CandidateDocument).where(CandidateDocument.id == document_id)
    )
    assert document is not None
    assert document.status is CandidateDocumentStatus.DELETED
