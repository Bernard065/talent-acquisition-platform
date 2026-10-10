"""Tenant-scoped candidate document workflow services."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.audit import record_audit_event
from app.services.candidate_document_errors import (
    CandidateDocumentAccessDeniedError,
    CandidateDocumentNotFoundError,
    CandidateDocumentNotUploadableError,
    CandidateDocumentVerificationError,
)
from app.services.candidate_errors import CandidateNotFoundError
from app.services.object_storage import (
    ObjectStorage,
    ObjectStorageError,
    PresignedDownload,
    PresignedUpload,
    StoredObjectMetadata,
    candidate_document_object_key,
)
from app.services.outbox import enqueue_outbox_event

_DOCUMENT_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_DOCUMENT_WRITE_ROLES = _DOCUMENT_READ_ROLES

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class CreateCandidateDocumentUploadIntentCommand:
    """Validated metadata required before a document upload is authorized."""

    candidate_id: UUID
    original_filename: str
    declared_content_type: str
    expected_byte_size: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        filename = self.original_filename.strip()

        if not filename:
            raise ValueError("Document filename is required.")

        if len(filename) > 255:
            raise ValueError("Document filename must not exceed 255 characters.")

        if "/" in filename or "\\" in filename:
            raise ValueError("Document filename must not contain a path.")

        if any(ord(character) < 32 for character in filename):
            raise ValueError("Document filename contains invalid characters.")

        if self.declared_content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError("Document content type is not allowed.")

        if not 0 < self.expected_byte_size <= _MAX_DOCUMENT_BYTES:
            raise ValueError("Document size must be between 1 byte and 10 MiB.")

        if not _SHA256_PATTERN.fullmatch(self.checksum_sha256.lower()):
            raise ValueError("Document checksum must be a SHA-256 hexadecimal value.")


def _require_document_access(
    context: TenantContext,
    allowed_roles: frozenset[Role],
) -> None:
    """Enforce document authorization at the service boundary."""
    if context.roles.isdisjoint(allowed_roles):
        raise CandidateDocumentAccessDeniedError(
            "Caller is not permitted to access candidate documents."
        )


async def get_candidate_document(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
) -> CandidateDocument:
    """Return one document visible only to the verified caller's tenant."""
    _require_document_access(context, _DOCUMENT_READ_ROLES)

    document = await session.scalar(
        select(CandidateDocument).where(
            CandidateDocument.id == document_id,
            CandidateDocument.tenant_id == context.tenant_id,
            CandidateDocument.status != CandidateDocumentStatus.DELETED,
        )
    )
    if document is None:
        raise CandidateDocumentNotFoundError("Candidate document was not found.")

    return document


async def list_candidate_documents(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> list[CandidateDocument]:
    """List non-deleted documents for one active tenant candidate."""
    _require_document_access(context, _DOCUMENT_READ_ROLES)

    candidate_exists = await session.scalar(
        select(Candidate.id).where(
            Candidate.id == candidate_id,
            Candidate.tenant_id == context.tenant_id,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
        )
    )
    if candidate_exists is None:
        raise CandidateNotFoundError("Candidate was not found.")

    return list(
        await session.scalars(
            select(CandidateDocument)
            .where(
                CandidateDocument.candidate_id == candidate_id,
                CandidateDocument.tenant_id == context.tenant_id,
                CandidateDocument.status != CandidateDocumentStatus.DELETED,
            )
            .order_by(CandidateDocument.created_at.desc(), CandidateDocument.id.desc())
        )
    )


async def create_document_download_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
) -> PresignedDownload:
    """Authorize a private download only after the document passes malware scanning."""
    return await _create_document_access_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=expires_in,
        preview=False,
    )


async def create_document_preview_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
) -> PresignedDownload:
    """Authorize an inline preview only for a clean, active candidate document."""
    return await _create_document_access_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=expires_in,
        preview=True,
    )


async def _create_document_access_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
    preview: bool,
) -> PresignedDownload:
    """Authorize short-lived access only to an available document."""
    document = await get_candidate_document(
        session,
        context=context,
        document_id=document_id,
    )
    if document.status is not CandidateDocumentStatus.AVAILABLE:
        raise CandidateDocumentNotUploadableError(
            "This document is not available for access yet."
        )
    if preview and document.declared_content_type != "application/pdf":
        raise CandidateDocumentNotUploadableError(
            "Only PDF documents can be previewed in the browser."
        )

    candidate_exists = await session.scalar(
        select(Candidate.id).where(
            Candidate.id == document.candidate_id,
            Candidate.tenant_id == context.tenant_id,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
        )
    )
    if candidate_exists is None:
        raise CandidateDocumentNotFoundError("Candidate document was not found.")

    try:
        create_authorization = (
            storage.create_presigned_preview
            if preview
            else storage.create_presigned_download
        )
        return await create_authorization(
            object_key=document.storage_key,
            filename=document.original_filename,
            content_type=document.declared_content_type,
            expires_in=expires_in,
        )
    except ObjectStorageError as error:
        raise CandidateDocumentVerificationError(
            "Document access authorization could not be created."
        ) from error


