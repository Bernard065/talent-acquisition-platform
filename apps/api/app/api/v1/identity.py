"""Protected endpoints for retrieving the authenticated user's identity."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_tenant_context
from app.core.authorization import Role, TenantContext

TENANT_CONTEXT_DEPENDENCY = Depends(get_tenant_context)

router = APIRouter(prefix="/identity", tags=["identity"])


class CurrentIdentityResponse(BaseModel):
    """Response containing the authenticated user's verified identity."""

    tenant_id: UUID
    subject: str
    roles: list[Role]


@router.get("/me", response_model=CurrentIdentityResponse)
async def get_current_identity(
    context: TenantContext = TENANT_CONTEXT_DEPENDENCY,
) -> CurrentIdentityResponse:
    """Return the identity and roles of the authenticated caller."""

    return CurrentIdentityResponse(
        tenant_id=context.tenant_id,
        subject=context.subject,
        roles=sorted(context.roles),
    )
