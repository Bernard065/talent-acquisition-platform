"""Immutable, privacy-safe receipts for verified e-signature callbacks."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.signatures.enums import OfferSignatureCallbackEventType


class OfferSignatureCallbackReceipt(Base):
    """
    Idempotent evidence that a provider callback was verified and processed.

    Raw callback bodies, headers, provider signatures, secrets, signer PII,
    signing URLs, and document content are intentionally never persisted.
    """

    __tablename__ = "offer_signature_callback_receipts"
    __table_args__ = (
        CheckConstraint(
            "char_length(payload_sha256) = 64",
            name="ck_offer_signature_callback_receipts_payload_sha256_length",
        ),
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_offer_signature_callback_receipts_provider_event",
        ),
        Index(
            "ix_offer_signature_callback_receipts_tenant_request_received_at",
            "tenant_id",
            "offer_signature_request_id",
            "received_at",
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
        ForeignKey("offer_signature_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Provider identifiers are opaque routing and idempotency references.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_envelope_reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    event_type: Mapped[OfferSignatureCallbackEventType] = mapped_column(
        Enum(
            OfferSignatureCallbackEventType,
            name="offer_signature_callback_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )

    # The digest detects an attempted mutation of a reused provider event ID.
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Supplied by the verified provider event; validated as timezone-aware later.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
