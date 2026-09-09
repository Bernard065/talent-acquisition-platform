"""Tenant-scoped onboarding templates, instances, tasks, and history."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.authorization import Role
from app.db.base import Base
from app.domains.onboarding.enums import (
    OnboardingInstanceEventType,
    OnboardingInstanceStatus,
    OnboardingTaskEventType,
    OnboardingTaskStatus,
)


class OnboardingTemplate(Base):
    """A tenant-owned, versioned definition used to create onboarding tasks."""

    __tablename__ = "onboarding_templates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            "version",
            name="uq_onboarding_templates_tenant_name_version",
        ),
        Index(
            "ix_onboarding_templates_tenant_active",
            "tenant_id",
            "is_active",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class OnboardingTemplateTask(Base):
    """An ordered task definition belonging to one template version."""

    __tablename__ = "onboarding_template_tasks"
    __table_args__ = (
        CheckConstraint(
            "position >= 1",
            name="ck_onboarding_template_tasks_position_positive",
        ),
        CheckConstraint(
            "due_offset_days IS NULL OR due_offset_days >= 0",
            name="ck_onboarding_template_tasks_due_offset_non_negative",
        ),
        UniqueConstraint(
            "onboarding_template_id",
            "position",
            name="uq_onboarding_template_tasks_template_position",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    onboarding_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_offset_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    default_assignee_role: Mapped[Role | None] = mapped_column(
        Enum(
            Role,
            name="user_role",
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class OnboardingInstance(Base):
    """Onboarding work created for one hired application."""

    __tablename__ = "onboarding_instances"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            name="uq_onboarding_instances_tenant_application",
        ),
        CheckConstraint(
            "(status != 'completed') OR completed_at IS NOT NULL",
            name="ck_onboarding_instances_completed_at_required",
        ),
        CheckConstraint(
            "(status != 'cancelled') OR cancelled_at IS NOT NULL",
            name="ck_onboarding_instances_cancelled_at_required",
        ),
        Index(
            "ix_onboarding_instances_tenant_status_started_at",
            "tenant_id",
            "status",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    onboarding_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Prevents later template edits from changing existing onboarding work.
    template_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[OnboardingInstanceStatus] = mapped_column(
        Enum(
            OnboardingInstanceStatus,
            name="onboarding_instance_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=OnboardingInstanceStatus.ACTIVE,
        server_default=OnboardingInstanceStatus.ACTIVE.value,
    )
    started_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class OnboardingTask(Base):
    """A tenant-scoped task instantiated from a template task snapshot."""

    __tablename__ = "onboarding_tasks"
    __table_args__ = (
        CheckConstraint(
            "(status != 'completed') OR completed_at IS NOT NULL",
            name="ck_onboarding_tasks_completed_at_required",
        ),
        Index(
            "ix_onboarding_tasks_tenant_status_due_at",
            "tenant_id",
            "status",
            "due_at",
        ),
        Index(
            "ix_onboarding_tasks_assignee_status",
            "assignee_user_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onboarding_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_template_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[OnboardingTaskStatus] = mapped_column(
        Enum(
            OnboardingTaskStatus,
            name="onboarding_task_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=OnboardingTaskStatus.NOT_STARTED,
        server_default=OnboardingTaskStatus.NOT_STARTED.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    blocked_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class OnboardingInstanceHistory(Base):
    """Append-only lifecycle history for an onboarding instance."""

    __tablename__ = "onboarding_instance_history"
    __table_args__ = (
        Index(
            "ix_onboarding_instance_history_tenant_instance_occurred_at",
            "tenant_id",
            "onboarding_instance_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onboarding_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[OnboardingInstanceEventType] = mapped_column(
        Enum(
            OnboardingInstanceEventType,
            name="onboarding_instance_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    from_status: Mapped[OnboardingInstanceStatus | None] = mapped_column(
        Enum(
            OnboardingInstanceStatus,
            name="onboarding_instance_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )
    to_status: Mapped[OnboardingInstanceStatus] = mapped_column(
        Enum(
            OnboardingInstanceStatus,
            name="onboarding_instance_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    occurred_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class OnboardingTaskHistory(Base):
    """Append-only lifecycle and assignment history for an onboarding task."""

    __tablename__ = "onboarding_task_history"
    __table_args__ = (
        Index(
            "ix_onboarding_task_history_tenant_task_occurred_at",
            "tenant_id",
            "onboarding_task_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onboarding_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[OnboardingTaskEventType] = mapped_column(
        Enum(
            OnboardingTaskEventType,
            name="onboarding_task_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    from_status: Mapped[OnboardingTaskStatus | None] = mapped_column(
        Enum(
            OnboardingTaskStatus,
            name="onboarding_task_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )
    to_status: Mapped[OnboardingTaskStatus] = mapped_column(
        Enum(
            OnboardingTaskStatus,
            name="onboarding_task_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    occurred_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
