"""Tenant-scoped candidate document upload-intent service."""

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.transactions import transactional
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.audit import record_audit_event
from app.services.candidate_errors import (
    CandidateAccessDeniedError,
    CandidateNotFoundError,
)
from app.services.object_storage import candidate_document_object_key

_DOCUMENT_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)

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
    """Validated metadata needed before issuing an upload authorization."""

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


def _require_document_write_access(context: TenantContext) -> None:
    """Ensure only approved recruiting roles can attach candidate documents."""
    if context.roles.isdisjoint(_DOCUMENT_WRITE_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to manage candidate documents."
        )


async def create_candidate_document_upload_intent(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateCandidateDocumentUploadIntentCommand,
) -> CandidateDocument:
    """
    Persist a pending document record with a server-generated object key.

    This does not upload file bytes or make the file downloadable. A later
    storage adapter will issue a presigned URL, and scan processing must mark
    the document AVAILABLE before any download is permitted.
    """

    _require_document_write_access(context)

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == command.candidate_id,
                Candidate.tenant_id == context.tenant_id,
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
