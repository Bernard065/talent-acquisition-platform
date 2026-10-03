"""Tenant identity-provider mapping lookups."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import Tenant


class Auth0OrganizationNotMappedError(LookupError):
    """Raised when a verified Auth0 Organization is not provisioned locally."""


async def resolve_auth0_organization_tenant_id(
    session: AsyncSession,
    *,
    organization_id: str,
) -> UUID:
    """Resolve a verified Auth0 Organization ID to its internal tenant ID."""
    tenant_id = await session.scalar(
        select(Tenant.id).where(
            Tenant.auth0_organization_id == organization_id,
        )
    )
    if tenant_id is None:
        raise Auth0OrganizationNotMappedError

    return tenant_id
