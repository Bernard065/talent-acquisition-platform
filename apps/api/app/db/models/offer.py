"""Tenant-scoped offer persistence and immutable lifecycle history."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.offers.enums import (
    OfferLifecycleEventType,
    OfferPayPeriod,
    OfferStatus,
)

_ACTIVE_OFFER_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "sent",
)


class Offer(Base):
    """One tenant-owned compensation offer for an application."""

    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint(
            "char_length(currency) = 3",
            name="ck_offers_currency_length",
        ),
        CheckConstraint(
            "base_salary > 0",
            name="ck_offers_base_salary_positive",
        ),
        CheckConstraint(
            "bonus_amount IS NULL OR bonus_amount >= 0",
            name="ck_offers_bonus_amount_non_negative",
        ),
        CheckConstraint(
            "(status != 'sent') OR sent_at IS NOT NULL",
            name="ck_offers_sent_at_required",
        ),
        CheckConstraint(
            "(status != 'accepted') OR accepted_at IS NOT NULL",
            name="ck_offers_accepted_at_required",
        ),
        CheckConstraint(
            "(status != 'declined') OR declined_at IS NOT NULL",
            name="ck_offers_declined_at_required",
        ),
        CheckConstraint(
            "(status != 'cancelled') OR cancelled_at IS NOT NULL",
            name="ck_offers_cancelled_at_required",
        ),
        CheckConstraint(
            "(status != 'expired') OR expired_at IS NOT NULL",
            name="ck_offers_expired_at_required",
        ),
        Index(
            "uq_offers_one_active_offer_per_application",
            "tenant_id",
            "application_id",
            unique=True,
            postgresql_where=text(
                "status IN ('draft', 'pending_approval', 'approved', 'sent')"
            ),
        ),
        Index(
            "ix_offers_tenant_status_expiry_at",
            "tenant_id",
            "status",
            "expires_at",
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

    status: Mapped[OfferStatus] = mapped_column(
        Enum(
            OfferStatus,
            name="offer_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=OfferStatus.DRAFT,
        server_default=OfferStatus.DRAFT.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    pay_period: Mapped[OfferPayPeriod] = mapped_column(
        Enum(
            OfferPayPeriod,
            name="offer_pay_period",
            values_callable=lambda periods: [period.value for period in periods],
        ),
        nullable=False,
    )
    bonus_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )
    equity_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class OfferLifecycleHistory(Base):
    """Append-only audit-grade history of an offer's lifecycle events."""

    __tablename__ = "offer_lifecycle_history"
    __table_args__ = (
        Index(
            "ix_offer_lifecycle_history_tenant_offer_occurred_at",
            "tenant_id",
            "offer_id",
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
    offer_id: Mapped[UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[OfferLifecycleEventType] = mapped_column(
        Enum(
            OfferLifecycleEventType,
            name="offer_lifecycle_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    from_status: Mapped[OfferStatus | None] = mapped_column(
        Enum(
            OfferStatus,
            name="offer_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=True,
    )
    to_status: Mapped[OfferStatus] = mapped_column(
        Enum(
            OfferStatus,
            name="offer_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
    )
    occurred_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
