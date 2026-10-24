"""Workspace-admin audit event search endpoints."""

from datetime import UTC, date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.audit_events import (
    AuditEventListResponse,
    AuditEventResponse,
)
from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import User

router = APIRouter(prefix="/audit-events", tags=["Audit events"])
CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    action: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    entity_type: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    actor: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    occurred_from: date | None = None,
    occurred_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> AuditEventListResponse:
    """Return the caller's tenant audit history with bounded filters."""
    response.headers["Cache-Control"] = "private, no-store"
    if Role.TENANT_ADMIN not in context.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace administrator permission is required to view the audit log.",
            headers={"Cache-Control": "private, no-store"},
        )

    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The start date must be on or before the end date.",
            headers={"Cache-Control": "private, no-store"},
        )

    filters = [AuditEvent.tenant_id == context.tenant_id]
    if action:
        filters.append(AuditEvent.action.ilike(f"%{action.strip()}%"))
    if entity_type:
        filters.append(AuditEvent.entity_type.ilike(f"%{entity_type.strip()}%"))
    if actor:
        actor_pattern = f"%{actor.strip()}%"
        filters.append(
            or_(
                User.display_name.ilike(actor_pattern),
                AuditEvent.actor_subject.ilike(actor_pattern),
            )
        )
    if occurred_from:
        filters.append(
            AuditEvent.occurred_at >= datetime.combine(occurred_from, time.min, UTC)
        )
    if occurred_to:
        filters.append(
            AuditEvent.occurred_at <= datetime.combine(occurred_to, time.max, UTC)
        )

    tenant_actor_join = and_(
        User.tenant_id == AuditEvent.tenant_id,
        User.external_subject == AuditEvent.actor_subject,
    )
    total = await session.scalar(
        select(func.count(AuditEvent.id))
        .outerjoin(User, tenant_actor_join)
        .where(*filters)
    )
    rows = await session.execute(
        select(AuditEvent, User.display_name)
        .outerjoin(User, tenant_actor_join)
        .where(*filters)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )

    return AuditEventListResponse(
        items=[
            AuditEventResponse(
                id=event.id,
                actor_display_name=display_name,
                actor_subject=event.actor_subject,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                request_id=event.request_id,
                occurred_at=event.occurred_at,
            )
            for event, display_name in rows.all()
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
