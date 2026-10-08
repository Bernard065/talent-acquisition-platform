"""PostgreSQL integration tests for tenant-scoped job posting workflows."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
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
from app.services.job_posting_errors import (
    JobPostingAccessDeniedError,
    JobPostingNotFoundError,
    JobPostingRequisitionNotOpenError,
    JobPostingVersionConflictError,
)
from app.services.job_postings import (
    CreateJobPostingCommand,
    create_job_posting,
    publish_job_posting,
    unpublish_job_postings_for_requisition,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "recruiter-subject",
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified internal caller context for one tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="job-posting-service-test-request-id",
    )


async def _seed_requisition(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    title: str = "Senior Backend Engineer",
    status: RequisitionStatus = RequisitionStatus.OPEN,
) -> Requisition:
    """Create a tenant and one requisition suitable for posting tests."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Job Posting Tenant {tenant_id.hex[:12]}",
            slug=f"job-posting-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title=title,
        description="Public engineering role description.",
        department="Engineering",
        location="Nairobi, Kenya",
        headcount=1,
        status=status,
        created_by_subject="recruiter-subject",
    )
    session.add(requisition)
    await session.commit()

    return requisition


async def _install_snapshot_immutability_trigger(
    session: AsyncSession,
) -> None:
    """
    Install the production trigger because metadata-based test setup does not
    execute Alembic migrations.
    """
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION
            prevent_published_job_posting_snapshot_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF OLD.published_at IS NOT NULL
                   AND (
                        NEW.title IS DISTINCT FROM OLD.title
                        OR NEW.description IS DISTINCT FROM OLD.description
                        OR NEW.department IS DISTINCT FROM OLD.department
                        OR NEW.location IS DISTINCT FROM OLD.location
                        OR NEW.employment_type IS DISTINCT FROM OLD.employment_type
                   )
                THEN
                    RAISE EXCEPTION
                        USING
                            ERRCODE = '23514',
                            MESSAGE = 'Published job posting public snapshot cannot be changed';
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    await session.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
            trg_job_postings_protect_published_snapshot ON job_postings;
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER trg_job_postings_protect_published_snapshot
            BEFORE UPDATE ON job_postings
            FOR EACH ROW
            EXECUTE FUNCTION prevent_published_job_posting_snapshot_mutation();
            """
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_creates_collision_safe_tenant_scoped_slugs_and_safe_audits(
    session: AsyncSession,
) -> None:
    """Allocate deterministic suffixes and never copy public content into audit data."""
    tenant_id = uuid4()
    first_requisition = await _seed_requisition(
        session,
        tenant_id=tenant_id,
    )

    second_requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        description="Different public role description.",
        department="Engineering",
        location="Nairobi, Kenya",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="recruiter-subject",
    )
    session.add(second_requisition)
    await session.commit()

    first = await create_job_posting(
        session,
        context=_context(tenant_id),
        requisition_id=first_requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )
    second = await create_job_posting(
        session,
        context=_context(tenant_id),
        requisition_id=second_requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )

    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action == "job_posting.created",
            )
        )
    )

    assert first.slug == "senior-backend-engineer"
    assert second.slug == "senior-backend-engineer-2"
    assert first.public_id != second.public_id
    assert first.status is JobPostingStatus.DRAFT
    assert first.title == first_requisition.title
    assert first.description == first_requisition.description
    assert len(audits) == 2
    assert "Public engineering role description." not in str(
        [audit.details for audit in audits]
    )


@pytest.mark.asyncio
async def test_publishes_only_open_requisition_and_uses_current_version(
    session: AsyncSession,
) -> None:
    """Require an open requisition and a fresh optimistic-lock version."""
    tenant_id = uuid4()
    requisition = await _seed_requisition(
        session,
        tenant_id=tenant_id,
        status=RequisitionStatus.APPROVED,
    )
    posting = await create_job_posting(
        session,
        context=_context(tenant_id),
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.CONTRACT,
        ),
    )
    posting_id = posting.id

    with pytest.raises(JobPostingRequisitionNotOpenError):
        await publish_job_posting(
            session,
            context=_context(tenant_id),
            job_posting_id=posting.id,
            expected_version=1,
        )

    requisition.status = RequisitionStatus.OPEN
    await session.commit()

    published = await publish_job_posting(
        session,
        context=_context(tenant_id),
        job_posting_id=posting_id,
        expected_version=1,
    )
    published_status = published.status
    published_at = published.published_at
    published_version = published.version
    requisition_id = requisition.id

    with pytest.raises(JobPostingVersionConflictError):
        await publish_job_posting(
            session,
            context=_context(tenant_id),
            job_posting_id=posting_id,
            expected_version=1,
        )

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == str(posting_id),
            AuditEvent.action == "job_posting.published",
        )
    )

    assert published_status is JobPostingStatus.PUBLISHED
    assert published_at is not None
    assert published_version == 2
    assert audit is not None
    assert audit.details["requisition_id"] == str(requisition_id)
    assert "description" not in audit.details


@pytest.mark.asyncio
async def test_hides_postings_across_tenants_and_rejects_unauthorized_roles(
    session: AsyncSession,
) -> None:
    """Never reveal another tenant's posting and enforce management roles."""
    owner_tenant_id = uuid4()
    requisition = await _seed_requisition(
        session,
        tenant_id=owner_tenant_id,
    )
    posting = await create_job_posting(
        session,
        context=_context(owner_tenant_id),
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )

    with pytest.raises(JobPostingAccessDeniedError):
        await publish_job_posting(
            session,
            context=_context(
                owner_tenant_id,
                subject="unrelated-user",
                roles=frozenset({Role.INTERVIEWER}),
            ),
            job_posting_id=posting.id,
            expected_version=1,
        )

    with pytest.raises(JobPostingNotFoundError):
        await publish_job_posting(
            session,
            context=_context(uuid4()),
            job_posting_id=posting.id,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_automatically_unpublishes_all_published_requisition_postings(
    session: AsyncSession,
) -> None:
    """Provide an atomic hook for requisition close or cancellation."""
    tenant_id = uuid4()
    requisition = await _seed_requisition(
        session,
        tenant_id=tenant_id,
    )
    posting = await create_job_posting(
        session,
        context=_context(tenant_id),
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )
    published = await publish_job_posting(
        session,
        context=_context(tenant_id),
        job_posting_id=posting.id,
        expected_version=1,
    )

    requisition.status = RequisitionStatus.CLOSED
    await session.commit()

    unpublished = await unpublish_job_postings_for_requisition(
        session,
        context=_context(tenant_id),
        requisition_id=requisition.id,
        reason="requisition_closed",
    )

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == str(published.id),
            AuditEvent.action == "job_posting.unpublished",
        )
    )

    assert [item.id for item in unpublished] == [published.id]
    assert unpublished[0].status is JobPostingStatus.UNPUBLISHED
    assert unpublished[0].unpublished_at is not None
    assert audit is not None
    assert audit.details["reason"] == "requisition_closed"


@pytest.mark.asyncio
async def test_database_trigger_rejects_published_snapshot_mutation(
    session: AsyncSession,
) -> None:
    """Database enforcement prevents bypassing immutable public snapshots."""
    tenant_id = uuid4()
    requisition = await _seed_requisition(
        session,
        tenant_id=tenant_id,
    )
    posting = await create_job_posting(
        session,
        context=_context(tenant_id),
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(
            employment_type=EmploymentType.FULL_TIME,
        ),
    )
    published = await publish_job_posting(
        session,
        context=_context(tenant_id),
        job_posting_id=posting.id,
        expected_version=1,
    )
    posting_id = posting.id
    await _install_snapshot_immutability_trigger(session)

    published.title = "Mutated public title"

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()

    persisted = await session.scalar(
        select(JobPosting).where(JobPosting.id == posting_id)
    )

    assert persisted is not None
    assert persisted.title == "Senior Backend Engineer"
    assert persisted.status is JobPostingStatus.PUBLISHED

    assert persisted is not None
    assert persisted.title == "Senior Backend Engineer"
    assert persisted.status is JobPostingStatus.PUBLISHED
