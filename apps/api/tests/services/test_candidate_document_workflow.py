"""PostgreSQL integration tests for candidate document upload workflows."""

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
from app.domains.documents.enums import CandidateDocumentStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.candidate_document_errors import (
    CandidateDocumentNotFoundError,
    CandidateDocumentNotUploadableError,
    CandidateDocumentVerificationError,
)
from app.services.candidate_documents import (
    CreateCandidateDocumentUploadIntentCommand,
    confirm_candidate_document_upload,
    create_candidate_document_upload_intent,
    create_upload_authorization,
)
from app.services.candidates import CreateCandidateCommand, create_candidate
from app.services.object_storage import (
    ObjectStorageError,
    PresignedUpload,
    StoredObjectMetadata,
)


class FakeObjectStorage:
    """In-memory ObjectStorage implementation for workflow tests."""

    def __init__(self) -> None:
        self.upload_requests: list[dict[str, object]] = []
        self.metadata_by_key: dict[str, StoredObjectMetadata] = {}
        self.metadata_error: ObjectStorageError | None = None

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        checksum_sha256: str,
        expires_in: timedelta,
    ) -> PresignedUpload:
        """Return a deterministic upload authorization."""
        self.upload_requests.append(
            {
                "object_key": object_key,
                "content_type": content_type,
                "checksum_sha256": checksum_sha256,
                "expires_in": expires_in,
            }
        )
        return PresignedUpload(
            url="https://storage.example.test/signed-upload",
            required_headers={
                "Content-Type": content_type,
                "x-amz-checksum-sha256": "test-checksum",
            },
            expires_at=datetime.now(UTC) + expires_in,
        )

    async def get_object_metadata(
        self,
        *,
        object_key: str,
    ) -> StoredObjectMetadata:
        """Return configured metadata or a simulated provider failure."""
        if self.metadata_error is not None:
            raise self.metadata_error

        return self.metadata_by_key[object_key]

    async def delete_object(self, *, object_key: str) -> None:
        """Implement the storage contract; deletion is outside this test scope."""


def _context(tenant_id: UUID) -> TenantContext:
    """Build a recruiter context with document-management access."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Create the tenant required by document foreign keys."""
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
    """Create one candidate using the production service."""
    return await create_candidate(
        session,
        context=_context(tenant_id),
        command=CreateCandidateCommand(
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:8]}@candidate-tests.com",
            source="employee_referral",
        ),
    )


async def _create_document(
    session: AsyncSession,
    tenant_id: UUID,
) -> CandidateDocument:
    """Create one pending document with immutable upload expectations."""
    candidate = await _create_candidate(session, tenant_id)

    return await create_candidate_document_upload_intent(
        session,
        context=_context(tenant_id),
        command=CreateCandidateDocumentUploadIntentCommand(
            candidate_id=candidate.id,
            original_filename="resume.pdf",
            declared_content_type="application/pdf",
            expected_byte_size=512_000,
            checksum_sha256="a" * 64,
        ),
    )


