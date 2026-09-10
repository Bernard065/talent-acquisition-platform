"""Tenant-scoped job posting publication workflow service."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.job_postings.transitions import (
    validate_job_posting_transition,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.audit import record_audit_event
from app.services.job_posting_errors import (
    JobPostingAccessDeniedError,
    JobPostingNotFoundError,
    JobPostingRequisitionNotOpenError,
    JobPostingValidationError,
    JobPostingVersionConflictError,
)

_JOB_POSTING_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.HIRING_MANAGER,
    }
)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CreateJobPostingCommand:
    """Input needed to create a non-public draft posting."""

    employment_type: EmploymentType
    expires_at: datetime | None = None


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _require_management_role(context: TenantContext) -> None:
    """Allow only hiring workflow roles to manage public job postings."""
    if not context.roles.intersection(_JOB_POSTING_WRITE_ROLES):
        raise JobPostingAccessDeniedError(
            "Caller lacks job posting management permission."
        )


def _validate_expected_version(
    *,
    actual_version: int,
    expected_version: int,
) -> None:
    """Require a current optimistic-lock version."""
    if actual_version != expected_version:
        raise JobPostingVersionConflictError(
            "Job posting has changed; retrieve the latest version and retry."
        )


def _validate_expiry(
    expires_at: datetime | None,
    *,
    require_future: bool,
) -> None:
    """Ensure expiry timestamps are timezone-aware and usable."""
    if expires_at is None:
        return

    if expires_at.tzinfo is None:
        raise JobPostingValidationError(
            "Job posting expiry must include a UTC offset."
        )

    if require_future and expires_at <= _now():
        raise JobPostingValidationError(
            "Job posting expiry must be in the future before publication."
        )


def _slug_base(title: str) -> str:
    """Build a stable ASCII slug base from candidate-visible job title."""
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_PATTERN.sub("-", ascii_title).strip("-")

    if not slug:
        return "job"

    return slug[:160].rstrip("-")


async def _acquire_slug_lock(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    slug_base: str,
) -> None:
    """
    Serialize allocation for identical tenant slug bases.

    PostgreSQL advisory locks prevent two concurrent draft creations from
    selecting the same available suffix before the unique constraint is hit.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {
            "lock_key": f"job-posting-slug:{tenant_id}:{slug_base}",
        },
    )


async def _allocate_slug(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    title: str,
) -> str:
    """Allocate a collision-safe, tenant-scoped readable slug."""
    slug_base = _slug_base(title)
    await _acquire_slug_lock(
        session,
        tenant_id=tenant_id,
        slug_base=slug_base,
    )

    suffix = 1
    while True:
        candidate = (
            slug_base
            if suffix == 1
            else f"{slug_base[:170].rstrip('-')}-{suffix}"
        )
        exists = await session.scalar(
            select(JobPosting.id).where(
                JobPosting.tenant_id == tenant_id,
                JobPosting.slug == candidate,
            )
        )
        if exists is None:
            return candidate

        suffix += 1