async def create_candidate_document_upload_intent(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateCandidateDocumentUploadIntentCommand,
) -> CandidateDocument:
    """Persist a pending document record with a server-generated object key."""
    _require_document_access(context, _DOCUMENT_WRITE_ROLES)

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == command.candidate_id,
                Candidate.tenant_id == context.tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
            .with_for_update()
        )
        if candidate is None:
            raise CandidateNotFoundError("Candidate was not found.")

        document_id = uuid4()
        document = CandidateDocument(
            id=document_id,
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            storage_key=candidate_document_object_key(
                tenant_id=context.tenant_id,
                candidate_id=candidate.id,
                document_id=document_id,
            ),
            original_filename=command.original_filename.strip(),
            declared_content_type=command.declared_content_type,
            expected_byte_size=command.expected_byte_size,
            checksum_sha256=command.checksum_sha256.lower(),
            status=CandidateDocumentStatus.PENDING_UPLOAD,
            created_by_subject=context.subject,
        )
        session.add(document)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="candidate_document.upload_intent_created",
            entity_type="candidate_document",
            entity_id=str(document.id),
            details={
                "candidate_id": str(candidate.id),
                "content_type": document.declared_content_type,
                "expected_byte_size": document.expected_byte_size,
            },
        )

    return document


async def create_upload_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
) -> PresignedUpload:
    """
    Create a fresh, short-lived upload authorization for a pending document.

    The latest authorization expiry is persisted so a later erasure request
    can wait until all already-issued upload URLs are no longer valid. The URL
    itself is never stored in durable idempotency data.
    """
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

        if document.status is not CandidateDocumentStatus.PENDING_UPLOAD:
            raise CandidateDocumentNotUploadableError(
                "Document is not awaiting an upload."
            )

        candidate = await session.scalar(
            select(Candidate).where(
                Candidate.id == document.candidate_id,
                Candidate.tenant_id == context.tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
        )
        if candidate is None:
            raise CandidateDocumentNotFoundError("Candidate document was not found.")

        if document.checksum_sha256 is None:
            raise CandidateDocumentVerificationError(
                "Document checksum is missing; upload authorization cannot be created."
            )

        authorization_expires_at = datetime.now(UTC) + expires_in
        if (
            document.upload_authorization_expires_at is None
            or authorization_expires_at > document.upload_authorization_expires_at
        ):
            document.upload_authorization_expires_at = authorization_expires_at
        await session.flush()

        object_key = document.storage_key
        content_type = document.declared_content_type
        checksum = document.checksum_sha256

    try:
        return await storage.create_presigned_upload(
            object_key=object_key,
            content_type=content_type,
            checksum_sha256=checksum,
            expires_in=expires_in,
        )
    except ObjectStorageError as error:
        raise CandidateDocumentVerificationError(
            "Document upload authorization could not be created."
        ) from error


async def confirm_candidate_document_upload(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
) -> CandidateDocument:
    """
    Verify uploaded-object metadata and atomically update document state.

    A metadata mismatch is a completed verification result, not an exception:
    the document becomes rejected and its audit event commits atomically.
    """
    _require_document_access(context, _DOCUMENT_WRITE_ROLES)

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

        if document.status is not CandidateDocumentStatus.PENDING_UPLOAD:
            raise CandidateDocumentNotUploadableError(
                "Document upload cannot be confirmed in its current state."
            )

        try:
            metadata = await storage.get_object_metadata(
                object_key=document.storage_key,
            )
        except ObjectStorageError as error:
            raise CandidateDocumentVerificationError(
                "Uploaded document could not be verified."
            ) from error

        if not _metadata_matches(document, metadata):
            document.status = CandidateDocumentStatus.REJECTED

            record_audit_event(
                session,
                context=context,
                action="candidate_document.upload_rejected",
                entity_type="candidate_document",
                entity_id=str(document.id),
                details={"reason": "metadata_mismatch"},
            )

            await session.flush()
            await session.refresh(document)
            return document

        document.status = CandidateDocumentStatus.UPLOADED
        document.uploaded_at = datetime.now(UTC)

        enqueue_outbox_event(
            session,
            context=context,
            event_type="candidate_document.scan_requested",
            aggregate_type="candidate_document",
            aggregate_id=str(document.id),
            deduplication_key=f"candidate_document.scan_requested:{document.id}",
            payload={
                "document_id": str(document.id),
            },
        )

        record_audit_event(
            session,
            context=context,
            action="candidate_document.upload_confirmed",
            entity_type="candidate_document",
            entity_id=str(document.id),
            details={
                "content_type": document.declared_content_type,
                "byte_size": document.expected_byte_size,
            },
        )

        await session.flush()
        await session.refresh(document)

    return document


def _metadata_matches(
    document: CandidateDocument,
    metadata: StoredObjectMetadata,
) -> bool:
    """Compare provider-verified metadata with immutable upload expectations."""
    return (
        metadata.content_type == document.declared_content_type
        and metadata.byte_size == document.expected_byte_size
        and metadata.checksum_sha256 == document.checksum_sha256
    )
