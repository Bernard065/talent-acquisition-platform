"""Workspace team member read endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.team import TeamMemberListResponse, TeamMemberResponse
from app.core.authorization import Role, TenantContext
from app.db.models.identity import User, UserRoleAssignment
from app.services.candidate_errors import CandidateAccessDeniedError

_TEAM_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)

router = APIRouter(prefix="/team", tags=["Team"])
CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/members", response_model=TeamMemberListResponse)
async def list_team_members(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> TeamMemberListResponse:
    """List active recruiting roles in the caller's workspace."""
    if context.roles.isdisjoint(_TEAM_READ_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to view recruiting team members."
        )

    members = list(
        await session.scalars(
            select(User)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .where(
                User.tenant_id == context.tenant_id,
                UserRoleAssignment.role.in_(_TEAM_READ_ROLES),
            )
            .distinct()
            .order_by(User.display_name, User.id)
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return TeamMemberListResponse(
        items=[
            TeamMemberResponse(
                id=member.id,
                display_name=member.display_name,
                email=member.email,
            )
            for member in members
        ]
    )
