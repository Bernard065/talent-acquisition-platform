"""PostgreSQL integration tests for concurrent job-posting expiry."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.functions import count

from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import EmploymentType, JobPostingStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.job_posting_expiry import (
    SYSTEM_SUBJECT,
    expire_due_job_postings,
)

_EXPIRY_TIME = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


async def _seed_job_postings(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    posting_count: int,
    posting_status: JobPostingStatus,
    expires_at: datetime | None,
) -> list[JobPosting]:
    """Create tenant-owned job postings with controlled expiry conditions."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Job Posting Expiry Tenant {tenant_id.hex[:12]}",
            slug=f"job-posting-expiry-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    postings: list[JobPosting] = []

    for position in range(posting_count):
        requisition = Requisition(
            tenant_id=tenant_id,
            title=f"Platform Engineer {position}",
            description=f"Job description {position}.",
            department="Engineering",
            location="Nairobi, Kenya",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="seed",
        )
        session.add(requisition)
        await session.flush()

        posting = JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            slug=f"platform-engineer-{position}-{tenant_id.hex[:8]}",
            title=f"Platform Engineer {position}",
            description=f"Job description {position}.",
            department="Engineering",
            location="Nairobi, Kenya",
            employment_type=EmploymentType.FULL_TIME,
            status=posting_status,
            published_at=(
                expires_at - timedelta(days=7)
                if posting_status is JobPostingStatus.PUBLISHED
                and expires_at is not None
                else None
            ),
            expires_at=expires_at,
            created_by_subject="seed",
        )
        session.add(posting)
        postings.append(posting)

    await session.commit()
    return postings


@pytest.mark.asyncio
async def test_expires_only_bounded_due_posting_batch(
    session: AsyncSession,
) -> None:
    """Expire no more than the configured batch size."""
    due_postings = await _seed_job_postings(
        session,
        tenant_id=uuid4(),
        posting_count=3,
        posting_status=JobPostingStatus.PUBLISHED,
        expires_at=_EXPIRY_TIME - timedelta(minutes=1),
    )

    result = await expire_due_job_postings(
        session,
        batch_size=2,
        now=_EXPIRY_TIME,
    )

    statuses = list(
        await session.scalars(
            select(JobPosting.status)
            .where(JobPosting.id.in_([posting.id for posting in due_postings]))
            .order_by(JobPosting.id)
        )
    )

    assert result.expired_count == 2
    assert len(set(result.expired_job_posting_ids)) == 2
    assert statuses.count(JobPostingStatus.EXPIRED) == 2
    assert statuses.count(JobPostingStatus.PUBLISHED) == 1


@pytest.mark.asyncio
async def test_leaves_non_due_and_non_published_postings_unchanged(
    session: AsyncSession,
) -> None:
    """Only due, published postings are eligible for automatic expiry."""
    future_posting = (
        await _seed_job_postings(
            session,
            tenant_id=uuid4(),
            posting_count=1,
            posting_status=JobPostingStatus.PUBLISHED,
            expires_at=_EXPIRY_TIME + timedelta(minutes=1),
        )
    )[0]
    draft_posting = (
        await _seed_job_postings(
            session,
            tenant_id=uuid4(),
            posting_count=1,
            posting_status=JobPostingStatus.DRAFT,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )
    )[0]

    result = await expire_due_job_postings(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )

    stored_future = await session.get(JobPosting, future_posting.id)
    stored_draft = await session.get(JobPosting, draft_posting.id)

    assert result.expired_count == 0
    assert stored_future is not None
    assert stored_future.status is JobPostingStatus.PUBLISHED
    assert stored_future.unpublished_at is None

    assert stored_draft is not None
    assert stored_draft.status is JobPostingStatus.DRAFT
    assert stored_draft.unpublished_at is None


@pytest.mark.asyncio
async def test_concurrent_workers_expire_each_posting_once(
    database_engine: AsyncEngine,
) -> None:
    """Use PostgreSQL SKIP LOCKED to divide work between worker sessions."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    tenant_id = uuid4()

    async with session_factory() as setup_session:
        postings = await _seed_job_postings(
            setup_session,
            tenant_id=tenant_id,
            posting_count=4,
            posting_status=JobPostingStatus.PUBLISHED,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )

    async def run_worker(request_id: str) -> tuple[UUID, ...]:
        async with session_factory() as worker_session:
            result = await expire_due_job_postings(
                worker_session,
                batch_size=2,
                now=_EXPIRY_TIME,
                request_id=request_id,
            )
            return result.expired_job_posting_ids

    first_claim, second_claim = await asyncio.gather(
        run_worker("job-posting-expiry-worker-one"),
        run_worker("job-posting-expiry-worker-two"),
    )
    claimed_ids = (*first_claim, *second_claim)

    async with session_factory() as verification_session:
        expired_count = await verification_session.scalar(
            select(count())
            .select_from(JobPosting)
            .where(
                JobPosting.id.in_([posting.id for posting in postings]),
                JobPosting.status == JobPostingStatus.EXPIRED,
            )
        )
        audit_count = await verification_session.scalar(
            select(count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_id.in_(
                    [str(posting.id) for posting in postings]
                ),
                AuditEvent.action == "job_posting.expired",
            )
        )

    assert len(claimed_ids) == 4
    assert len(set(claimed_ids)) == 4
    assert expired_count == 4
    assert audit_count == 4


@pytest.mark.asyncio
async def test_repeat_run_is_safe_and_records_privacy_safe_audit_event(
    session: AsyncSession,
) -> None:
    """A terminal posting is not re-expired and receives one audit record."""
    posting = (
        await _seed_job_postings(
            session,
            tenant_id=uuid4(),
            posting_count=1,
            posting_status=JobPostingStatus.PUBLISHED,
            expires_at=_EXPIRY_TIME - timedelta(minutes=1),
        )
    )[0]

    first = await expire_due_job_postings(
        session,
        batch_size=10,
        now=_EXPIRY_TIME,
    )
    second = await expire_due_job_postings(
        session,
        batch_size=10,
        now=_EXPIRY_TIME + timedelta(minutes=1),
    )

    stored_posting = await session.get(JobPosting, posting.id)
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(posting.id),
            AuditEvent.action == "job_posting.expired",
        )
    )

    assert first.expired_job_posting_ids == (posting.id,)
    assert second.expired_count == 0

    assert stored_posting is not None
    assert stored_posting.status is JobPostingStatus.EXPIRED
    assert stored_posting.unpublished_at == _EXPIRY_TIME

    assert audit is not None
    assert audit.actor_subject == SYSTEM_SUBJECT
    assert audit.details["expired_at"] == _EXPIRY_TIME.isoformat()
    assert "title" not in audit.details
    assert "description" not in audit.details
    assert "department" not in audit.details
    assert "location" not in audit.details


@pytest.mark.asyncio
async def test_rejects_unbounded_or_invalid_batch_sizes(
    session: AsyncSession,
) -> None:
    """Prevent unexpectedly large expiry transactions."""
    with pytest.raises(ValueError, match="batch size"):
        await expire_due_job_postings(
            session,
            batch_size=0,
            now=_EXPIRY_TIME,
        )

    with pytest.raises(ValueError, match="batch size"):
        await expire_due_job_postings(
            session,
            batch_size=101,
            now=_EXPIRY_TIME,
        )
