"""PostgreSQL tests for requisition-driven job posting visibility changes."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services import requisition_workflow
from app.services.job_postings import (
    CreateJobPostingCommand,
    create_job_posting,
    publish_job_posting,
)


def _context(tenant_id: UUID) -> TenantContext:
    """Build a recruiter context authorized for both workflow operations."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="requisition-posting-visibility-test-request-id",
    )


async def _seed_published_posting(
    session: AsyncSession,
) -> tuple[UUID, Requisition, JobPosting]:
    """Create an open requisition with one published public job posting."""
    tenant_id = uuid4()
    context = _context(tenant_id)

    session.add(
        Tenant(
            id=tenant_id,
            name=f"Visibility Tenant {tenant_id.hex[:12]}",
            slug=f"visibility-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        description="Public engineering role.",
        department="Engineering",
        location="Nairobi, Kenya",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject=context.subject,
    )
    session.add(requisition)
    await session.commit()

    draft = await create_job_posting(
        session,
        context=context,
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )
    published = await publish_job_posting(
        session,
        context=context,
        job_posting_id=draft.id,
        expected_version=draft.version,
    )

    return tenant_id, requisition, published


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_status", "expected_reason"),
    [
        (RequisitionStatus.CLOSED, "requisition_closed"),
        (RequisitionStatus.CANCELLED, "requisition_cancelled"),
    ],
)
async def test_terminal_requisition_transition_unpublishes_postings_atomically(
    session: AsyncSession,
    target_status: RequisitionStatus,
    expected_reason: str,
) -> None:
    """Closing or cancelling a requisition removes public visibility immediately."""
    tenant_id, requisition, published = await _seed_published_posting(session)
    context = _context(tenant_id)

    transitioned = await requisition_workflow.transition_requisition_status(
        session,
        context=context,
        requisition_id=requisition.id,
        target_status=target_status,
    )
    await session.refresh(published)

    posting_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == str(published.id),
            AuditEvent.action == "job_posting.unpublished",
        )
    )

    requisition_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == str(requisition.id),
            AuditEvent.action == "requisition.status_changed",
        )
    )

    assert transitioned.status is target_status
    assert published.status is JobPostingStatus.UNPUBLISHED
    assert published.unpublished_at is not None
    assert posting_audit is not None
    assert posting_audit.details["reason"] == expected_reason
    assert requisition_audit is not None
    assert requisition_audit.details["target_status"] == target_status.value


@pytest.mark.asyncio
async def test_non_terminal_requisition_transition_keeps_posting_published(
    session: AsyncSession,
) -> None:
    """Putting a requisition on hold does not remove its posting automatically."""
    tenant_id, requisition, published = await _seed_published_posting(session)

    transitioned = await requisition_workflow.transition_requisition_status(
        session,
        context=_context(tenant_id),
        requisition_id=requisition.id,
        target_status=RequisitionStatus.ON_HOLD,
    )
    await session.refresh(published)

    unpublish_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(published.id),
            AuditEvent.action == "job_posting.unpublished",
        )
    )

    assert transitioned.status is RequisitionStatus.ON_HOLD
    assert published.status is JobPostingStatus.PUBLISHED
    assert published.unpublished_at is None
    assert unpublish_audit is None


@pytest.mark.asyncio
async def test_requisition_transition_rolls_back_when_unpublish_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The requisition cannot close if its public visibility update fails."""
    tenant_id, requisition, published = await _seed_published_posting(session)
    requisition_id = requisition.id
    posting_id = published.id

    async def fail_unpublish(**_: object) -> tuple[JobPosting, ...]:
        raise RuntimeError("simulated job posting persistence failure")

    monkeypatch.setattr(
        requisition_workflow,
        "unpublish_job_postings_for_requisition",
        fail_unpublish,
    )

    with pytest.raises(RuntimeError, match="simulated"):
        await requisition_workflow.transition_requisition_status(
            session,
            context=_context(tenant_id),
            requisition_id=requisition_id,
            target_status=RequisitionStatus.CLOSED,
        )

    await session.rollback()

    persisted_requisition = await session.get(Requisition, requisition_id)
    persisted_posting = await session.get(JobPosting, posting_id)

    assert persisted_requisition is not None
    assert persisted_posting is not None
    assert persisted_requisition.status is RequisitionStatus.OPEN
    assert persisted_posting.status is JobPostingStatus.PUBLISHED
