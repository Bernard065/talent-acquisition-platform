"""Workspace administration and Supabase invitation acceptance endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant, User, UserRoleAssignment, WorkspaceInvitation

router = APIRouter(tags=["workspace invitations"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


class CreateInvitation(BaseModel):
    """Payload for creating a workspace invitation."""

    email: EmailStr
    role: Role = Role.RECRUITER


class InvitationView(BaseModel):
    """Representation of a workspace invitation returned by the API."""

    id: UUID
    email: str
    role: Role
    status: str
    expires_at: datetime
    created_at: datetime


class AcceptInvitation(BaseModel):
    """Payload used to accept a workspace invitation with a token and password."""

    token_hash: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8, max_length=128)


def _settings(request: Request) -> Settings:
    """Resolve the settings needed for Supabase invitation operations."""

    settings: Settings = request.app.state.settings
    if settings.supabase_url is None or settings.supabase_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workspace invitations are not configured.",
        )
    return settings


def _require_admin(context: TenantContext) -> None:
    """Ensure the request is made by a tenant administrator."""

    if Role.TENANT_ADMIN not in context.roles:
        raise HTTPException(status_code=403, detail="Insufficient permission.")


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a JSON object or an empty object for a non-object response value."""

    return value if isinstance(value, dict) else {}


def _admin_headers(settings: Settings) -> dict[str, str]:
    """Build the admin authorization headers for Supabase requests."""

    key = settings.supabase_secret_key.get_secret_value()  # type: ignore[union-attr]
    return {
        "apikey": key,
        "Authorization": "******",
        "Content-Type": "application/json",
    }


async def _supabase_request(
    settings: Settings,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Invoke a Supabase Auth endpoint and normalize HTTP errors."""

    base = str(settings.supabase_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(
                method,
                f"{base}/auth/v1/{path}",
                headers=headers or _admin_headers(settings),
                json=json,
                params=params,
            )
        if response.is_error:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            error_code = (
                str(error_payload.get("code", "unknown"))
                if isinstance(error_payload, dict)
                else "unknown"
            )
            error_message = (
                error_payload.get("msg") or error_payload.get("message")
                if isinstance(error_payload, dict)
                else None
            )
            safe_message = (
                " ".join(str(error_message).split())[:160]
                if error_message
                else "No provider message was returned."
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Supabase rejected the authentication request "
                    f"(HTTP {response.status_code}; code {error_code}): {safe_message}"
                ),
            )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth is unavailable.",
        ) from exc


@router.post("/team/invitations", response_model=InvitationView, status_code=201)
async def create_invitation(
    body: CreateInvitation,
    request: Request,
    session: SessionDep,
    context: ContextDep,
) -> WorkspaceInvitation:
    """Create and send a pending workspace invitation for a tenant member."""

    _require_admin(context)
    settings = _settings(request)
    if body.role == Role.TENANT_ADMIN:
        raise HTTPException(
            status_code=422,
            detail="Tenant administrator access is provisioned separately.",
        )
    email = str(body.email).strip().casefold()
    already_member = await session.scalar(select(User.id).where(User.email == email))
    pending = await session.scalar(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.email == email, WorkspaceInvitation.status == "pending"
        )
    )
    if already_member or (pending is not None and pending.expires_at > datetime.now(UTC)):
        raise HTTPException(
            status_code=409,
            detail="This email already belongs to a member or has a pending invitation.",
        )
    if pending is not None:
        pending.status = "expired"
        await session.flush()
    tenant = await session.get(Tenant, context.tenant_id)
    if tenant is None or not tenant.identity_provider_organization_id:
        raise HTTPException(
            status_code=409,
            detail="Workspace identity is not configured.",
        )

    invitation = WorkspaceInvitation(
        tenant_id=context.tenant_id,
        email=email,
        role=body.role,
        invited_by_subject=context.subject,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(invitation)
    await session.flush()
    redirect = f"{str(settings.web_app_base_url).rstrip('/')}/accept-invitation"
    invited = await _supabase_request(
        settings,
        "POST",
        "invite",
        json={
            "email": email,
            "data": {"workspace_name": tenant.name, "invited_role": body.role.value},
        },
        params={"redirect_to": redirect},
    )
    invited_payload = _as_dict(invited)
    user = _as_dict(invited_payload.get("user")) or invited_payload
    user_id = user.get("id")
    if not user_id:
        await session.rollback()
        raise HTTPException(
            status_code=502,
            detail="Supabase did not return an invited user.",
        )
    await _supabase_request(
        settings,
        "PUT",
        f"admin/users/{user_id}",
        json={
            "app_metadata": {
                "organization_id": tenant.identity_provider_organization_id,
                "roles": [body.role.value],
            }
        },
    )
    await session.commit()
    await session.refresh(invitation)
    return invitation


@router.get("/team/invitations", response_model=list[InvitationView])
async def list_invitations(session: SessionDep, context: ContextDep) -> list[WorkspaceInvitation]:
    """List tenant invitations and mark expired ones as expired."""

    _require_admin(context)
    rows = await session.scalars(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.tenant_id == context.tenant_id)
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    invitations = list(rows)
    now = datetime.now(UTC)
    changed = False
    for invitation in invitations:
        if invitation.status == "pending" and invitation.expires_at <= now:
            invitation.status = "expired"
            changed = True
    if changed:
        await session.commit()
    return invitations


@router.delete("/team/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: UUID, session: SessionDep, context: ContextDep) -> None:
    """Revoke a pending invitation for the current tenant."""

    _require_admin(context)
    invitation = await session.scalar(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.tenant_id == context.tenant_id,
            WorkspaceInvitation.status == "pending",
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Pending invitation not found.")
    invitation.status = "revoked"
    await session.commit()


@router.post("/workspace-invitations/accept", status_code=204)
async def accept_invitation(body: AcceptInvitation, request: Request, session: SessionDep) -> None:
    """Accept a pending invitation by verifying the Supabase token."""

    settings = _settings(request)
    publishable_key = settings.supabase_publishable_key
    if publishable_key is None:
        raise HTTPException(
            status_code=503,
            detail="Workspace invitations are not configured.",
        )
    key = publishable_key.get_secret_value()
    payload = await _supabase_request(
        settings,
        "POST",
        "verify",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"token_hash": body.token_hash, "type": "invite"},
    )
    payload_object = _as_dict(payload)
    auth_user = _as_dict(payload_object.get("user"))
    email = str(auth_user.get("email", "")).casefold()
    subject = str(auth_user.get("id", ""))
    access_token = payload_object.get("access_token")
    if not email or not subject or not access_token:
        raise HTTPException(
            status_code=400,
            detail="The invitation link is invalid or expired.",
        )
    invitation = await session.scalar(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.email == email,
            WorkspaceInvitation.status == "pending",
            WorkspaceInvitation.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if invitation is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This invitation is no longer valid. Ask your workspace administrator "
                "for a new one."
            ),
        )
    await _supabase_request(
        settings,
        "PUT",
        "user",
        headers={
            "apikey": key,
            "Authorization": "******",
            "Content-Type": "application/json",
        },
        json={"password": body.password},
    )
    tenant = await session.get(Tenant, invitation.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=400,
            detail="The invited workspace no longer exists.",
        )
    existing = await session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.email == email)
    )
    if existing is None:
        member = User(
            tenant_id=tenant.id,
            external_subject=subject,
            email=email,
            display_name=email.split("@")[0],
        )
        session.add(member)
        await session.flush()
        session.add(UserRoleAssignment(user_id=member.id, role=invitation.role))
    invitation.status = "accepted"
    invitation.accepted_at = datetime.now(UTC)
    await session.commit()
