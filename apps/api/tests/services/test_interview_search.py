"""PostgreSQL tests for tenant-scoped interview schedule search."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import (
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.interview_search import (
    InterviewSearchFilters,
    search_interviews,
)
from app.services.interview_search_errors import (
    InterviewSearchAccessDeniedError,
    InvalidInterviewSearchCursorError,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "recruiter-subject",
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for one tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="interview-search-service-test-request-id",
    )


async def _seed_interviews(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[list[InterviewSession], dict[str, User]]:
    """Create tenant users, one application, and three calendar sessions."""
    now = datetime.now(UTC).replace(microsecond=0)

    session.add(
        Tenant(
            id=tenant_id,
            name=f"Interview Search Tenant {tenant_id.hex[:12]}",
            slug=f"interview-search-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    users = {
        "recruiter": User(
            tenant_id=tenant_id,
            external_subject="recruiter-subject",
            email=f"recruiter-{tenant_id.hex[:8]}@example.test",
            display_name="Recruiter",
        ),
        "interviewer_one": User(
            tenant_id=tenant_id,
            external_subject="interviewer-one-subject",
            email=f"interviewer-one-{tenant_id.hex[:8]}@example.test",
            display_name="Interviewer One",
        ),
        "interviewer_two": User(
            tenant_id=tenant_id,
            external_subject="interviewer-two-subject",
            email=f"interviewer-two-{tenant_id.hex[:8]}@example.test",
            display_name="Interviewer Two",
        ),
    }
    session.add_all(users.values())

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:8]}@example.test",
        normalized_email=f"ada-{tenant_id.hex[:8]}@example.test",
        source="public_job",
        source_metadata={},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="seed",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.INTERVIEW,
        created_by_subject="seed",
    )
    session.add(application)
    await session.flush()

    sessions = [
        InterviewSession(
            tenant_id=tenant_id,
            application_id=application.id,
            scheduled_start_at=now + timedelta(hours=3),
            scheduled_end_at=now + timedelta(hours=4),
            status=InterviewSessionStatus.SCHEDULED,
            created_by_subject="recruiter-subject",
        ),
        InterviewSession(
            tenant_id=tenant_id,
            application_id=application.id,
            scheduled_start_at=now + timedelta(hours=2),
            scheduled_end_at=now + timedelta(hours=3),
            status=InterviewSessionStatus.COMPLETED,
            completed_at=now + timedelta(hours=3),
            created_by_subject="recruiter-subject",
        ),
        InterviewSession(
            tenant_id=tenant_id,
            application_id=application.id,
            scheduled_start_at=now + timedelta(hours=1),
            scheduled_end_at=now + timedelta(hours=2),
            status=InterviewSessionStatus.SCHEDULED,
            created_by_subject="recruiter-subject",
        ),
    ]
    session.add_all(sessions)
    await session.flush()

    session.add_all(
        [
            InterviewParticipant(
                tenant_id=tenant_id,
                interview_session_id=sessions[0].id,
                user_id=users["interviewer_one"].id,
                role=InterviewParticipantRole.INTERVIEWER,
                scheduled_time_range=Range(
                    sessions[0].scheduled_start_at,
                    sessions[0].scheduled_end_at,
                    bounds="[)",
                ),
            ),
            InterviewParticipant(
                tenant_id=tenant_id,
                interview_session_id=sessions[1].id,
                user_id=users["interviewer_two"].id,
                role=InterviewParticipantRole.INTERVIEWER,
                scheduled_time_range=Range(
                    sessions[1].scheduled_start_at,
                    sessions[1].scheduled_end_at,
                    bounds="[)",
                ),
            ),
            InterviewParticipant(
                tenant_id=tenant_id,
                interview_session_id=sessions[2].id,
                user_id=users["interviewer_one"].id,
                role=InterviewParticipantRole.INTERVIEWER,
                scheduled_time_range=Range(
                    sessions[2].scheduled_start_at,
                    sessions[2].scheduled_end_at,
                    bounds="[)",
                ),
            ),
        ]
    )
    await session.commit()

    return sessions, users


@pytest.mark.asyncio
async def test_recruiter_filters_by_participant_status_and_calendar_range(
    session: AsyncSession,
) -> None:
    """Broad recruiting roles can apply tenant-local schedule filters."""
    tenant_id = uuid4()
    sessions, users = await _seed_interviews(session, tenant_id=tenant_id)

    participant_page = await search_interviews(
        session,
        context=_context(tenant_id),
        filters=InterviewSearchFilters(
            participant_user_id=users["interviewer_one"].id,
        ),
    )
    completed_page = await search_interviews(
        session,
        context=_context(tenant_id),
        filters=InterviewSearchFilters(
            status=InterviewSessionStatus.COMPLETED,
        ),
    )
    range_page = await search_interviews(
        session,
        context=_context(tenant_id),
        filters=InterviewSearchFilters(
            scheduled_after=sessions[1].scheduled_start_at,
            scheduled_before=sessions[1].scheduled_start_at,
        ),
    )

    assert [item.id for item in participant_page.items] == [
        sessions[0].id,
        sessions[2].id,
    ]
    assert [item.id for item in completed_page.items] == [sessions[1].id]
    assert [item.id for item in range_page.items] == [sessions[1].id]


@pytest.mark.asyncio
async def test_interviewer_can_view_only_own_sessions(
    session: AsyncSession,
) -> None:
    """An interviewer cannot use calendar search to inspect others' sessions."""
    tenant_id = uuid4()
    sessions, users = await _seed_interviews(session, tenant_id=tenant_id)

    own_page = await search_interviews(
        session,
        context=_context(
            tenant_id,
            subject="interviewer-one-subject",
            roles=frozenset({Role.INTERVIEWER}),
        ),
    )

    with pytest.raises(InterviewSearchAccessDeniedError):
        await search_interviews(
            session,
            context=_context(
                tenant_id,
                subject="interviewer-one-subject",
                roles=frozenset({Role.INTERVIEWER}),
            ),
            filters=InterviewSearchFilters(
                participant_user_id=users["interviewer_two"].id,
            ),
        )

    assert [item.id for item in own_page.items] == [
        sessions[0].id,
        sessions[2].id,
    ]


