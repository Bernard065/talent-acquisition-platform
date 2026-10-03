"""PostgreSQL tests for tenant identity-provider mappings."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import Tenant


async def test_auth0_organization_id_must_be_unique_per_tenant(
    session: AsyncSession,
) -> None:
    """One Auth0 Organization cannot be mapped to multiple tenants."""
    session.add_all(
        [
            Tenant(
                name="First tenant",
                slug="first-tenant-auth0-mapping-test",
                auth0_organization_id="org_shared_for_test",
            ),
            Tenant(
                name="Second tenant",
                slug="second-tenant-auth0-mapping-test",
                auth0_organization_id="org_shared_for_test",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_multiple_tenants_may_have_no_auth0_organization(
    session: AsyncSession,
) -> None:
    """The mapping stays optional while tenants are being onboarded."""
    session.add_all(
        [
            Tenant(
                name="First unlinked tenant",
                slug="first-unlinked-auth0-mapping-test",
            ),
            Tenant(
                name="Second unlinked tenant",
                slug="second-unlinked-auth0-mapping-test",
            ),
        ]
    )

    await session.flush()
