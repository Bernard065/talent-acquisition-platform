"""Tenant-scoped HRIS connection and onboarding handoff persistence."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
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
from app.domains.hris.enums import (
    HrisConnectionStatus,
    HrisHandoffStatus,
    HrisProvider,
)


class HrisConnection(Base):
    """
    A tenant-owned connection to an external HRIS.

    `credential_reference` is an opaque reference to Infisical. It must never
    contain credentials, tokens, client secrets, HRIS URLs, or employee data.
    """

    __tablename__ = "hris_connections"
    __table_args__ = (
        CheckConstraint(
            "(deleted_at IS NULL) OR (status = 'disabled')",
            name="ck_hris_connections_deleted_requires_disabled",
        ),
        UniqueConstraint(
            "credential_reference",
            name="uq_hris_connections_credential_reference",
        ),
        Index(
            "uq_hris_connections_tenant_provider_name_active",
            "tenant_id",
            "provider",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_hris_connections_tenant_status",
            "tenant_id",
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
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    provider: Mapped[HrisProvider] = mapped_column(
        Enum(
            HrisProvider,
            name="hris_provider",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[HrisConnectionStatus] = mapped_column(
        Enum(
            HrisConnectionStatus,
            name="hris_connection_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=HrisConnectionStatus.ACTIVE,
        server_default=HrisConnectionStatus.ACTIVE.value,
    )
    credential_reference: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_by_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_by_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class HrisHandoff(Base):
    """
    Durable handoff state from one onboarding instance to one HRIS connection.

    The worker loads the candidate and accepted-offer data privately when it
    needs to dispatch. This row and its future outbox payload retain only
    identifiers and classified failure codes.
    """

    __tablename__ = "hris_handoffs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "onboarding_instance_id",
            name="uq_hris_handoffs_tenant_onboarding_instance",
        ),
        UniqueConstraint(
            "external_idempotency_key",
            name="uq_hris_handoffs_external_idempotency_key",
        ),
        CheckConstraint(
            "(status != 'succeeded') OR succeeded_at IS NOT NULL",
            name="ck_hris_handoffs_succeeded_at_required",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_hris_handoffs_attempt_count_nonnegative",
        ),
        Index(
            "ix_hris_handoffs_tenant_status_updated_at",
            "tenant_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_hris_handoffs_connection_status",
            "hris_connection_id",
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
    hris_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("hris_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    onboarding_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("onboarding_instances.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[HrisHandoffStatus] = mapped_column(
        Enum(
            HrisHandoffStatus,
            name="hris_handoff_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=HrisHandoffStatus.PENDING,
        server_default=HrisHandoffStatus.PENDING.value,
    )

    # Stable for the handoff lifetime; provider adapters use this on retries.
    external_idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=lambda: str(uuid4()),
    )

    # Provider employee IDs are opaque integration references, never authorization IDs.
    external_employee_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    succeeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
