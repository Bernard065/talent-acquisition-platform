"""Tenant-scoped offer signature request and immutable history persistence."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.offers.enums import OfferPayPeriod
from app.domains.signatures.enums import (
    OfferSignatureEventType,
    OfferSignatureStatus,
)


class OfferSignatureRequest(Base):
    """
    A provider-neutral signature request for one approved offer.

    Offer terms are snapshotted here. They must never be read from the mutable
    offer when proving what a candidate was asked to sign.
    """

    __tablename__ = "offer_signature_requests"
    __table_args__ = (
        CheckConstraint(
            "char_length(currency) = 3",
            name="ck_offer_signature_requests_currency_length",
        ),
        CheckConstraint(
            "base_salary > 0",
            name="ck_offer_signature_requests_base_salary_positive",
        ),
        CheckConstraint(
            "bonus_amount IS NULL OR bonus_amount >= 0",
            name="ck_offer_signature_requests_bonus_amount_nonnegative",
        ),
        CheckConstraint(
            "(status != 'sent') OR sent_at IS NOT NULL",
            name="ck_offer_signature_requests_sent_at_required",
        ),
        CheckConstraint(
            "(status != 'signed') OR signed_at IS NOT NULL",
            name="ck_offer_signature_requests_signed_at_required",
        ),
        CheckConstraint(
            "(status != 'declined') OR declined_at IS NOT NULL",
            name="ck_offer_signature_requests_declined_at_required",
        ),
        CheckConstraint(
            "(status != 'voided') OR voided_at IS NOT NULL",
            name="ck_offer_signature_requests_voided_at_required",
        ),
        CheckConstraint(
            "(status != 'expired') OR expired_at IS NOT NULL",
            name="ck_offer_signature_requests_expired_at_required",
        ),
        UniqueConstraint(
            "tenant_id",
            "offer_id",
            "offer_version",
            name="uq_offer_signature_requests_tenant_offer_version",
        ),
        Index(
            "ix_offer_signature_requests_tenant_offer_status",
            "tenant_id",
            "offer_id",
            "status",
        ),
        Index(
            "ix_offer_signature_requests_tenant_status_expiry",
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
    offer_id: Mapped[UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Provider identifiers are opaque references, never signing URLs or tokens.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_envelope_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    document_reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[OfferSignatureStatus] = mapped_column(
        Enum(
            OfferSignatureStatus,
            name="offer_signature_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=OfferSignatureStatus.DRAFT,
        server_default=OfferSignatureStatus.DRAFT.value,
    )

    # Immutable snapshot of the approved offer terms.
    offer_version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    pay_period: Mapped[OfferPayPeriod] = mapped_column(
        PostgreSQLEnum(
            OfferPayPeriod,
            name="offer_pay_period",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=False,
    )
    bonus_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )
    proposed_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[datetime | None] = mapped_column(
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


class OfferSignatureHistory(Base):
    """Append-only lifecycle history for an offer signature request."""

    __tablename__ = "offer_signature_history"
    __table_args__ = (
        Index(
            "ix_offer_signature_history_tenant_request_occurred_at",
            "tenant_id",
            "offer_signature_request_id",
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
    offer_signature_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("offer_signature_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[OfferSignatureEventType] = mapped_column(
        Enum(
            OfferSignatureEventType,
            name="offer_signature_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    from_status: Mapped[OfferSignatureStatus | None] = mapped_column(
        PostgreSQLEnum(
            OfferSignatureStatus,
            name="offer_signature_status",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=True,
    )
    to_status: Mapped[OfferSignatureStatus] = mapped_column(
        PostgreSQLEnum(
            OfferSignatureStatus,
            name="offer_signature_status",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=False,
    )
    occurred_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
