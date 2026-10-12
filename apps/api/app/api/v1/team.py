"""Workspace team member read endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.team import (
    InterviewerListResponse,
    InterviewerResponse,
    TeamMemberListResponse,
    TeamMemberResponse,
)
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


@router.get("/workspace-members", response_model=TeamMemberListResponse)
async def list_workspace_members(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> TeamMemberListResponse:
    """List all existing workspace members for administrator role management."""
    if Role.TENANT_ADMIN not in context.roles:
        raise CandidateAccessDeniedError(
            "Only workspace admins can view the workspace member roster."
        )

    members = list(
        await session.scalars(
            select(User)
            .where(User.tenant_id == context.tenant_id)
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


@router.get("/interviewers", response_model=InterviewerListResponse)
async def list_team_interviewers(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewerListResponse:
    """List workspace users with the interviewer role for interview scheduling."""
    if context.roles.isdisjoint(_TEAM_READ_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to view workspace interviewers."
        )

    interviewers = list(
        await session.scalars(
            select(User)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .where(
                User.tenant_id == context.tenant_id,
                UserRoleAssignment.role == Role.INTERVIEWER,
            )
            .distinct()
            .order_by(User.display_name, User.id)
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return InterviewerListResponse(
        items=[
            InterviewerResponse(
                id=interviewer.id,
                display_name=interviewer.display_name,
                email=interviewer.email,
            )
            for interviewer in interviewers
        ]
    )
