"""Database-safe scheduled expiry of published job postings."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.job_posting import JobPosting
from app.db.transactions import transactional
from app.domains.job_boards.enums import (
    JobBoardPublicationOperation,
    JobBoardUnpublishReason,
)
from app.domains.job_postings.enums import JobPostingStatus
from app.domains.job_postings.transitions import (
    validate_job_posting_transition,
)
from app.services.audit import record_audit_event
from app.services.job_board_publications import (
    synchronize_job_board_publications_for_posting,
)

SYSTEM_SUBJECT = "system:job-posting-expiry-worker"


@dataclass(frozen=True, slots=True)
class JobPostingExpiryResult:
    """Outcome of one bounded job-posting expiry batch."""

    expired_job_posting_ids: tuple[UUID, ...]

    @property
    def expired_count(self) -> int:
        """Return the number of postings expired by this batch."""
        return len(self.expired_job_posting_ids)


def _validate_batch_size(batch_size: int) -> None:
    """Keep one database transaction bounded and predictable."""
    if not 1 <= batch_size <= 100:
        raise ValueError(
            "Job posting expiry batch size must be between 1 and 100."
        )


def _resolve_now(now: datetime | None) -> datetime:
    """Return an aware UTC timestamp, accepting an injected test clock."""
    resolved_now = now or datetime.now(UTC)

    if resolved_now.tzinfo is None:
        raise ValueError("Job posting expiry time must include a UTC offset.")

    return resolved_now


async def expire_due_job_postings(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
    request_id: str = "job-posting-expiry-worker",
) -> JobPostingExpiryResult:
    """
    Expire one locked batch of due published job postings.

    PostgreSQL row locks and `SKIP LOCKED` allow multiple worker instances to
    process different postings concurrently. The status mutation and audit
    event are committed together, so a posting is never expired without its
    corresponding audit record.
    """
    _validate_batch_size(batch_size)
    expiry_time = _resolve_now(now)

    async with transactional(session):
        postings = list(
            await session.scalars(
                select(JobPosting)
                .where(
                    JobPosting.status == JobPostingStatus.PUBLISHED,
                    JobPosting.expires_at.is_not(None),
                    JobPosting.expires_at <= expiry_time,
                )
                .order_by(JobPosting.expires_at, JobPosting.id)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )

        for posting in postings:
            validate_job_posting_transition(
                posting.status,
                JobPostingStatus.EXPIRED,
            )

            posting.status = JobPostingStatus.EXPIRED
            # The posting is no longer publicly visible at this timestamp.
            posting.unpublished_at = expiry_time

        # Flush before audit logging so optimistic-lock versions are current.
        await session.flush()

        for posting in postings:
            context = TenantContext(
                tenant_id=posting.tenant_id,
                subject=SYSTEM_SUBJECT,
                roles=frozenset(),
                request_id=request_id,
            )
            await synchronize_job_board_publications_for_posting(
                session,
                context=context,
                job_posting_id=posting.id,
                operation=JobBoardPublicationOperation.UNPUBLISH,
                reason=JobBoardUnpublishReason.JOB_POSTING_EXPIRED,
            )
            record_audit_event(
                session,
                context=context,
                action="job_posting.expired",
                entity_type="job_posting",
                entity_id=str(posting.id),
                details={
                    "job_posting_version": posting.version,
                    "expired_at": expiry_time.isoformat(),
                },
            )

        await session.flush()

    return JobPostingExpiryResult(
        expired_job_posting_ids=tuple(posting.id for posting in postings),
    )
