"""Workspace offboarding checklist definitions and employee task snapshots."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.employees.enums import EmployeeOffboardingTaskStatus


class EmployeeOffboardingTemplateTask(Base):
    """A workspace task definition copied into each new offboarding plan."""

    __tablename__ = "employee_offboarding_template_tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position",
            name="uq_employee_offboarding_template_tasks_tenant_position",
        ),
        CheckConstraint("position >= 1", name="ck_offboarding_template_task_position"),
        CheckConstraint(
            "due_days_before_last_working_day BETWEEN 0 AND 365",
            name="ck_offboarding_template_task_due_offset",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_days_before_last_working_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )


class EmployeeOffboardingTask(Base):
    """A versioned task snapshot for one employee offboarding cycle."""

    __tablename__ = "employee_offboarding_tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "offboarding_cycle_id",
            "position",
            name="uq_employee_offboarding_tasks_cycle_position",
        ),
        CheckConstraint("position >= 1", name="ck_employee_offboarding_task_position"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'blocked')",
            name="ck_employee_offboarding_task_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offboarding_cycle_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    template_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("employee_offboarding_template_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[EmployeeOffboardingTaskStatus] = mapped_column(
        Enum(
            EmployeeOffboardingTaskStatus,
            name="employee_offboarding_task_status",
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=EmployeeOffboardingTaskStatus.PENDING,
        server_default=EmployeeOffboardingTaskStatus.PENDING.value,
    )
    completion_notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_subject: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}
