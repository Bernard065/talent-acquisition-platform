"""PostgreSQL tests for tenant-scoped recruiter search read models."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_errors import CandidateAccessDeniedError
from app.services.recruiting_search import (
    ApplicationSearchFilters,
    CandidateSearchFilters,
    search_applications,
    search_candidates,
)
from app.services.recruiting_search_errors import (
    InvalidRecruitingSearchCursorError,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build one verified recruiter context."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="recruiting-search-test-request-id",
    )


async def _seed_tenant_records(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    created_at: datetime,
) -> tuple[list[Candidate], list[Application]]:
    """Create tenant-local candidates and applications with stable timestamps."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Recruiting Search Tenant {tenant_id.hex[:12]}",
            slug=f"recruiting-search-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    session.add(requisition)
    await session.flush()

    candidates = [
        Candidate(
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"ada-{tenant_id.hex[:8]}@example.test",
            location="Nairobi, Kenya",
            source="public_job",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
            created_at=created_at,
        ),
        Candidate(
            tenant_id=tenant_id,
            full_name="Grace Hopper",
            email=f"grace-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"grace-{tenant_id.hex[:8]}@example.test",
            location="Remote - Kenya",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="seed",
            created_at=created_at - timedelta(minutes=1),
        ),
        Candidate(
            tenant_id=tenant_id,
            full_name="C_Developer% Specialist",
            email=f"escaped-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"escaped-{tenant_id.hex[:8]}@example.test",
            location="Mombasa, Kenya",
            source="agency",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
            created_at=created_at - timedelta(minutes=2),
        ),
        Candidate(
            tenant_id=tenant_id,
            full_name="Cadeveloper-other",
            email=f"other-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"other-{tenant_id.hex[:8]}@example.test",
            location="Kisumu, Kenya",
            source="agency",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
            created_at=created_at - timedelta(minutes=3),
        ),
    ]
    session.add_all(candidates)
    await session.flush()

    applications = [
        Application(
            tenant_id=tenant_id,
            candidate_id=candidates[0].id,
            requisition_id=requisition.id,
            status=ApplicationStatus.APPLIED,
            applied_at=created_at,
            created_by_subject="seed",
        ),
        Application(
            tenant_id=tenant_id,
            candidate_id=candidates[1].id,
            requisition_id=requisition.id,
            status=ApplicationStatus.INTERVIEW,
            applied_at=created_at - timedelta(minutes=1),
            created_by_subject="seed",
        ),
        Application(
            tenant_id=tenant_id,
            candidate_id=candidates[2].id,
            requisition_id=requisition.id,
            status=ApplicationStatus.REJECTED,
            applied_at=created_at - timedelta(minutes=2),
            created_by_subject="seed",
        ),
    ]
    session.add_all(applications)
    await session.commit()

    return candidates, applications


@pytest.mark.asyncio
async def test_filters_candidates_and_escapes_search_text(
    session: AsyncSession,
) -> None:
    """Apply tenant-local filters and treat wildcard characters literally."""
    tenant_id = uuid4()
    candidates, _ = await _seed_tenant_records(
        session,
        tenant_id=tenant_id,
        created_at=datetime.now(UTC),
    )

    filtered = await search_candidates(
        session,
        context=_context(tenant_id),
        filters=CandidateSearchFilters(
            source="public_job",
            location="nairobi",
            consent_status=CandidateConsentStatus.GRANTED,
        ),
    )
    escaped_query = await search_candidates(
        session,
        context=_context(tenant_id),
        filters=CandidateSearchFilters(query="C_Developer%"),
    )

    assert [candidate.id for candidate in filtered.items] == [candidates[0].id]
    assert [candidate.id for candidate in escaped_query.items] == [
        candidates[2].id
    ]


@pytest.mark.asyncio
async def test_candidate_search_uses_stable_non_duplicating_cursor_pages(
    session: AsyncSession,
) -> None:
    """Return deterministic descending pages without duplicate candidates."""
    tenant_id = uuid4()
    candidates, _ = await _seed_tenant_records(
        session,
        tenant_id=tenant_id,
        created_at=datetime.now(UTC),
    )

    first_page = await search_candidates(
        session,
        context=_context(tenant_id),
        limit=2,
    )
    second_page = await search_candidates(
        session,
        context=_context(tenant_id),
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [
        candidate.id
        for candidate in first_page.items + second_page.items
    ]

    assert returned_ids == [
        candidates[0].id,
        candidates[1].id,
        candidates[2].id,
        candidates[3].id,
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_filters_applications_and_respects_date_bounds(
    session: AsyncSession,
) -> None:
    """Filter applications by pipeline state, candidate, and applied dates."""
    tenant_id = uuid4()
    now = datetime.now(UTC)
    candidates, applications = await _seed_tenant_records(
        session,
        tenant_id=tenant_id,
        created_at=now,
    )

    interview_page = await search_applications(
        session,
        context=_context(tenant_id),
        filters=ApplicationSearchFilters(
            status=ApplicationStatus.INTERVIEW,
            candidate_id=candidates[1].id,
            applied_after=now - timedelta(minutes=90),
            applied_before=now - timedelta(seconds=30),
        ),
    )

    assert [application.id for application in interview_page.items] == [
        applications[1].id
    ]


@pytest.mark.asyncio
async def test_hides_other_tenant_records_and_rejects_unauthorized_roles(
    session: AsyncSession,
) -> None:
    """Tenant filters and role checks protect candidate PII."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()

    owner_candidates, owner_applications = await _seed_tenant_records(
        session,
        tenant_id=owner_tenant_id,
        created_at=datetime.now(UTC),
    )
    await _seed_tenant_records(
        session,
        tenant_id=other_tenant_id,
        created_at=datetime.now(UTC),
    )

    hidden_candidates = await search_candidates(
        session,
        context=_context(other_tenant_id),
        filters=CandidateSearchFilters(query="Ada Lovelace"),
    )
    hidden_applications = await search_applications(
        session,
        context=_context(other_tenant_id),
        filters=ApplicationSearchFilters(
            candidate_id=owner_candidates[0].id,
        ),
    )

    with pytest.raises(CandidateAccessDeniedError):
        await search_candidates(
            session,
            context=_context(
                owner_tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
        )

    assert owner_candidates[0].id not in [
        candidate.id for candidate in hidden_candidates.items
    ]
    assert owner_applications[0].id not in [
        application.id for application in hidden_applications.items
    ]


@pytest.mark.asyncio
async def test_rejects_invalid_cursor_and_invalid_date_range(
    session: AsyncSession,
) -> None:
    """Reject malformed keyset state and contradictory date filters."""
    tenant_id = uuid4()
    now = datetime.now(UTC)
    await _seed_tenant_records(
        session,
        tenant_id=tenant_id,
        created_at=now,
    )

    with pytest.raises(InvalidRecruitingSearchCursorError):
        await search_candidates(
            session,
            context=_context(tenant_id),
            cursor="not-a-valid-cursor",
        )

    with pytest.raises(ValueError, match="applied_after"):
        await search_applications(
            session,
            context=_context(tenant_id),
            filters=ApplicationSearchFilters(
                applied_after=now,
                applied_before=now - timedelta(days=1),
            ),
        )