@pytest.mark.asyncio
async def test_search_uses_stable_non_duplicating_cursor_pages(
    session: AsyncSession,
) -> None:
    """Return each schedule record exactly once across keyset pages."""
    tenant_id = uuid4()
    sessions, _ = await _seed_interviews(session, tenant_id=tenant_id)

    first_page = await search_interviews(
        session,
        context=_context(tenant_id),
        limit=2,
    )
    second_page = await search_interviews(
        session,
        context=_context(tenant_id),
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [
        item.id
        for item in first_page.items + second_page.items
    ]

    assert returned_ids == [
        sessions[0].id,
        sessions[1].id,
        sessions[2].id,
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_hides_other_tenant_interviews(
    session: AsyncSession,
) -> None:
    """Tenant scope prevents cross-organization interview discovery."""
    owner_tenant_id = uuid4()
    caller_tenant_id = uuid4()

    owner_sessions, _ = await _seed_interviews(
        session,
        tenant_id=owner_tenant_id,
    )
    await _seed_interviews(
        session,
        tenant_id=caller_tenant_id,
    )

    hidden = await search_interviews(
        session,
        context=_context(caller_tenant_id),
        filters=InterviewSearchFilters(
            application_id=owner_sessions[0].application_id,
        ),
    )

    assert hidden.items == []


@pytest.mark.asyncio
async def test_rejects_invalid_cursor_and_invalid_calendar_range(
    session: AsyncSession,
) -> None:
    """Reject malformed pagination state and contradictory schedule bounds."""
    tenant_id = uuid4()
    sessions, _ = await _seed_interviews(session, tenant_id=tenant_id)

    with pytest.raises(InvalidInterviewSearchCursorError):
        await search_interviews(
            session,
            context=_context(tenant_id),
            cursor="not-a-valid-cursor",
        )

    with pytest.raises(ValueError, match="scheduled_after"):
        await search_interviews(
            session,
            context=_context(tenant_id),
            filters=InterviewSearchFilters(
                scheduled_after=sessions[0].scheduled_start_at,
                scheduled_before=sessions[2].scheduled_start_at,
            ),
        )
