"""PostgreSQL tests for the provider-neutral job-board publication foundation."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.job_board_publication import JobBoardPublication
from app.db.models.job_posting import JobPosting
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.job_boards.enums import JobBoardPublicationStatus
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.job_board_publication_errors import (
    JobBoardPublicationAccessDeniedError,
    JobBoardPublicationConflictError,
    JobBoardPublicationNotFoundError,
    JobBoardPublicationValidationError,
)
from app.services.job_board_publications import (
    request_job_board_publication,
    request_job_board_unpublication,
)
from app.services.job_posting_expiry import expire_due_job_postings
from app.services.job_postings import (
    CreateJobPostingCommand,
    create_job_posting,
    publish_job_posting,
    unpublish_job_posting,
)
from app.services.requisition_workflow import transition_requisition_status


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
    subject: str = "board-recruiter",
) -> TenantContext:
    """Build a trusted caller context for one tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="job-board-publication-test-request",
    )


async def _seed_published_posting(
    session: AsyncSession,
) -> tuple[TenantContext, Requisition, JobPosting]:
    """Create one tenant-owned, locally published posting with sensitive sentinels."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Board Tenant {tenant_id.hex[:12]}",
            slug=f"board-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title="Private Sentinel Job Title",
        description="Private Sentinel Description",
        department="Engineering",
        location="Nairobi",
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
        command=CreateJobPostingCommand(employment_type=EmploymentType.FULL_TIME),
    )
    posting = await publish_job_posting(
        session,
        context=context,
        job_posting_id=draft.id,
        expected_version=draft.version,
    )
    return context, requisition, posting


@pytest.mark.asyncio
async def test_publication_request_is_idempotent_and_privacy_safe(
    session: AsyncSession,
) -> None:
    """Persist one identifier-only outbox request and audit event per operation."""
    context, _, posting = await _seed_published_posting(session)

    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="  Board_A  ",
    )
    replay = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="board_a",
    )

    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == context.tenant_id,
                OutboxEvent.aggregate_id == str(publication.id),
            )
        )
    )
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == context.tenant_id,
                AuditEvent.entity_id == str(publication.id),
                AuditEvent.action == "job_board.publication.publish_requested",
            )
        )
    )

    assert publication.id == replay.id
    assert publication.status is JobBoardPublicationStatus.PUBLISH_REQUESTED
    assert publication.provider_key == "board_a"
    assert len(events) == 1
    assert events[0].event_type == "job_board.publish_requested"
    assert events[0].payload == {
        "publication_id": str(publication.id),
        "version": publication.version,
        "provider_key": "board_a",
        "operation": "publish",
    }
    assert len(audits) == 1

    serialized_private_data = str(events[0].payload) + str(audits[0].details)
    assert "Private Sentinel Job Title" not in serialized_private_data
    assert "Private Sentinel Description" not in serialized_private_data


@pytest.mark.asyncio
async def test_publication_requires_authorized_role_and_published_job(
    session: AsyncSession,
) -> None:
    """Reject non-recruiters and drafts before creating persistent work."""
    context, _, posting = await _seed_published_posting(session)

    with pytest.raises(JobBoardPublicationAccessDeniedError):
        await request_job_board_publication(
            session,
            context=_context(context.tenant_id, roles=frozenset({Role.INTERVIEWER})),
            job_posting_id=posting.id,
            provider_key="board_a",
        )

    draft = JobPosting(
        tenant_id=context.tenant_id,
        requisition_id=posting.requisition_id,
        slug=f"draft-{uuid4().hex[:10]}",
        title="Draft posting",
        employment_type=EmploymentType.FULL_TIME,
        status=JobPostingStatus.DRAFT,
        created_by_subject=context.subject,
    )
    session.add(draft)
    await session.commit()

    with pytest.raises(JobBoardPublicationConflictError):
        await request_job_board_publication(
            session,
            context=context,
            job_posting_id=draft.id,
            provider_key="board_a",
        )

    publication_count = len(
        (
            await session.scalars(
                select(JobBoardPublication.id).where(
                    JobBoardPublication.tenant_id == context.tenant_id
                )
            )
        ).all()
    )
    assert publication_count == 0


@pytest.mark.asyncio
async def test_tenant_isolation_hides_posting_and_publication(
    session: AsyncSession,
) -> None:
    """Other tenants cannot find postings or external publication records."""
    context, _, posting = await _seed_published_posting(session)
    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="board_a",
    )
    publication_id = publication.id
    other_tenant_id = uuid4()
    session.add(
        Tenant(
            id=other_tenant_id,
            name=f"Other Board Tenant {other_tenant_id.hex[:12]}",
            slug=f"other-board-{other_tenant_id.hex[:12]}",
        )
    )
    await session.commit()

    with pytest.raises(JobBoardPublicationNotFoundError):
        await request_job_board_publication(
            session,
            context=_context(other_tenant_id),
            job_posting_id=posting.id,
            provider_key="board_a",
        )

    with pytest.raises(JobBoardPublicationNotFoundError):
        await request_job_board_unpublication(
            session,
            context=_context(other_tenant_id),
            publication_id=publication_id,
        )


@pytest.mark.asyncio
async def test_provider_key_validation_rejects_noncanonical_input(
    session: AsyncSession,
) -> None:
    """Provider keys are opaque identifiers, never free-form endpoints or secrets."""
    context, _, posting = await _seed_published_posting(session)

    with pytest.raises(JobBoardPublicationValidationError):
        await request_job_board_publication(
            session,
            context=context,
            job_posting_id=posting.id,
            provider_key="https://attacker.example/secret",
        )


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_create_one_publication_and_event(
    database_engine: AsyncEngine,
) -> None:
    """Row/advisory locks and uniqueness prevent duplicate remote work."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as seed_session:
        context, _, posting = await _seed_published_posting(seed_session)

    async def request_in_own_session() -> UUID:
        async with session_factory() as request_session:
            publication = await request_job_board_publication(
                request_session,
                context=context,
                job_posting_id=posting.id,
                provider_key="board_a",
            )
            return publication.id

    first_id, second_id = await asyncio.gather(
        request_in_own_session(),
        request_in_own_session(),
    )
    async with session_factory() as verify_session:
        publications = list(
            await verify_session.scalars(
                select(JobBoardPublication).where(
                    JobBoardPublication.tenant_id == context.tenant_id,
                    JobBoardPublication.job_posting_id == posting.id,
                )
            )
        )
        events = list(
            await verify_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.tenant_id == context.tenant_id,
                    OutboxEvent.event_type == "job_board.publish_requested",
                )
            )
        )

    assert first_id == second_id
    assert len(publications) == 1
    assert len(events) == 1


