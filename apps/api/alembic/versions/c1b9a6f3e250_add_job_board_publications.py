"""add provider-neutral job-board publication state

Revision ID: c1b9a6f3e250
Revises: 8e5b89152b00
Create Date: 2026-09-29

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1b9a6f3e250"
down_revision: str | Sequence[str] | None = "8e5b89152b00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist tenant-scoped external publication state and sync requests."""
    status_type = postgresql.ENUM(
        "publish_requested",
        "published",
        "unpublish_requested",
        "unpublished",
        "failed",
        name="job_board_publication_status",
        create_type=False,
    )
    status_type.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_job_postings_tenant_id_id",
        "job_postings",
        ["tenant_id", "id"],
    )
    op.create_table(
        "job_board_publications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("job_posting_id", sa.UUID(), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            status_type,
            server_default="publish_requested",
            nullable=False,
        ),
        sa.Column("external_posting_id", sa.String(length=255), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider_key ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name=op.f("ck_job_board_publications_provider_key_format"),
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR "
            "last_error_code ~ '^[a-z0-9][a-z0-9_.-]{0,99}$'",
            name=op.f("ck_job_board_publications_safe_error_code"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_posting_id"],
            ["job_postings.tenant_id", "job_postings.id"],
            name="fk_job_board_publications_tenant_posting",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_board_publications")),
        sa.UniqueConstraint(
            "tenant_id",
            "job_posting_id",
            "provider_key",
            name="uq_job_board_publications_tenant_posting_provider",
        ),
    )
    op.create_index(
        "ix_job_board_publications_tenant_status_updated_at",
        "job_board_publications",
        ["tenant_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_board_publications_provider_status_updated_at",
        "job_board_publications",
        ["provider_key", "status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove external publication state and its PostgreSQL enum type."""
    op.drop_index(
        "ix_job_board_publications_provider_status_updated_at",
        table_name="job_board_publications",
    )
    op.drop_index(
        "ix_job_board_publications_tenant_status_updated_at",
        table_name="job_board_publications",
    )
    op.drop_table("job_board_publications")
    postgresql.ENUM(name="job_board_publication_status").drop(
        op.get_bind(),
        checkfirst=True,
    )
    op.drop_constraint(
        "uq_job_postings_tenant_id_id",
        "job_postings",
        type_="unique",
    )
