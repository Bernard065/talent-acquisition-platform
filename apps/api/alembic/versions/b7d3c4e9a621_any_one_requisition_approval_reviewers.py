"""support any-one requisition approval reviewers

Revision ID: b7d3c4e9a621
Revises: 2f4a6c8d1e30
Create Date: 2026-10-09

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7d3c4e9a621"
down_revision: str | Sequence[str] | None = "2f4a6c8d1e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow multiple alternative reviewers at the same approval step."""
    op.execute(
        "CREATE TYPE requisition_approval_decision_status AS ENUM "
        "('pending', 'approved', 'rejected', 'not_required')"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status TYPE requisition_approval_decision_status "
        "USING status::text::requisition_approval_decision_status"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status SET DEFAULT 'pending'"
    )
    op.drop_constraint(
        "uq_requisition_approval_decisions_requisition_approval_id",
        "requisition_approval_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_requisition_approval_decisions_reviewer",
        "requisition_approval_decisions",
        ["requisition_approval_id", "step_position", "approver_user_id"],
    )


def downgrade() -> None:
    """Restore the sequential-assignment schema."""
    op.drop_constraint(
        "uq_requisition_approval_decisions_reviewer",
        "requisition_approval_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_requisition_approval_decisions_requisition_approval_id",
        "requisition_approval_decisions",
        ["requisition_approval_id", "step_position"],
    )
    op.execute(
        "UPDATE requisition_approval_decisions "
        "SET status = 'pending' WHERE status = 'not_required'"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status TYPE approval_decision_status "
        "USING status::text::approval_decision_status"
    )
    op.execute(
        "ALTER TABLE requisition_approval_decisions "
        "ALTER COLUMN status SET DEFAULT 'pending'"
    )
    op.execute("DROP TYPE requisition_approval_decision_status")
