"""Tenant-owned employee records created from hired applications."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.employees.enums import EmployeeOffboardingReason, EmployeeStatus


class Employee(Base):
    """A workspace's internal employee record for a hired candidate."""

    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            name="uq_employees_tenant_application",
        ),
        UniqueConstraint(
            "tenant_id",
            "employee_number",
            name="uq_employees_tenant_employee_number",
        ),
        UniqueConstraint(
            "tenant_id",
            "work_email",
            name="uq_employees_tenant_work_email",
        ),
        UniqueConstraint("user_id", name="uq_employees_user_id"),
        Index(
            "ix_employees_tenant_status_created_at",
            "tenant_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employee_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manager_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(
            EmployeeStatus,
            name="employee_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=EmployeeStatus.PREBOARDING,
        server_default=EmployeeStatus.PREBOARDING.value,
    )
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    offboarding_reason: Mapped[EmployeeOffboardingReason | None] = mapped_column(
        Enum(
            EmployeeOffboardingReason,
            name="employee_offboarding_reason",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )
    offboarding_cycle_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True, index=True
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