@pytest.mark.asyncio
async def test_creates_fresh_upload_authorization_for_pending_document(
    session: AsyncSession,
) -> None:
    """Authorize uploads only while a tenant-owned document is pending."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(session, tenant_id)
    storage = FakeObjectStorage()

    upload = await create_upload_authorization(
        session,
        context=_context(tenant_id),
        document_id=document.id,
        storage=storage,
        expires_in=timedelta(minutes=15),
    )

    assert upload.url == "https://storage.example.test/signed-upload"
    assert storage.upload_requests == [
        {
            "object_key": document.storage_key,
            "content_type": "application/pdf",
            "checksum_sha256": "a" * 64,
            "expires_in": timedelta(minutes=15),
        }
    ]


@pytest.mark.asyncio
async def test_confirms_matching_upload_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Mark a verified upload as uploaded without making it downloadable."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(session, tenant_id)
    storage = FakeObjectStorage()
    storage.metadata_by_key[document.storage_key] = StoredObjectMetadata(
        content_type="application/pdf",
        byte_size=512_000,
        checksum_sha256="a" * 64,
    )

    confirmed = await confirm_candidate_document_upload(
        session,
        context=_context(tenant_id),
        document_id=document.id,
        storage=storage,
    )

    audit_actions = list(
        await session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id == str(document.id))
            .order_by(AuditEvent.occurred_at)
        )
    )
    outbox_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "candidate_document.scan_requested",
                OutboxEvent.aggregate_id == str(document.id),
            )
        )
    )

    assert confirmed.status is CandidateDocumentStatus.UPLOADED
    assert confirmed.uploaded_at is not None
    assert audit_actions == [
        "candidate_document.upload_intent_created",
        "candidate_document.upload_confirmed",
    ]
    assert len(outbox_events) == 1
    assert outbox_events[0].tenant_id == tenant_id
    assert outbox_events[0].status is OutboxEventStatus.PENDING
    assert outbox_events[0].deduplication_key == (
        f"candidate_document.scan_requested:{document.id}"
    )
    assert outbox_events[0].payload == {
        "document_id": str(document.id),
    }


@pytest.mark.asyncio
async def test_rejects_metadata_mismatch_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Fail closed when storage metadata differs from declared expectations."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(session, tenant_id)
    storage = FakeObjectStorage()
    storage.metadata_by_key[document.storage_key] = StoredObjectMetadata(
        content_type="application/pdf",
        byte_size=512_001,
        checksum_sha256="a" * 64,
    )

    rejected = await confirm_candidate_document_upload(
        session,
        context=_context(tenant_id),
        document_id=document.id,
        storage=storage,
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(document.id),
            AuditEvent.action == "candidate_document.upload_rejected",
        )
    )
    scan_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "candidate_document.scan_requested"
            )
        )
    )

    assert rejected.status is CandidateDocumentStatus.REJECTED
    assert audit_event is not None
    assert audit_event.details == {"reason": "metadata_mismatch"}
    assert not scan_events

    with pytest.raises(CandidateDocumentNotUploadableError):
        await create_upload_authorization(
            session,
            context=_context(tenant_id),
            document_id=document.id,
            storage=storage,
            expires_in=timedelta(minutes=15),
        )


@pytest.mark.asyncio
async def test_hides_document_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Prevent another tenant from authorizing or confirming a document."""
    owner_tenant_id = uuid4()
    caller_tenant_id = uuid4()
    await _create_tenant(session, owner_tenant_id)
    await _create_tenant(session, caller_tenant_id)

    document = await _create_document(session, owner_tenant_id)
    storage = FakeObjectStorage()

    with pytest.raises(CandidateDocumentNotFoundError):
        await create_upload_authorization(
            session,
            context=_context(caller_tenant_id),
            document_id=document.id,
            storage=storage,
            expires_in=timedelta(minutes=15),
        )

    assert not storage.upload_requests


@pytest.mark.asyncio
async def test_keeps_document_pending_when_provider_cannot_verify_upload(
    session: AsyncSession,
) -> None:
    """Do not reject a document merely because storage is temporarily unavailable."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    document = await _create_document(session, tenant_id)
    storage = FakeObjectStorage()
    storage.metadata_error = ObjectStorageError("Storage temporarily unavailable.")

    with pytest.raises(CandidateDocumentVerificationError):
        await confirm_candidate_document_upload(
            session,
            context=_context(tenant_id),
            document_id=document.id,
            storage=storage,
        )

    await session.refresh(document)

    upload_audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(document.id),
                AuditEvent.action == "candidate_document.upload_confirmed",
            )
        )
    )
    scan_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "candidate_document.scan_requested"
            )
        )
    )

    assert document.status is CandidateDocumentStatus.PENDING_UPLOAD
    assert not upload_audits
    assert not scan_events
