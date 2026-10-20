"""Add draft and publication state to onboarding template versions.

Revision ID: f4b29c6d8a13
Revises: c8f1b5a2d904
Create Date: 2026-10-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b29c6d8a13"
down_revision: str | Sequence[str] | None = "c8f1b5a2d904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Mark existing versions published and add constrained draft metadata."""
    op.add_column(
        "onboarding_templates",
        sa.Column(
            "publication_status",
            sa.String(length=20),
            server_default="published",
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_templates",
        sa.Column(
            "draft_revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_templates_publication_status",
        "onboarding_templates",
        "publication_status IN ('draft', 'published')",
    )
    op.create_check_constraint(
        "ck_onboarding_templates_draft_revision_positive",
        "onboarding_templates",
        "draft_revision >= 1",
    )
    op.create_check_constraint(
        "ck_onboarding_templates_active_must_be_published",
        "onboarding_templates",
        "is_active IS FALSE OR publication_status = 'published'",
    )
    op.create_index(
        "uq_onboarding_templates_tenant_name_draft",
        "onboarding_templates",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("publication_status = 'draft'"),
    )


def downgrade() -> None:
    """Remove draft metadata and its uniqueness invariant."""
    op.drop_index(
        "uq_onboarding_templates_tenant_name_draft",
        table_name="onboarding_templates",
    )
    op.drop_constraint(
        "ck_onboarding_templates_draft_revision_positive",
        "onboarding_templates",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_templates_active_must_be_published",
        "onboarding_templates",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_templates_publication_status",
        "onboarding_templates",
        type_="check",
    )
    op.drop_column("onboarding_templates", "draft_revision")
    op.drop_column("onboarding_templates", "publication_status")
