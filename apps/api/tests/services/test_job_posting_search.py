"""PostgreSQL tests for tenant job-posting management read models."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.job_posting_errors import (
    InvalidJobPostingCursorError,
    JobPostingAccessDeniedError,
    JobPostingValidationError,
)
from app.services.job_postings import (
    JobPostingSearchFilters,
    get_job_posting,
    list_job_postings,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build an authenticated tenant-local management context."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="job-posting-search-test-request-id",
    )


async def _seed_postings(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    prefix: str,
) -> tuple[list[JobPosting], Requisition]:
    """Create a tenant requisition and mixed-visibility management postings."""
    now = datetime.now(UTC).replace(microsecond=0)

    session.add(
        Tenant(
            id=tenant_id,
            name=f"Job Posting Search Tenant {prefix}",
            slug=f"job-posting-search-{prefix}-{tenant_id.hex[:8]}",
        )
    )
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title="Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    session.add(requisition)
    await session.flush()

    postings = [
        JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            public_id=uuid4(),
            slug=f"backend-engineer-{prefix}-draft",
            title="Backend Engineer Draft",
            employment_type=EmploymentType.FULL_TIME,
            status=JobPostingStatus.DRAFT,
            created_by_subject="seed",
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
        ),
        JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            public_id=uuid4(),
            slug=f"backend-engineer-{prefix}-published",
            title="Backend Engineer Published",
            employment_type=EmploymentType.CONTRACT,
            status=JobPostingStatus.PUBLISHED,
            published_at=now - timedelta(hours=1),
            created_by_subject="seed",
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
        ),
        JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            public_id=uuid4(),
            slug=f"backend-engineer-{prefix}-unpublished",
            title="Backend Engineer Unpublished",
            employment_type=EmploymentType.PART_TIME,
            status=JobPostingStatus.UNPUBLISHED,
            published_at=now - timedelta(days=2),
            unpublished_at=now - timedelta(days=1),
            created_by_subject="seed",
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
        ),
    ]
    session.add_all(postings)
    await session.commit()

    return postings, requisition


@pytest.mark.asyncio
async def test_lists_all_management_posting_states_and_filters(
    session: AsyncSession,
) -> None:
    """Internal management listing includes non-public posting lifecycle states."""
    tenant_id = uuid4()
    postings, requisition = await _seed_postings(
        session,
        tenant_id=tenant_id,
        prefix="owner",
    )

    published = await list_job_postings(
        session,
        context=_context(tenant_id),
        filters=JobPostingSearchFilters(
            requisition_id=requisition.id,
            status=JobPostingStatus.PUBLISHED,
            employment_type=EmploymentType.CONTRACT,
        ),
    )

    all_postings = await list_job_postings(
        session,
        context=_context(tenant_id),
    )

    assert [posting.id for posting in published.items] == [postings[1].id]
    assert [posting.id for posting in all_postings.items] == [
        postings[2].id,
        postings[1].id,
        postings[0].id,
    ]


@pytest.mark.asyncio
async def test_filters_by_publication_range(
    session: AsyncSession,
) -> None:
    """Published date bounds apply only to records that were published."""
    tenant_id = uuid4()
    postings, _ = await _seed_postings(
        session,
        tenant_id=tenant_id,
        prefix="owner",
    )
    now = datetime.now(UTC)

    result = await list_job_postings(
        session,
        context=_context(tenant_id),
        filters=JobPostingSearchFilters(
            published_after=now - timedelta(hours=2),
            published_before=now,
        ),
    )

    assert [posting.id for posting in result.items] == [postings[1].id]


@pytest.mark.asyncio
async def test_uses_stable_non_duplicating_cursor_pages(
    session: AsyncSession,
) -> None:
    """Return every job posting exactly once across keyset pages."""
    tenant_id = uuid4()
    postings, _ = await _seed_postings(
        session,
        tenant_id=tenant_id,
        prefix="owner",
    )

    first_page = await list_job_postings(
        session,
        context=_context(tenant_id),
        limit=2,
    )
    second_page = await list_job_postings(
        session,
        context=_context(tenant_id),
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [
        posting.id
        for posting in first_page.items + second_page.items
    ]

    assert returned_ids == [
        postings[2].id,
        postings[1].id,
        postings[0].id,
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_enforces_read_roles_and_tenant_isolation(
    session: AsyncSession,
) -> None:
    """Hide other tenants' job postings and reject unauthorized roles."""
    owner_tenant_id = uuid4()
    caller_tenant_id = uuid4()

    owner_postings, _ = await _seed_postings(
        session,
        tenant_id=owner_tenant_id,
        prefix="owner",
    )
    await _seed_postings(
        session,
        tenant_id=caller_tenant_id,
        prefix="caller",
    )

    hidden = await list_job_postings(
        session,
        context=_context(caller_tenant_id),
        filters=JobPostingSearchFilters(
            requisition_id=owner_postings[0].requisition_id,
        ),
    )

    with pytest.raises(JobPostingAccessDeniedError):
        await get_job_posting(
            session,
            context=_context(
                owner_tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            job_posting_id=owner_postings[0].id,
        )

    assert hidden.items == []


@pytest.mark.asyncio
async def test_rejects_invalid_cursor_and_publication_date_range(
    session: AsyncSession,
) -> None:
    """Reject malformed keysets and contradictory or naive date filters."""
    tenant_id = uuid4()
    await _seed_postings(
        session,
        tenant_id=tenant_id,
        prefix="owner",
    )
    now = datetime.now(UTC)

    with pytest.raises(InvalidJobPostingCursorError):
        await list_job_postings(
            session,
            context=_context(tenant_id),
            cursor="not-a-valid-cursor",
        )

    with pytest.raises(JobPostingValidationError, match="published_after"):
        await list_job_postings(
            session,
            context=_context(tenant_id),
            filters=JobPostingSearchFilters(
                published_after=now,
                published_before=now - timedelta(days=1),
            ),
        )

    with pytest.raises(JobPostingValidationError, match="published_after"):
        await list_job_postings(
            session,
            context=_context(tenant_id),
            filters=JobPostingSearchFilters(
                published_after=datetime.now(),
            ),
        )
