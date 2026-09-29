"""Tenant-scoped, transactional requests for external job-board publication."""

import re
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.job_board_publication import JobBoardPublication
from app.db.models.job_posting import JobPosting
from app.db.transactions import transactional
from app.domains.job_boards.enums import (
    JobBoardPublicationOperation,
    JobBoardPublicationStatus,
    JobBoardUnpublishReason,
)
from app.domains.job_boards.transitions import validate_job_board_publication_transition
from app.domains.job_postings.enums import JobPostingStatus
from app.services.audit import record_audit_event
from app.services.job_board_publication_errors import (
    JobBoardPublicationAccessDeniedError,
    JobBoardPublicationConflictError,
    JobBoardPublicationNotFoundError,
    JobBoardPublicationValidationError,
)
from app.services.outbox import enqueue_outbox_event

_JOB_BOARD_MANAGEMENT_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.HIRING_MANAGER}
)
_PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _require_management_role(context: TenantContext) -> None:
    """Restrict publishing controls to authorized hiring roles."""
    if context.roles.isdisjoint(_JOB_BOARD_MANAGEMENT_ROLES):
        raise JobBoardPublicationAccessDeniedError(
            "Caller lacks job-board publication permission."
        )


def _normalize_provider_key(provider_key: str) -> str:
    """Accept only canonical, opaque provider identifiers; never credentials."""
    normalized = provider_key.strip().lower()
    if not _PROVIDER_KEY_PATTERN.fullmatch(normalized):
        raise JobBoardPublicationValidationError("Invalid job-board provider key.")
    return normalized


