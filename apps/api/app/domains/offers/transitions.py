"""Pure offer lifecycle transition rules."""

from app.domains.offers.enums import OfferStatus

_ALLOWED_TRANSITIONS: dict[OfferStatus, frozenset[OfferStatus]] = {
    OfferStatus.DRAFT: frozenset(
        {
            OfferStatus.PENDING_APPROVAL,
            OfferStatus.CANCELLED,
        }
    ),
    OfferStatus.PENDING_APPROVAL: frozenset(
        {
            OfferStatus.APPROVED,
            OfferStatus.DRAFT,
            OfferStatus.CANCELLED,
        }
    ),
    OfferStatus.APPROVED: frozenset(
        {
            OfferStatus.SENT,
            OfferStatus.CANCELLED,
        }
    ),
    OfferStatus.SENT: frozenset(
        {
            OfferStatus.ACCEPTED,
            OfferStatus.DECLINED,
            OfferStatus.EXPIRED,
            OfferStatus.CANCELLED,
        }
    ),
    OfferStatus.ACCEPTED: frozenset(),
    OfferStatus.DECLINED: frozenset(),
    OfferStatus.EXPIRED: frozenset(),
    OfferStatus.CANCELLED: frozenset(),
}


class InvalidOfferTransitionError(ValueError):
    """Raised when an offer lifecycle change is not permitted."""


def validate_offer_transition(
    current_status: OfferStatus,
    target_status: OfferStatus,
) -> None:
    """Ensure an offer transition is explicitly allowed."""
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidOfferTransitionError(
            f"Cannot transition offer from {current_status.value} "
            f"to {target_status.value}."
        )
