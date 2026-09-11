"""Private HTTP endpoint for recruiting analytics."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.recruiting_metrics import (
    FunnelMetricResponse,
    RecruitingMetricsResponse,
    SourceEffectivenessMetricResponse,
    StageTransitionMetricResponse,
    TimeToHireMetricResponse,
)
from app.core.authorization import TenantContext
from app.services.recruiting_metrics import (
    MetricsWindow,
    get_recruiting_metrics,
)

router = APIRouter(prefix="/analytics", tags=["Recruiting analytics"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]

_PRIVATE_NO_STORE = "private, no-store"


@router.get(
    "/recruiting-metrics",
    response_model=RecruitingMetricsResponse,
    summary="Get aggregate recruiting metrics",
)
async def get_recruiting_metrics_endpoint(
    response: Response,
    context: CallerContext,
    session: DatabaseSession,
    starts_at: Annotated[datetime, Query()],
    ends_at: Annotated[datetime, Query()],
) -> RecruitingMetricsResponse:
    """Return privacy-safe aggregate metrics for the caller's tenant."""
    metrics = await get_recruiting_metrics(
        session,
        context=context,
        window=MetricsWindow(
            starts_at=starts_at,
            ends_at=ends_at,
        ),
    )

    response.headers["Cache-Control"] = _PRIVATE_NO_STORE

    return RecruitingMetricsResponse(
        starts_at=metrics.window.starts_at,
        ends_at=metrics.window.ends_at,
        funnel=[
            FunnelMetricResponse(
                status=metric.status,
                count=metric.count,
            )
            for metric in metrics.funnel
        ],
        stage_transitions=[
            StageTransitionMetricResponse(
                from_status=metric.from_status,
                to_status=metric.to_status,
                count=metric.count,
            )
            for metric in metrics.stage_transitions
        ],
        source_effectiveness=[
            SourceEffectivenessMetricResponse(
                source=metric.source,
                application_count=metric.application_count,
                hired_count=metric.hired_count,
            )
            for metric in metrics.source_effectiveness
        ],
        time_to_hire=TimeToHireMetricResponse(
            hired_count=metrics.time_to_hire.hired_count,
            average_hours=metrics.time_to_hire.average_hours,
        ),
    )