@pytest.mark.asyncio
async def test_local_unpublish_atomically_requests_remote_unpublish(
    session: AsyncSession,
) -> None:
    """Public visibility and external-board removal are coordinated atomically."""
    context, _, posting = await _seed_published_posting(session)
    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="board_a",
    )
    await session.refresh(posting)

    updated_posting = await unpublish_job_posting(
        session,
        context=context,
        job_posting_id=posting.id,
        expected_version=posting.version,
    )
    await session.refresh(publication)

    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == context.tenant_id,
                OutboxEvent.aggregate_id == str(publication.id),
            )
        )
    )
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == context.tenant_id,
                AuditEvent.entity_id == str(publication.id),
            )
        )
    )

    assert updated_posting.status is JobPostingStatus.UNPUBLISHED
    assert publication.status is JobBoardPublicationStatus.UNPUBLISH_REQUESTED
    assert [event.event_type for event in events].count(
        "job_board.publish_requested"
    ) == 1
    assert [event.event_type for event in events].count(
        "job_board.unpublish_requested"
    ) == 1
    assert len(audits) == 2
    event_and_audit_data = str([event.payload for event in events]) + str(
        [audit.details for audit in audits]
    )
    assert "Private Sentinel Job Title" not in event_and_audit_data
    assert "Private Sentinel Description" not in event_and_audit_data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "expected_audit_reason"),
    [
        ("requisition_closed", "requisition_closed"),
        ("requisition_cancelled", "requisition_cancelled"),
    ],
)
async def test_requisition_lifecycle_atomically_requests_remote_unpublish(
    session: AsyncSession,
    reason: str,
    expected_audit_reason: str,
) -> None:
    """Closing or cancelling a requisition queues privacy-safe board removal."""
    context, requisition, posting = await _seed_published_posting(session)
    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="board_a",
    )
    publication_id = publication.id

    target_status = (
        RequisitionStatus.CLOSED
        if reason == "requisition_closed"
        else RequisitionStatus.CANCELLED
    )
    transitioned_requisition = await transition_requisition_status(
        session,
        context=context,
        requisition_id=requisition.id,
        target_status=target_status,
    )
    posting_after = await session.get(JobPosting, posting.id)
    publication_after = await session.get(JobBoardPublication, publication_id)
    removal_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(publication_id),
                OutboxEvent.event_type == "job_board.unpublish_requested",
            )
        )
    )
    removal_audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(publication_id),
                AuditEvent.action == "job_board.publication.unpublish_requested",
            )
        )
    )

    assert publication_after is not None
    assert publication_after.status is JobBoardPublicationStatus.UNPUBLISH_REQUESTED
    assert transitioned_requisition.status is target_status
    assert posting_after is not None
    assert posting_after.status is JobPostingStatus.UNPUBLISHED
    assert len(removal_events) == 1
    assert removal_events[0].payload["operation"] == "unpublish"
    assert len(removal_audits) == 1
    assert removal_audits[0].details["reason"] == expected_audit_reason
    assert "Private Sentinel Job Title" not in str(removal_events[0].payload)
    assert "Private Sentinel Description" not in str(removal_audits[0].details)

    requisition_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(requisition.id),
            AuditEvent.action == "requisition.status_changed",
        )
    )
    posting_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(posting.id),
            AuditEvent.action == "job_posting.unpublished",
        )
    )
    assert requisition_audit is not None
    assert posting_audit is not None


@pytest.mark.asyncio
async def test_scheduled_expiry_atomically_requests_remote_unpublish(
    session: AsyncSession,
) -> None:
    """The expiry worker coordinates public expiry and provider removal."""
    context, _, posting = await _seed_published_posting(session)
    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key="board_a",
    )
    publication_id = publication.id
    job_posting_id = posting.id
    expiry_time = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    posting.expires_at = expiry_time - timedelta(minutes=1)
    await session.commit()

    result = await expire_due_job_postings(
        session,
        now=expiry_time,
        batch_size=10,
    )
    expired_posting = await session.get(JobPosting, job_posting_id)
    publication_after = await session.get(JobBoardPublication, publication_id)
    removal_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(publication_id),
                OutboxEvent.event_type == "job_board.unpublish_requested",
            )
        )
    )

    assert result.expired_job_posting_ids == (job_posting_id,)
    assert expired_posting is not None
    assert expired_posting.status is JobPostingStatus.EXPIRED
    assert publication_after is not None
    assert publication_after.status is JobBoardPublicationStatus.UNPUBLISH_REQUESTED
    assert len(removal_events) == 1
    assert removal_events[0].payload["operation"] == "unpublish"
