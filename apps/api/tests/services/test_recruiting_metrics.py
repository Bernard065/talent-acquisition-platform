"""PostgreSQL integration tests for privacy-safe recruiting metrics."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.recruiting_metrics import (
    MetricsWindow,
    get_recruiting_metrics,
)
from app.services.recruiting_metrics_errors import (
    RecruitingMetricsAccessDeniedError,
    RecruitingMetricsValidationError,
)

_WINDOW_START = datetime(2026, 9, 1, tzinfo=UTC)
_WINDOW_END = datetime(2026, 9, 11, tzinfo=UTC)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] | None = None,
) -> TenantContext:
    """Build a verified caller context for one tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="analytics-user",
        roles=roles or frozenset({Role.ANALYST}),
        request_id="analytics-test-request",
    )


async def _add_application(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    position: int,
    source: str,
    applied_at: datetime,
    current_status: ApplicationStatus,
    transitions: list[
        tuple[
            ApplicationStatus | None,
            ApplicationStatus,
            datetime,
        ]
    ],
) -> Application:
    """Persist one application and its append-only stage history."""
    candidate = Candidate(
        tenant_id=tenant_id,
        full_name=f"Candidate {position}",
        email=f"candidate-{position}-{tenant_id.hex[:8]}@example.test",
        normalized_email=(
            f"candidate-{position}-{tenant_id.hex[:8]}@example.test"
        ),
        source=source,
        source_metadata={"internal_campaign_code": "ignored-by-analytics"},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="seed",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title=f"Platform Engineer {position}",
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
        status=current_status,
        applied_at=applied_at,
        created_by_subject="seed",
    )
    session.add(application)
    await session.flush()

    for from_status, to_status, transitioned_at in transitions:
        session.add(
            ApplicationStageHistory(
                tenant_id=tenant_id,
                application_id=application.id,
                from_status=from_status,
                to_status=to_status,
                transitioned_by_subject="seed",
                transitioned_at=transitioned_at,
            )
        )

    return application


