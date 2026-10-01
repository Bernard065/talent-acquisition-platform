"""Tenant-scoped, privacy-safe recruiting analytics read service."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import Function, count

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.candidate import Candidate
from app.domains.candidates.enums import ApplicationStatus
from app.services.recruiting_metrics_errors import (
    RecruitingMetricsAccessDeniedError,
    RecruitingMetricsValidationError,
)

_ANALYTICS_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
        Role.ANALYST,
    }
)

_MAX_WINDOW = timedelta(days=366)


@dataclass(frozen=True, slots=True)
class MetricsWindow:
    """Inclusive UTC start and exclusive UTC end for aggregated metrics."""

    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class FunnelMetric:
    """Count of application transitions into one pipeline stage."""

    status: ApplicationStatus
    count: int


@dataclass(frozen=True, slots=True)
class StageTransitionMetric:
    """Count of one typed application-stage transition."""

    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    count: int


@dataclass(frozen=True, slots=True)
class SourceEffectivenessMetric:
    """Aggregated application and hire counts for one candidate source."""

    source: str
    application_count: int
    hired_count: int


@dataclass(frozen=True, slots=True)
class TimeToHireMetric:
    """Aggregate duration from application to hired stage."""

    hired_count: int
    average_hours: float | None


@dataclass(frozen=True, slots=True)
class RecruitingMetrics:
    """Privacy-safe aggregate recruiting metrics for one tenant and window."""

    window: MetricsWindow
    funnel: tuple[FunnelMetric, ...]
    stage_transitions: tuple[StageTransitionMetric, ...]
    source_effectiveness: tuple[SourceEffectivenessMetric, ...]
    time_to_hire: TimeToHireMetric


def _require_analytics_role(context: TenantContext) -> None:
    """Allow only approved recruiting and reporting roles."""
    if not context.roles.intersection(_ANALYTICS_ROLES):
        raise RecruitingMetricsAccessDeniedError(
            "Caller lacks recruiting analytics permission."
        )


def _validate_window(window: MetricsWindow) -> None:
    """Reject unbounded, naive, inverted, and overly expensive queries."""
    if window.starts_at.tzinfo is None or window.ends_at.tzinfo is None:
        raise RecruitingMetricsValidationError(
            "Analytics timestamps must include a UTC offset."
        )

    starts_at = window.starts_at.astimezone(UTC)
    ends_at = window.ends_at.astimezone(UTC)

    if starts_at >= ends_at:
        raise RecruitingMetricsValidationError(
            "Analytics start time must be before end time."
        )

    if ends_at - starts_at > _MAX_WINDOW:
        raise RecruitingMetricsValidationError(
            "Analytics date range cannot exceed 366 days."
        )


def _as_utc(window: MetricsWindow) -> MetricsWindow:
    """Normalize an already-valid window to UTC."""
    return MetricsWindow(
        starts_at=window.starts_at.astimezone(UTC),
        ends_at=window.ends_at.astimezone(UTC),
    )


async def get_recruiting_metrics(
    session: AsyncSession,
    *,
    context: TenantContext,
    window: MetricsWindow,
) -> RecruitingMetrics:
    """
    Return aggregate metrics without candidate, feedback, or offer-sensitive data.

    Metrics come from typed lifecycle tables rather than audit-event JSON.
    The result never includes candidate identifiers, names, contact details,
    feedback, document data, compensation, or free-text decision rationale.
    """
    _require_analytics_role(context)
    _validate_window(window)
    utc_window = _as_utc(window)

    history_scope = (
        ApplicationStageHistory.tenant_id == context.tenant_id,
        ApplicationStageHistory.transitioned_at >= utc_window.starts_at,
        ApplicationStageHistory.transitioned_at < utc_window.ends_at,
    )

    funnel_rows = (
        await session.execute(
            select(
                ApplicationStageHistory.to_status,
                count(ApplicationStageHistory.id),
            )
            .where(*history_scope)
            .group_by(ApplicationStageHistory.to_status)
        )
    ).all()
    funnel_counts = {status: int(count) for status, count in funnel_rows}

    funnel = tuple(
        FunnelMetric(
            status=status,
            count=funnel_counts.get(status, 0),
        )
        for status in ApplicationStatus
    )

    transition_rows = (
        await session.execute(
            select(
                ApplicationStageHistory.from_status,
                ApplicationStageHistory.to_status,
                count(ApplicationStageHistory.id),
            )
            .where(*history_scope)
            .group_by(
                ApplicationStageHistory.from_status,
                ApplicationStageHistory.to_status,
            )
            .order_by(
                ApplicationStageHistory.from_status,
                ApplicationStageHistory.to_status,
            )
        )
    ).all()
    stage_transitions = tuple(
        StageTransitionMetric(
            from_status=from_status,
            to_status=to_status,
            count=int(count),
        )
        for from_status, to_status, count in transition_rows
    )

    application_source_rows = (
        await session.execute(
            select(
                Candidate.source,
                count(Application.id),
            )
            .join(
                Candidate,
                Candidate.id == Application.candidate_id,
            )
            .where(
                Application.tenant_id == context.tenant_id,
                Candidate.tenant_id == context.tenant_id,
                Application.applied_at >= utc_window.starts_at,
                Application.applied_at < utc_window.ends_at,
            )
            .group_by(Candidate.source)
        )
    ).all()
    application_counts_by_source = {
        source: int(count)
        for source, count in application_source_rows
    }

    hired_source_rows = (
        await session.execute(
            select(
                Candidate.source,
                count(ApplicationStageHistory.id),
            )
            .join(
                Application,
                Application.id == ApplicationStageHistory.application_id,
            )
            .join(
                Candidate,
                Candidate.id == Application.candidate_id,
            )
            .where(
                *history_scope,
                ApplicationStageHistory.to_status == ApplicationStatus.HIRED,
                Application.tenant_id == context.tenant_id,
                Candidate.tenant_id == context.tenant_id,
            )
            .group_by(Candidate.source)
        )
    ).all()
    hired_counts_by_source = {
        source: int(count)
        for source, count in hired_source_rows
    }

    all_source_rows = (
        await session.execute(
            select(Candidate.source)
            .join(
                Application,
                Application.candidate_id == Candidate.id,
            )
            .where(
                Application.tenant_id == context.tenant_id,
                Candidate.tenant_id == context.tenant_id,
            )
            .group_by(Candidate.source)
        )
    ).all()

    sources = sorted(
        {source for (source,) in all_source_rows}
        | set(application_counts_by_source)
        | set(hired_counts_by_source)
    )
    source_effectiveness = tuple(
        SourceEffectivenessMetric(
            source=source,
            application_count=application_counts_by_source.get(source, 0),
            hired_count=hired_counts_by_source.get(source, 0),
        )
        for source in sources
    )

    time_to_hire_row: tuple[int, float | None] = (
            await session.execute(
                select(
                    count(ApplicationStageHistory.id),
                    Function(
                        "avg",
                        extract(
                            "epoch",
                            ApplicationStageHistory.transitioned_at
                            - Application.applied_at,
                        ),
                    ),
                )
                .join(
                    Application,
                    Application.id == ApplicationStageHistory.application_id,
                )
                .where(
                    *history_scope,
                    ApplicationStageHistory.to_status == ApplicationStatus.HIRED,
                    Application.tenant_id == context.tenant_id,
                    ApplicationStageHistory.transitioned_at
                    >= Application.applied_at,
                )
            )
        ).tuples().one()

    hired_count = int(time_to_hire_row[0] or 0)
    average_seconds = time_to_hire_row[1]
    average_hours = (
        round(float(average_seconds) / 3600, 2)
        if average_seconds is not None
        else None
    )

    return RecruitingMetrics(
        window=utc_window,
        funnel=funnel,
        stage_transitions=stage_transitions,
        source_effectiveness=source_effectiveness,
        time_to_hire=TimeToHireMetric(
            hired_count=hired_count,
            average_hours=average_hours,
        ),
    )
