"""Pure offer signature lifecycle transition rules."""

from app.domains.signatures.enums import OfferSignatureStatus

_ALLOWED_TRANSITIONS: dict[
    OfferSignatureStatus,
    frozenset[OfferSignatureStatus],
] = {
    OfferSignatureStatus.DRAFT: frozenset(
        {
            OfferSignatureStatus.SENT,
            OfferSignatureStatus.VOIDED,
        }
    ),
    OfferSignatureStatus.SENT: frozenset(
        {
            OfferSignatureStatus.SIGNED,
            OfferSignatureStatus.DECLINED,
            OfferSignatureStatus.VOIDED,
            OfferSignatureStatus.EXPIRED,
        }
    ),
    OfferSignatureStatus.SIGNED: frozenset(),
    OfferSignatureStatus.DECLINED: frozenset(),
    OfferSignatureStatus.VOIDED: frozenset(),
    OfferSignatureStatus.EXPIRED: frozenset(),
}


class InvalidOfferSignatureTransitionError(ValueError):
    """Raised when a signature lifecycle transition is not allowed."""


def validate_offer_signature_transition(
    current_status: OfferSignatureStatus,
    target_status: OfferSignatureStatus,
) -> None:
    """Ensure a signature request can make the requested state change."""
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidOfferSignatureTransitionError(
            "Cannot transition offer signature request from "
            f"{current_status.value} to {target_status.value}."
        )