async def _seed_metrics_data(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> None:
    """Create one tenant's typed lifecycle data for aggregate assertions."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Analytics Tenant {tenant_id.hex[:12]}",
            slug=f"analytics-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    await _add_application(
        session,
        tenant_id=tenant_id,
        position=1,
        source="employee_referral",
        applied_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        current_status=ApplicationStatus.HIRED,
        transitions=[
            (
                None,
                ApplicationStatus.APPLIED,
                datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
            ),
            (
                ApplicationStatus.APPLIED,
                ApplicationStatus.SCREENING,
                datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
            ),
            (
                ApplicationStatus.SCREENING,
                ApplicationStatus.INTERVIEW,
                datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
            ),
            (
                ApplicationStatus.INTERVIEW,
                ApplicationStatus.HIRED,
                datetime(2026, 9, 5, 9, 0, tzinfo=UTC),
            ),
        ],
    )

    await _add_application(
        session,
        tenant_id=tenant_id,
        position=2,
        source="job_board",
        applied_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
        current_status=ApplicationStatus.REJECTED,
        transitions=[
            (
                None,
                ApplicationStatus.APPLIED,
                datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
            ),
            (
                ApplicationStatus.APPLIED,
                ApplicationStatus.SCREENING,
                datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
            ),
            (
                ApplicationStatus.SCREENING,
                ApplicationStatus.REJECTED,
                datetime(2026, 9, 6, 10, 0, tzinfo=UTC),
            ),
        ],
    )

    await session.commit()


@pytest.mark.asyncio
async def test_returns_funnel_transitions_sources_and_time_to_hire(
    session: AsyncSession,
) -> None:
    """Return typed aggregate metrics for the caller's tenant and time window."""
    tenant_id = uuid4()
    await _seed_metrics_data(session, tenant_id=tenant_id)

    metrics = await get_recruiting_metrics(
        session,
        context=_context(tenant_id),
        window=MetricsWindow(
            starts_at=_WINDOW_START,
            ends_at=_WINDOW_END,
        ),
    )

    funnel = {metric.status: metric.count for metric in metrics.funnel}

    assert funnel == {
        ApplicationStatus.APPLIED: 2,
        ApplicationStatus.SCREENING: 2,
        ApplicationStatus.INTERVIEW: 1,
        ApplicationStatus.OFFER: 0,
        ApplicationStatus.HIRED: 1,
        ApplicationStatus.REJECTED: 1,
        ApplicationStatus.WITHDRAWN: 0,
    }

    transitions = {
        (metric.from_status, metric.to_status): metric.count
        for metric in metrics.stage_transitions
    }
    assert transitions[(None, ApplicationStatus.APPLIED)] == 2
    assert (
        transitions[
            (
                ApplicationStatus.APPLIED,
                ApplicationStatus.SCREENING,
            )
        ]
        == 2
    )
    assert (
        transitions[
            (
                ApplicationStatus.INTERVIEW,
                ApplicationStatus.HIRED,
            )
        ]
        == 1
    )

    sources = {metric.source: metric for metric in metrics.source_effectiveness}
    assert sources["employee_referral"].application_count == 1
    assert sources["employee_referral"].hired_count == 1
    assert sources["job_board"].application_count == 1
    assert sources["job_board"].hired_count == 0

    assert metrics.time_to_hire.hired_count == 1
    assert metrics.time_to_hire.average_hours == 96.0


@pytest.mark.asyncio
async def test_uses_window_for_lifecycle_and_source_metrics(
    session: AsyncSession,
) -> None:
    """Exclude applications and transitions outside the requested UTC window."""
    tenant_id = uuid4()
    await _seed_metrics_data(session, tenant_id=tenant_id)

    metrics = await get_recruiting_metrics(
        session,
        context=_context(tenant_id),
        window=MetricsWindow(
            starts_at=datetime(2026, 9, 4, tzinfo=UTC),
            ends_at=datetime(2026, 9, 7, tzinfo=UTC),
        ),
    )

    funnel = {metric.status: metric.count for metric in metrics.funnel}

    assert funnel[ApplicationStatus.APPLIED] == 0
    assert funnel[ApplicationStatus.SCREENING] == 1
    assert funnel[ApplicationStatus.HIRED] == 1
    assert funnel[ApplicationStatus.REJECTED] == 1

    sources = {metric.source: metric for metric in metrics.source_effectiveness}
    assert sources["employee_referral"].application_count == 0
    assert sources["employee_referral"].hired_count == 1
    assert sources["job_board"].application_count == 0
    assert sources["job_board"].hired_count == 0


@pytest.mark.asyncio
async def test_enforces_tenant_isolation(
    session: AsyncSession,
) -> None:
    """Never include lifecycle data belonging to another tenant."""
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    await _seed_metrics_data(session, tenant_id=tenant_a_id)
    await _seed_metrics_data(session, tenant_id=tenant_b_id)

    metrics = await get_recruiting_metrics(
        session,
        context=_context(tenant_a_id),
        window=MetricsWindow(
            starts_at=_WINDOW_START,
            ends_at=_WINDOW_END,
        ),
    )

    funnel = {metric.status: metric.count for metric in metrics.funnel}

    assert funnel[ApplicationStatus.APPLIED] == 2
    assert funnel[ApplicationStatus.HIRED] == 1
    assert metrics.time_to_hire.hired_count == 1
    assert len(metrics.source_effectiveness) == 2


@pytest.mark.asyncio
async def test_rejects_roles_without_analytics_access(
    session: AsyncSession,
) -> None:
    """Interviewers cannot query tenant-wide recruiting metrics."""
    tenant_id = uuid4()
    await _seed_metrics_data(session, tenant_id=tenant_id)

    with pytest.raises(RecruitingMetricsAccessDeniedError):
        await get_recruiting_metrics(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            window=MetricsWindow(
                starts_at=_WINDOW_START,
                ends_at=_WINDOW_END,
            ),
        )


@pytest.mark.asyncio
async def test_rejects_invalid_metric_windows(
    session: AsyncSession,
) -> None:
    """Reject naive, inverted, and unbounded reporting windows."""
    tenant_id = uuid4()
    context = _context(tenant_id)

    with pytest.raises(
        RecruitingMetricsValidationError,
        match="UTC offset",
    ):
        await get_recruiting_metrics(
            session,
            context=context,
            window=MetricsWindow(
                starts_at=datetime(2026, 9, 1),
                ends_at=datetime(2026, 9, 2, tzinfo=UTC),
            ),
        )

    with pytest.raises(
        RecruitingMetricsValidationError,
        match="start time",
    ):
        await get_recruiting_metrics(
            session,
            context=context,
            window=MetricsWindow(
                starts_at=_WINDOW_END,
                ends_at=_WINDOW_START,
            ),
        )

    with pytest.raises(
        RecruitingMetricsValidationError,
        match="366 days",
    ):
        await get_recruiting_metrics(
            session,
            context=context,
            window=MetricsWindow(
                starts_at=_WINDOW_START,
                ends_at=_WINDOW_START + timedelta(days=367),
            ),
        )


@pytest.mark.asyncio
async def test_metric_result_excludes_candidate_and_sensitive_data(
    session: AsyncSession,
) -> None:
    """Metrics expose aggregate counts only, never candidate-level data."""
    tenant_id = uuid4()
    await _seed_metrics_data(session, tenant_id=tenant_id)

    metrics = await get_recruiting_metrics(
        session,
        context=_context(tenant_id),
        window=MetricsWindow(
            starts_at=_WINDOW_START,
            ends_at=_WINDOW_END,
        ),
    )

    rendered = repr(metrics)

    for prohibited_value in (
        "candidate-",
        "@example.test",
        "Candidate 1",
        "internal_campaign_code",
        "seed",
    ):
        assert prohibited_value not in rendered

    for source in metrics.source_effectiveness:
        assert not hasattr(source, "candidate_id")
        assert not hasattr(source, "email")
        assert not hasattr(source, "phone")