async def _load_requisition(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
) -> Requisition:
    """Load and lock one tenant-owned requisition."""
    requisition = await session.scalar(
        select(Requisition)
        .where(
            Requisition.id == requisition_id,
            Requisition.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise JobPostingNotFoundError("Requisition was not found.")

    return requisition


async def _load_job_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
) -> JobPosting:
    """Load and lock one tenant-owned job posting."""
    posting = await session.scalar(
        select(JobPosting)
        .where(
            JobPosting.id == job_posting_id,
            JobPosting.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if posting is None:
        raise JobPostingNotFoundError("Job posting was not found.")

    return posting


async def create_job_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
    command: CreateJobPostingCommand,
) -> JobPosting:
    """Create a draft candidate-visible snapshot from a requisition."""
    _require_management_role(context)
    _validate_expiry(command.expires_at, require_future=False)

    async with transactional(session):
        requisition = await _load_requisition(
            session,
            context=context,
            requisition_id=requisition_id,
        )
        slug = await _allocate_slug(
            session,
            tenant_id=context.tenant_id,
            title=requisition.title,
        )

        posting = JobPosting(
            tenant_id=context.tenant_id,
            requisition_id=requisition.id,
            slug=slug,
            title=requisition.title,
            description=requisition.description,
            department=requisition.department,
            location=requisition.location,
            employment_type=command.employment_type,
            expires_at=command.expires_at,
            created_by_subject=context.subject,
        )
        session.add(posting)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="job_posting.created",
            entity_type="job_posting",
            entity_id=str(posting.id),
            details={
                "requisition_id": str(requisition.id),
                "status": posting.status.value,
                "employment_type": posting.employment_type.value,
            },
        )
        await session.flush()
        await session.refresh(posting)

    return posting


async def publish_job_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    expected_version: int,
) -> JobPosting:
    """Publish a draft or unpublished posting only for an open requisition."""
    _require_management_role(context)

    async with transactional(session):
        posting = await _load_job_posting(
            session,
            context=context,
            job_posting_id=job_posting_id,
        )
        _validate_expected_version(
            actual_version=posting.version,
            expected_version=expected_version,
        )

        requisition = await _load_requisition(
            session,
            context=context,
            requisition_id=posting.requisition_id,
        )
        if requisition.status is not RequisitionStatus.OPEN:
            raise JobPostingRequisitionNotOpenError(
                "Only open requisitions can be published."
            )

        _validate_expiry(posting.expires_at, require_future=True)
        validate_job_posting_transition(
            posting.status,
            JobPostingStatus.PUBLISHED,
        )

        posting.status = JobPostingStatus.PUBLISHED
        posting.published_at = _now()
        posting.unpublished_at = None

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="job_posting.published",
            entity_type="job_posting",
            entity_id=str(posting.id),
            details={
                "requisition_id": str(requisition.id),
                "job_posting_version": posting.version,
            },
        )
        await session.flush()
        await session.refresh(posting)

    return posting


async def unpublish_job_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    expected_version: int,
) -> JobPosting:
    """Explicitly remove a published posting from public visibility."""
    _require_management_role(context)

    async with transactional(session):
        posting = await _load_job_posting(
            session,
            context=context,
            job_posting_id=job_posting_id,
        )
        _validate_expected_version(
            actual_version=posting.version,
            expected_version=expected_version,
        )
        validate_job_posting_transition(
            posting.status,
            JobPostingStatus.UNPUBLISHED,
        )

        posting.status = JobPostingStatus.UNPUBLISHED
        posting.unpublished_at = _now()

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="job_posting.unpublished",
            entity_type="job_posting",
            entity_id=str(posting.id),
            details={
                "job_posting_version": posting.version,
                "reason": "manual",
            },
        )
        await session.flush()
        await session.refresh(posting)

    return posting


async def expire_job_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    expected_version: int,
) -> JobPosting:
    """Expire a published posting when its configured expiry is reached."""
    _require_management_role(context)

    async with transactional(session):
        posting = await _load_job_posting(
            session,
            context=context,
            job_posting_id=job_posting_id,
        )
        _validate_expected_version(
            actual_version=posting.version,
            expected_version=expected_version,
        )
        validate_job_posting_transition(
            posting.status,
            JobPostingStatus.EXPIRED,
        )

        posting.status = JobPostingStatus.EXPIRED
        posting.unpublished_at = _now()

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="job_posting.expired",
            entity_type="job_posting",
            entity_id=str(posting.id),
            details={
                "job_posting_version": posting.version,
            },
        )
        await session.flush()
        await session.refresh(posting)

    return posting


async def unpublish_job_postings_for_requisition(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
    reason: str,
) -> tuple[JobPosting, ...]:
    """
    Remove all published postings for a requisition in the caller transaction.

    Requisition close/cancel logic should call this function inside its existing
    transaction, so requisition closure and public visibility change commit
    together.
    """
    if reason not in {"requisition_closed", "requisition_cancelled"}:
        raise JobPostingValidationError("Unsupported automatic unpublish reason.")

    async with transactional(session):
        postings = list(
            await session.scalars(
                select(JobPosting)
                .where(
                    JobPosting.tenant_id == context.tenant_id,
                    JobPosting.requisition_id == requisition_id,
                    JobPosting.status == JobPostingStatus.PUBLISHED,
                )
                .with_for_update()
            )
        )

        for posting in postings:
            validate_job_posting_transition(
                posting.status,
                JobPostingStatus.UNPUBLISHED,
            )
            posting.status = JobPostingStatus.UNPUBLISHED
            posting.unpublished_at = _now()

        await session.flush()

        for posting in postings:
            record_audit_event(
                session,
                context=context,
                action="job_posting.unpublished",
                entity_type="job_posting",
                entity_id=str(posting.id),
                details={
                    "job_posting_version": posting.version,
                    "reason": reason,
                },
            )

        await session.flush()

    return tuple(postings)
