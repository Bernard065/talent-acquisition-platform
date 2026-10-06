"""Create the first workspace and invite its initial tenant administrator.

Run from apps/api with: uv run python -m app.scripts.bootstrap_workspace \
  --name "Acme Hiring" --slug acme-hiring --admin-email admin@example.com
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.api.v1.workspace_invitations import _supabase_request
from app.core.authorization import Role
from app.core.config import get_settings
from app.db.models.identity import Tenant, WorkspaceInvitation
from app.db.session import Database


async def bootstrap(name: str, slug: str, email: str) -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required.")
    if settings.supabase_url is None or settings.supabase_secret_key is None:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required.")
    email = email.strip().casefold()
    database = Database(str(settings.database_url))
    try:
        async with database.session_factory() as session:
            existing = await session.scalar(select(Tenant.id).where(Tenant.slug == slug))
            if existing:
                raise RuntimeError(f"Workspace slug '{slug}' already exists.")
            organization_id = str(uuid4())
            tenant = Tenant(name=name, slug=slug, identity_provider_organization_id=organization_id)
            session.add(tenant)
            await session.flush()
            invitation = WorkspaceInvitation(
                tenant_id=tenant.id,
                email=email,
                role=Role.TENANT_ADMIN,
                invited_by_subject="bootstrap",
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(invitation)
            await session.flush()
            redirect = f"{str(settings.web_app_base_url).rstrip('/')}/accept-invitation"
            try:
                result = await _supabase_request(
                    settings,
                    "POST",
                    "invite",
                    json={
                        "email": email,
                        "data": {
                            "workspace_name": name,
                            "invited_role": Role.TENANT_ADMIN.value,
                        },
                    },
                    params={"redirect_to": redirect},
                )
                auth_user = result.get("user") if isinstance(result.get("user"), dict) else result
                user_id = auth_user.get("id")
                if not user_id:
                    raise RuntimeError("Supabase did not return an invited user.")
                await _supabase_request(
                    settings,
                    "PUT",
                    f"admin/users/{user_id}",
                    json={
                        "app_metadata": {
                            "organization_id": organization_id,
                            "roles": [Role.TENANT_ADMIN.value],
                        }
                    },
                )
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            print(f"Created workspace '{name}' ({slug}); invitation sent to {email}.")
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--admin-email", required=True)
    args = parser.parse_args()
    asyncio.run(bootstrap(args.name, args.slug, args.admin_email))


if __name__ == "__main__":
    main()
