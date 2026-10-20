"""Enforce one active version per onboarding template name.

Revision ID: c8f1b5a2d904
Revises: b7c41e92a630
Create Date: 2026-10-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8f1b5a2d904"
down_revision: str | Sequence[str] | None = "b7c41e92a630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep only the newest active version before enforcing the invariant."""
    op.execute(
        sa.text(
            """
            WITH ranked_templates AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY tenant_id, name
                        ORDER BY version DESC, created_at DESC, id DESC
                    ) AS version_rank
                FROM onboarding_templates
                WHERE is_active IS TRUE
            )
            UPDATE onboarding_templates AS template
            SET is_active = FALSE
            FROM ranked_templates AS ranked
            WHERE template.id = ranked.id
              AND ranked.version_rank > 1
            """
        )
    )
    op.create_index(
        "uq_onboarding_templates_tenant_name_active",
        "onboarding_templates",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    """Remove the active-version uniqueness constraint."""
    op.drop_index(
        "uq_onboarding_templates_tenant_name_active",
        table_name="onboarding_templates",
    )
