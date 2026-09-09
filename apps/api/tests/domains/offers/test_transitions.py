"""Pure tests for offer lifecycle transition rules."""

import pytest

from app.domains.offers.enums import OfferStatus
from app.domains.offers.transitions import (
    InvalidOfferTransitionError,
    validate_offer_transition,
)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (OfferStatus.DRAFT, OfferStatus.PENDING_APPROVAL),
        (OfferStatus.DRAFT, OfferStatus.CANCELLED),
        (OfferStatus.PENDING_APPROVAL, OfferStatus.APPROVED),
        (OfferStatus.PENDING_APPROVAL, OfferStatus.DRAFT),
        (OfferStatus.APPROVED, OfferStatus.SENT),
        (OfferStatus.SENT, OfferStatus.ACCEPTED),
        (OfferStatus.SENT, OfferStatus.DECLINED),
        (OfferStatus.SENT, OfferStatus.EXPIRED),
        (OfferStatus.SENT, OfferStatus.CANCELLED),
    ],
)
def test_allows_valid_offer_transitions(
    current_status: OfferStatus,
    target_status: OfferStatus,
) -> None:
    """Permit only the explicitly supported lifecycle changes."""
    validate_offer_transition(current_status, target_status)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (OfferStatus.DRAFT, OfferStatus.SENT),
        (OfferStatus.PENDING_APPROVAL, OfferStatus.SENT),
        (OfferStatus.APPROVED, OfferStatus.ACCEPTED),
        (OfferStatus.ACCEPTED, OfferStatus.CANCELLED),
        (OfferStatus.DECLINED, OfferStatus.SENT),
        (OfferStatus.EXPIRED, OfferStatus.SENT),
        (OfferStatus.CANCELLED, OfferStatus.DRAFT),
    ],
)
def test_rejects_invalid_offer_transitions(
    current_status: OfferStatus,
    target_status: OfferStatus,
) -> None:
    """Terminal states and skipped stages must remain impossible."""
    with pytest.raises(InvalidOfferTransitionError):
        validate_offer_transition(current_status, target_status)
