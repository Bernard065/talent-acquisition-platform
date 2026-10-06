"""Tenant identity-provider mapping lookups."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import Tenant


class IdentityProviderOrganizationNotMappedError(LookupError):
    """Raised when a verified external organization is not provisioned locally."""


async def resolve_identity_provider_organization_tenant_id(
    session: AsyncSession,
    *,
    organization_id: str,
) -> UUID:
    """Resolve a verified identity-provider organization to its tenant ID."""
    tenant_id = await session.scalar(
        select(Tenant.id).where(
            Tenant.identity_provider_organization_id == organization_id,
        )
    )
    if tenant_id is None:
        raise IdentityProviderOrganizationNotMappedError

    return tenant_id
