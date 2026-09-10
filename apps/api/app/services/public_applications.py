"""Privacy-safe anonymous application submission for published public jobs."""

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
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.job_postings.enums import JobPostingStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.audit import record_audit_event
from app.services.candidates import _canonicalize_email
from app.services.public_application_errors import (
    PublicApplicationJobNotFoundError,
)

_PUBLIC_APPLICATION_SUBJECT = "public:job-application"


@dataclass(frozen=True, slots=True)
class SubmitPublicApplicationCommand:
    """Validated candidate input accepted from the public application form."""

    full_name: str
    email: str
    phone: str | None
    location: str | None
    source_reference: str | None

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValueError("Full name is required.")

        if len(self.full_name.strip()) > 200:
            raise ValueError("Full name must not exceed 200 characters.")

        if self.phone is not None and len(self.phone.strip()) > 50:
            raise ValueError("Phone must not exceed 50 characters.")

        if self.location is not None and len(self.location.strip()) > 200:
            raise ValueError("Location must not exceed 200 characters.")

        if (
            self.source_reference is not None
            and len(self.source_reference.strip()) > 100
        ):
            raise ValueError("Source reference must not exceed 100 characters.")


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
) -> None:
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
        return

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


async def submit_public_application(
    session: AsyncSession,
    *,
    context: TenantContext,
    public_job_id: UUID,
    command: SubmitPublicApplicationCommand,
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
        candidate = await _find_or_create_candidate(
            session,
            context=context,
            command=command,
            public_job_id=public_job_id,
        )
        await _create_application_if_missing(
            session,
            context=context,
            candidate=candidate,
            requisition=requisition,
        )
        await session.flush()
