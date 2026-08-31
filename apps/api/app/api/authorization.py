"""FastAPI authorization dependencies for role-based access control."""

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_tenant_context
from app.core.authorization import Role, TenantContext

TENANT_CONTEXT_DEPENDENCY = Depends(get_tenant_context)


def require_any_role(*allowed_roles: Role):
    """Return a FastAPI dependency that requires at least one supplied role."""

    if not allowed_roles:
        raise ValueError("at least one role is required")

    async def authorize(
        context: TenantContext = TENANT_CONTEXT_DEPENDENCY,
    ) -> TenantContext:
        """Authorize the caller when they have at least one allowed role."""

        if context.roles.isdisjoint(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient role",
            )

        return context

    return authorize
