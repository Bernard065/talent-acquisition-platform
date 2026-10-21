"""Add planned employee offboarding details.

Revision ID: d8c1f4a9b702
Revises: f4b29c6d8a13
Create Date: 2026-10-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d8c1f4a9b702"
down_revision: str | Sequence[str] | None = "f4b29c6d8a13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


employee_offboarding_reason = postgresql.ENUM(
    "resignation",
    "retirement",
    "redundancy",
    "contract_end",
    "termination",
    "other",
    name="employee_offboarding_reason",
    create_type=False,
)


def upgrade() -> None:
    """Track an employee's planned final day and reason for leaving."""
    op.execute("ALTER TYPE employee_status ADD VALUE IF NOT EXISTS 'offboarding'")
    employee_offboarding_reason.create(op.get_bind(), checkfirst=True)
    op.add_column("employees", sa.Column("last_working_day", sa.Date(), nullable=True))
    op.add_column(
        "employees",
        sa.Column("offboarding_reason", employee_offboarding_reason, nullable=True),
    )
    op.create_check_constraint(
        "ck_employees_offboarding_details_required",
        "employees",
        "status::text <> 'offboarding' OR "
        "(last_working_day IS NOT NULL AND offboarding_reason IS NOT NULL)",
    )


def downgrade() -> None:
    """Remove planned offboarding fields and the status value."""
    op.drop_constraint(
        "ck_employees_offboarding_details_required",
        "employees",
        type_="check",
    )
    op.drop_column("employees", "offboarding_reason")
    op.drop_column("employees", "last_working_day")
    employee_offboarding_reason.drop(op.get_bind(), checkfirst=True)
    op.execute("UPDATE employees SET status = 'active' WHERE status = 'offboarding'")
    op.execute("ALTER TABLE employees ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE employee_status RENAME TO employee_status_old")
    op.execute(
        "CREATE TYPE employee_status AS ENUM ('preboarding', 'active', 'inactive')"
    )
    op.execute(
        "ALTER TABLE employees ALTER COLUMN status TYPE employee_status "
        "USING status::text::employee_status"
    )
    op.execute("ALTER TABLE employees ALTER COLUMN status SET DEFAULT 'preboarding'")
    op.execute("DROP TYPE employee_status_old")