async def _lock_provider_publication_key(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    job_posting_id: UUID,
    provider_key: str,
) -> None:
    """Serialize first creation for a tenant/posting/provider tuple."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {
            "lock_key": (
                f"job-board-publication:{tenant_id}:{job_posting_id}:{provider_key}"
            )
        },
    )


async def _load_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
) -> JobPosting:
    """Lock one posting within the caller's tenant."""
    posting = await session.scalar(
        select(JobPosting)
        .where(
            JobPosting.id == job_posting_id,
            JobPosting.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if posting is None:
        raise JobBoardPublicationNotFoundError("Job posting was not found.")
    return posting


def _enqueue_operation(
    session: AsyncSession,
    *,
    context: TenantContext,
    publication: JobBoardPublication,
    operation: JobBoardPublicationOperation,
) -> None:
    """Queue identifier-only work in the current business transaction."""
    event_type = f"job_board.{operation.value}_requested"
    enqueue_outbox_event(
        session,
        context=context,
        event_type=event_type,
        aggregate_type="job_board_publication",
        aggregate_id=str(publication.id),
        deduplication_key=(
            f"{publication.id}:g{publication.desired_generation}"
        ),
        payload={
            "publication_id": str(publication.id),
            "generation": publication.desired_generation,
            "provider_key": publication.provider_key,
            "operation": operation.value,
        },
    )


def _record_request_audit(
    session: AsyncSession,
    *,
    context: TenantContext,
    publication: JobBoardPublication,
    operation: JobBoardPublicationOperation,
    reason: JobBoardUnpublishReason | None = None,
) -> None:
    """Record operational metadata only; never copy public posting content."""
    details: dict[str, str | int] = {
        "job_posting_id": str(publication.job_posting_id),
        "provider_key": publication.provider_key,
        "operation": operation.value,
        "generation": publication.desired_generation,
    }
    if reason is not None:
        details["reason"] = reason.value

    record_audit_event(
        session,
        context=context,
        action=f"job_board.publication.{operation.value}_requested",
        entity_type="job_board_publication",
        entity_id=str(publication.id),
        details=details,
    )


async def request_job_board_publication(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    provider_key: str,
) -> JobBoardPublication:
    """Idempotently request publication of a locally published job posting."""
    _require_management_role(context)
    normalized_provider = _normalize_provider_key(provider_key)

    async with transactional(session):
        posting = await _load_posting(
            session,
            context=context,
            job_posting_id=job_posting_id,
        )
        if posting.status is not JobPostingStatus.PUBLISHED:
            raise JobBoardPublicationConflictError(
                "Only locally published job postings can be sent to a job board."
            )

        await _lock_provider_publication_key(
            session,
            tenant_id=context.tenant_id,
            job_posting_id=posting.id,
            provider_key=normalized_provider,
        )
        publication = await session.scalar(
            select(JobBoardPublication)
            .where(
                JobBoardPublication.tenant_id == context.tenant_id,
                JobBoardPublication.job_posting_id == posting.id,
                JobBoardPublication.provider_key == normalized_provider,
            )
            .with_for_update()
        )

        if publication is None:
            publication = JobBoardPublication(
                tenant_id=context.tenant_id,
                job_posting_id=posting.id,
                provider_key=normalized_provider,
                status=JobBoardPublicationStatus.PUBLISH_REQUESTED,
                created_by_subject=context.subject,
            )
            session.add(publication)
            await session.flush()
            operation = JobBoardPublicationOperation.PUBLISH
        elif publication.status in {
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.PUBLISHED,
        }:
            return publication
        else:
            validate_job_board_publication_transition(
                publication.status,
                JobBoardPublicationStatus.PUBLISH_REQUESTED,
            )
            publication.status = JobBoardPublicationStatus.PUBLISH_REQUESTED
            publication.desired_generation += 1
            publication.last_error_code = None
            await session.flush()
            operation = JobBoardPublicationOperation.PUBLISH

        _enqueue_operation(
            session,
            context=context,
            publication=publication,
            operation=operation,
        )
        _record_request_audit(
            session,
            context=context,
            publication=publication,
            operation=operation,
        )
        await session.flush()
        await session.refresh(publication)

    return publication


async def request_job_board_unpublication(
    session: AsyncSession,
    *,
    context: TenantContext,
    publication_id: UUID,
    reason: JobBoardUnpublishReason = JobBoardUnpublishReason.MANUAL,
) -> JobBoardPublication:
    """Idempotently request removal of one tenant-owned external posting."""
    _require_management_role(context)

    async with transactional(session):
        publication = await session.scalar(
            select(JobBoardPublication)
            .where(
                JobBoardPublication.id == publication_id,
                JobBoardPublication.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if publication is None:
            raise JobBoardPublicationNotFoundError(
                "Job-board publication was not found."
            )
        await _request_unpublication(
            session,
            context=context,
            publication=publication,
            reason=reason,
        )
        await session.refresh(publication)

    return publication


async def _request_unpublication(
    session: AsyncSession,
    *,
    context: TenantContext,
    publication: JobBoardPublication,
    reason: JobBoardUnpublishReason,
) -> bool:
    """Transition one locked publication and enqueue its remote removal."""
    if publication.status in {
        JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
        JobBoardPublicationStatus.UNPUBLISHED,
    }:
        return False

    validate_job_board_publication_transition(
        publication.status,
        JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
    )
    publication.status = JobBoardPublicationStatus.UNPUBLISH_REQUESTED
    publication.desired_generation += 1
    publication.last_error_code = None
    await session.flush()
    _enqueue_operation(
        session,
        context=context,
        publication=publication,
        operation=JobBoardPublicationOperation.UNPUBLISH,
    )
    _record_request_audit(
        session,
        context=context,
        publication=publication,
        operation=JobBoardPublicationOperation.UNPUBLISH,
        reason=reason,
    )
    return True


async def synchronize_job_board_publications_for_posting(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    operation: JobBoardPublicationOperation,
    reason: JobBoardUnpublishReason | None = None,
) -> tuple[JobBoardPublication, ...]:
    """Queue provider syncs with a local publication lifecycle transition.

    This internal service intentionally does not require a user role: it is
    called inside an already-authorized posting workflow or by a system worker.
    """
    if operation is JobBoardPublicationOperation.UNPUBLISH and reason is None:
        raise JobBoardPublicationValidationError(
            "An unpublish reason is required for lifecycle synchronization."
        )
    if operation is JobBoardPublicationOperation.PUBLISH and reason is not None:
        raise JobBoardPublicationValidationError(
            "A publish request cannot include an unpublish reason."
        )

    async with transactional(session):
        publications = list(
            await session.scalars(
                select(JobBoardPublication)
                .where(
                    JobBoardPublication.tenant_id == context.tenant_id,
                    JobBoardPublication.job_posting_id == job_posting_id,
                )
                .order_by(JobBoardPublication.provider_key)
                .with_for_update()
            )
        )
        changed: list[JobBoardPublication] = []

        for publication in publications:
            if operation is JobBoardPublicationOperation.PUBLISH:
                if publication.status in {
                    JobBoardPublicationStatus.PUBLISH_REQUESTED,
                    JobBoardPublicationStatus.PUBLISHED,
                }:
                    continue
                validate_job_board_publication_transition(
                    publication.status,
                    JobBoardPublicationStatus.PUBLISH_REQUESTED,
                )
                publication.status = JobBoardPublicationStatus.PUBLISH_REQUESTED
                publication.desired_generation += 1
                publication.last_error_code = None
                await session.flush()
                _enqueue_operation(
                    session,
                    context=context,
                    publication=publication,
                    operation=operation,
                )
                _record_request_audit(
                    session,
                    context=context,
                    publication=publication,
                    operation=operation,
                )
            else:
                if reason is None:
                    raise JobBoardPublicationValidationError(
                        "An unpublish reason is required for lifecycle synchronization."
                    )
                queued = await _request_unpublication(
                    session,
                    context=context,
                    publication=publication,
                    reason=reason,
                )
                if not queued:
                    continue
            changed.append(publication)

        await session.flush()
        for publication in changed:
            await session.refresh(publication)

    return tuple(changed)
