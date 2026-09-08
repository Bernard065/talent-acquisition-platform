"""Add interview session lifecycle history.

Revision ID: f8b6443d1c61
Revises: 5404bc192de4
Create Date: 2026-09-08 21:21:13.600666

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b6443d1c61"
down_revision: str | Sequence[str] | None = "5404bc192de4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    interview_session_status = postgresql.ENUM(
        "scheduled",
        "completed",
        "cancelled",
        name="interview_session_status",
        create_type=False,
    )

    op.create_table(
        "interview_session_lifecycle_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("interview_session_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "rescheduled",
                "completed",
                "cancelled",
                name="interview_lifecycle_event_type",
            ),
            nullable=False,
        ),
        sa.Column("from_status", interview_session_status, nullable=False),
        sa.Column("to_status", interview_session_status, nullable=False),
        sa.Column("previous_scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancellation_reason",
            sa.Enum(
                "candidate_withdrew",
                "candidate_unavailable",
                "interviewer_unavailable",
                "requisition_closed",
                "scheduling_conflict",
                "other",
                name="interview_cancellation_reason",
            ),
            nullable=True,
        ),
        sa.Column("occurred_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(event_type != 'cancelled') OR cancellation_reason IS NOT NULL",
            name=op.f(
                "ck_interview_session_lifecycle_history_"
                "ck_interview_lifecycle_cancellation_reason_required"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["interview_session_id"],
            ["interview_sessions.id"],
            name=op.f(
                "fk_interview_session_lifecycle_history_interview_session_id_"
                "interview_sessions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(
                "fk_interview_session_lifecycle_history_tenant_id_tenants"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_session_lifecycle_history")),
    )
    op.create_index(
        "ix_interview_lifecycle_tenant_session_occurred_at",
        "interview_session_lifecycle_history",
        ["tenant_id", "interview_session_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_interview_session_lifecycle_history_interview_session_id"),
        "interview_session_lifecycle_history",
        ["interview_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_interview_session_lifecycle_history_tenant_id"),
        "interview_session_lifecycle_history",
        ["tenant_id"],
        unique=False,
    )
    op.add_column(
        "interview_sessions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("cancelled_by_subject", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "cancellation_reason",
            sa.Enum(
                "candidate_withdrew",
                "candidate_unavailable",
                "interviewer_unavailable",
                "requisition_closed",
                "scheduling_conflict",
                "other",
                name="interview_cancellation_reason",
            ),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_interview_sessions_ck_interview_sessions_cancellation_metadata_required"),
        "interview_sessions",
        "(status != 'cancelled') OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_interview_sessions_ck_interview_sessions_completed_at_required"),
        "interview_sessions",
        "(status != 'completed') OR completed_at IS NOT NULL",
    )
    op.execute(
        """
        CREATE FUNCTION prevent_interview_lifecycle_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Interview lifecycle history is immutable.'
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_interview_lifecycle_history_immutable
        BEFORE UPDATE OR DELETE ON interview_session_lifecycle_history
        FOR EACH ROW
        EXECUTE FUNCTION prevent_interview_lifecycle_history_mutation();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_interview_lifecycle_history_immutable "
        "ON interview_session_lifecycle_history"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_interview_lifecycle_history_mutation()"
    )

    op.drop_constraint(
        op.f("ck_interview_sessions_ck_interview_sessions_completed_at_required"),
        "interview_sessions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_interview_sessions_ck_interview_sessions_cancellation_metadata_required"),
        "interview_sessions",
        type_="check",
    )
    op.drop_column("interview_sessions", "cancellation_reason")
    op.drop_column("interview_sessions", "cancelled_by_subject")
    op.drop_column("interview_sessions", "cancelled_at")
    op.drop_column("interview_sessions", "completed_at")
    op.drop_index(
        op.f("ix_interview_session_lifecycle_history_tenant_id"),
        table_name="interview_session_lifecycle_history",
    )
    op.drop_index(
        op.f("ix_interview_session_lifecycle_history_interview_session_id"),
        table_name="interview_session_lifecycle_history",
    )
    op.drop_index(
        "ix_interview_lifecycle_tenant_session_occurred_at",
        table_name="interview_session_lifecycle_history",
    )
    op.drop_table("interview_session_lifecycle_history")
