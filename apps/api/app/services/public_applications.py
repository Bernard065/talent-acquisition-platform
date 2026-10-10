"""Privacy-safe anonymous application submission for published public jobs."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.documents.enums import (
    CandidateDocumentScanStatus,
    CandidateDocumentStatus,
)
from app.domains.job_postings.enums import JobPostingStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.audit import record_audit_event
from app.services.candidate_document_errors import CandidateDocumentVerificationError
from app.services.candidates import _canonicalize_email
from app.services.object_storage import (
    ObjectStorage,
    ObjectStorageError,
)
from app.services.public_application_errors import (
    PublicApplicationJobNotFoundError,
)
from app.services.public_application_resumes import (
    ClaimedResumeScan,
    claim_public_application_resume_scan,
)

_PUBLIC_APPLICATION_SUBJECT = "public:job-application"
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True, slots=True)
class SubmitPublicApplicationCommand:
    """Validated candidate input accepted from the public application form."""

    full_name: str
    email: str
    phone: str | None
    location: str | None
    source_reference: str | None
    resume_filename: str | None = None
    resume_content_type: str | None = None
    resume_content: bytes | None = None
    resume_scan_token: str | None = None

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValueError("Full name is required.")

        if len(self.full_name.strip()) > 200:
            raise ValueError("Full name must not exceed 200 characters.")

        if self.phone is not None and len(self.phone.strip()) > 50:
            raise ValueError("Phone must not exceed 50 characters.")

        if self.location is not None and len(self.location.strip()) > 200:
            raise ValueError("Location must not exceed 200 characters.")

        if self.source_reference is not None and len(self.source_reference.strip()) > 100:
            raise ValueError("Source reference must not exceed 100 characters.")

        if self.resume_content is not None:
            if self.resume_filename is None or self.resume_content_type is None:
                raise ValueError("Résumé metadata is required for uploaded content.")
            if len(self.resume_content) > 10 * 1024 * 1024:
                raise ValueError("Résumé must not exceed 10 MiB.")


def _now() -> datetime:
    """Return a timezone-aware timestamp for consent recording."""
    return datetime.now(UTC)


async def resolve_public_application_tenant(
    session: AsyncSession,
    *,
    public_job_id: UUID,
) -> UUID:
    """
    Resolve tenant ownership only while a job is publicly eligible.

    The endpoint needs this before durable idempotency can scope a key to the
    tenant. The service revalidates visibility in its own transaction later.
    """
    posting = await session.scalar(
        select(JobPosting.tenant_id)
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .where(
            JobPosting.public_id == public_job_id,
            JobPosting.status == JobPostingStatus.PUBLISHED,
            JobPosting.published_at.is_not(None),
            (JobPosting.expires_at.is_(None) | (JobPosting.expires_at > _now())),
            Requisition.status == RequisitionStatus.OPEN,
        )
    )

    if posting is None:
        raise PublicApplicationJobNotFoundError("Public job was not found.")

    return posting


async def _load_public_job_for_submission(
    session: AsyncSession,
    *,
    context: TenantContext,
    public_job_id: UUID,
) -> tuple[JobPosting, Requisition]:
    """
    Lock the requisition first, then the job posting.

    This order matches requisition closure, avoiding a lock-order inversion
    while ensuring a concurrently closed or unpublished job cannot accept an
    application.
    """
    requisition = await session.scalar(
        select(Requisition)
        .join(JobPosting, JobPosting.requisition_id == Requisition.id)
        .where(
            JobPosting.public_id == public_job_id,
            JobPosting.tenant_id == context.tenant_id,
            JobPosting.status == JobPostingStatus.PUBLISHED,
            JobPosting.published_at.is_not(None),
            (JobPosting.expires_at.is_(None) | (JobPosting.expires_at > _now())),
            Requisition.tenant_id == context.tenant_id,
            Requisition.status == RequisitionStatus.OPEN,
        )
        .with_for_update()
    )
    if requisition is None:
        raise PublicApplicationJobNotFoundError("Public job was not found.")

    posting = await session.scalar(
        select(JobPosting)
        .where(
            JobPosting.public_id == public_job_id,
            JobPosting.tenant_id == context.tenant_id,
            JobPosting.requisition_id == requisition.id,
            JobPosting.status == JobPostingStatus.PUBLISHED,
        )
        .with_for_update()
    )
    if posting is None:
        raise PublicApplicationJobNotFoundError("Public job was not found.")

    return posting, requisition


async def _find_or_create_candidate(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: SubmitPublicApplicationCommand,
    public_job_id: UUID,
) -> Candidate:
    """Create a tenant candidate once, without allowing public profile overwrites."""
    email, normalized_email = _canonicalize_email(command.email)

    candidate = Candidate(
        tenant_id=context.tenant_id,
        full_name=command.full_name.strip(),
        email=email,
        normalized_email=normalized_email,
        phone=command.phone.strip() if command.phone else None,
        location=command.location.strip() if command.location else None,
        source="public_job",
        source_metadata={
            "channel": "public_job",
            "job_posting_public_id": str(public_job_id),
            **(
                {"source_reference": command.source_reference.strip()}
                if command.source_reference and command.source_reference.strip()
                else {}
            ),
        },
        consent_status=CandidateConsentStatus.GRANTED,
        consent_updated_at=_now(),
        created_by_subject=_PUBLIC_APPLICATION_SUBJECT,
    )

    try:
        async with session.begin_nested():
            session.add(candidate)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(Candidate)
            .where(
                Candidate.tenant_id == context.tenant_id,
                Candidate.normalized_email == normalized_email,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
            .with_for_update()
        )
        if existing is None:
            raise
        return existing

    record_audit_event(
        session,
        context=context,
        action="candidate.created_from_public_application",
        entity_type="candidate",
        entity_id=str(candidate.id),
        details={
            "source": "public_job",
            "consent_status": CandidateConsentStatus.GRANTED.value,
        },
    )
    return candidate


async def _create_application_if_missing(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate: Candidate,
    requisition: Requisition,
) -> bool:
    """
    Create a first application or silently accept a duplicate submission.

    Public callers receive one generic outcome in both cases, preventing
    candidate and application enumeration.
    """
    application = Application(
        tenant_id=context.tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.APPLIED,
        created_by_subject=_PUBLIC_APPLICATION_SUBJECT,
    )

    try:
        async with session.begin_nested():
            session.add(application)
            await session.flush()
    except IntegrityError:
        return False

    session.add(
        ApplicationStageHistory(
            tenant_id=context.tenant_id,
            application_id=application.id,
            from_status=None,
            to_status=ApplicationStatus.APPLIED,
            transitioned_by_subject=_PUBLIC_APPLICATION_SUBJECT,
        )
    )
    record_audit_event(
        session,
        context=context,
        action="application.created_from_public_job",
        entity_type="application",
        entity_id=str(application.id),
        details={
            "requisition_id": str(requisition.id),
            "status": ApplicationStatus.APPLIED.value,
            "source": "public_job",
        },
    )
    return True


async def _store_public_resume(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate: Candidate,
    command: SubmitPublicApplicationCommand,
    storage: ObjectStorage,
    scan: ClaimedResumeScan,
) -> None:
    """Persist a résumé already scanned clean before application acceptance."""
    content = command.resume_content
    filename = command.resume_filename
    content_type = command.resume_content_type
    if content is None or filename is None or content_type is None:
        return
    filename = filename.strip()
    if (
        not filename
        or len(filename) > 255
        or "/" in filename
        or "\\" in filename
        or any(ord(character) < 32 for character in filename)
    ):
        raise ValueError("Résumé filename is invalid.")

    allowed = {
        "application/pdf": content.startswith(b"%PDF-"),
        _DOCX_CONTENT_TYPE: content.startswith(b"PK\x03\x04"),
    }
    if content_type not in allowed or not allowed[content_type]:
        raise ValueError("Résumé file type is invalid.")

    document_id = scan.scan_id
    checksum = hashlib.sha256(content).hexdigest()
    existing_document = await session.scalar(
        select(CandidateDocument.id).where(
            CandidateDocument.tenant_id == context.tenant_id,
            CandidateDocument.candidate_id == candidate.id,
            CandidateDocument.checksum_sha256 == checksum,
            CandidateDocument.status != CandidateDocumentStatus.DELETED,
        )
    )
    if existing_document is not None:
        return

    storage_key = scan.object_key
    scanned_at = _now()
    document = CandidateDocument(
        id=document_id,
        tenant_id=context.tenant_id,
        candidate_id=candidate.id,
        storage_key=storage_key,
        original_filename=filename,
        declared_content_type=content_type,
        expected_byte_size=len(content),
        checksum_sha256=checksum,
        status=CandidateDocumentStatus.PENDING_UPLOAD,
        created_by_subject=_PUBLIC_APPLICATION_SUBJECT,
    )
    session.add(document)
    await session.flush()

    try:
        await storage.put_object(
            object_key=storage_key,
            content_type=content_type,
            checksum_sha256=checksum,
            content=content,
        )
        metadata = await storage.get_object_metadata(object_key=storage_key)
    except ObjectStorageError as error:
        try:
            await storage.delete_object(object_key=storage_key)
        except ObjectStorageError:
            pass
        raise CandidateDocumentVerificationError(
            "Uploaded résumé could not be verified."
        ) from error

    if (
        metadata.content_type != content_type
        or metadata.byte_size != len(content)
        or metadata.checksum_sha256 != checksum
    ):
        try:
            await storage.delete_object(object_key=storage_key)
        except ObjectStorageError:
            pass
        raise CandidateDocumentVerificationError("Uploaded résumé could not be verified.")

    document.status = CandidateDocumentStatus.AVAILABLE
    document.uploaded_at = scanned_at
    document.scan_started_at = scanned_at
    document.scan_completed_at = scanned_at
    document_scan = CandidateDocumentScan(
        tenant_id=context.tenant_id,
        candidate_document_id=document.id,
        status=CandidateDocumentScanStatus.CLEAN,
        scanner_name=scan.scanner_name,
        started_at=scanned_at,
        completed_at=scanned_at,
    )
    session.add(document_scan)
    record_audit_event(
        session,
        context=context,
        action="candidate_document.upload_confirmed",
        entity_type="candidate_document",
        entity_id=str(document.id),
        details={"content_type": content_type, "byte_size": len(content)},
    )
    record_audit_event(
        session,
        context=context,
        action="candidate_document.scan_clean",
        entity_type="candidate_document",
        entity_id=str(document.id),
        details={"scanner_name": scan.scanner_name},
    )


async def submit_public_application(
    session: AsyncSession,
    *,
    context: TenantContext,
    public_job_id: UUID,
    command: SubmitPublicApplicationCommand,
    storage: ObjectStorage | None = None,
) -> None:
    """
    Submit an application without returning candidate or application identity.

    The caller is expected to return the same generic acknowledgement for both
    new and duplicate submissions.
    """
    async with transactional(session):
        _, requisition = await _load_public_job_for_submission(
            session,
            context=context,
            public_job_id=public_job_id,
        )
        resume_scan: ClaimedResumeScan | None = None
        if command.resume_content is not None:
            if (
                command.resume_filename is None
                or command.resume_content_type is None
                or command.resume_scan_token is None
            ):
                raise CandidateDocumentVerificationError(
                    "Résumé scan proof is required before application acceptance."
                )
            resume_scan = await claim_public_application_resume_scan(
                session,
                context=context,
                public_job_id=public_job_id,
                scan_token=command.resume_scan_token,
                content=command.resume_content,
                content_type=command.resume_content_type,
            )
        elif command.resume_scan_token is not None:
            raise CandidateDocumentVerificationError(
                "Résumé scan proof was provided without a résumé file."
            )
        candidate = await _find_or_create_candidate(
            session,
            context=context,
            command=command,
            public_job_id=public_job_id,
        )
        if candidate.consent_status is not CandidateConsentStatus.GRANTED:
            # Do not restart processing after consent withdrawal. The public
            # caller still receives the same generic acknowledgement.
            return
        application_created = await _create_application_if_missing(
            session,
            context=context,
            candidate=candidate,
            requisition=requisition,
        )
        if command.resume_content is not None and application_created:
            if storage is None:
                raise CandidateDocumentVerificationError("Document storage service is unavailable.")
            if resume_scan is None:
                raise CandidateDocumentVerificationError("Résumé scan proof is missing.")
            await _store_public_resume(
                session,
                context=context,
                candidate=candidate,
                command=command,
                storage=storage,
                scan=resume_scan,
            )
        await session.flush()
