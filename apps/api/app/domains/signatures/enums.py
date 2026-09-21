"""Offer e-signature lifecycle enumerations."""

from enum import StrEnum


class OfferSignatureStatus(StrEnum):
    """Lifecycle state of one provider-neutral offer signature request."""

    DRAFT = "draft"
    SENT = "sent"
    SIGNED = "signed"
    DECLINED = "declined"
    VOIDED = "voided"
    EXPIRED = "expired"


class OfferSignatureEventType(StrEnum):
    """Immutable audit-grade events in the signature lifecycle."""

    CREATED = "created"
    SENT = "sent"
    SIGNED = "signed"
    DECLINED = "declined"
    VOIDED = "voided"
    EXPIRED = "expired"


class OfferSignatureCallbackEventType(StrEnum):
    """Verified provider events that can affect signature lifecycle state."""

    SIGNED = "signed"
    DECLINED = "declined"
    VOIDED = "voided"
