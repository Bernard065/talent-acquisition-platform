"""Tests for offer signature lifecycle transition rules."""

import pytest

from app.domains.signatures.enums import OfferSignatureStatus
from app.domains.signatures.transitions import (
    InvalidOfferSignatureTransitionError,
    validate_offer_signature_transition,
)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (OfferSignatureStatus.DRAFT, OfferSignatureStatus.SENT),
        (OfferSignatureStatus.DRAFT, OfferSignatureStatus.VOIDED),
        (OfferSignatureStatus.SENT, OfferSignatureStatus.SIGNED),
        (OfferSignatureStatus.SENT, OfferSignatureStatus.DECLINED),
        (OfferSignatureStatus.SENT, OfferSignatureStatus.VOIDED),
        (OfferSignatureStatus.SENT, OfferSignatureStatus.EXPIRED),
    ],
)
def test_allows_explicit_signature_transitions(
    current_status: OfferSignatureStatus,
    target_status: OfferSignatureStatus,
) -> None:
    """Allow only the declared signature lifecycle transitions."""
    validate_offer_signature_transition(current_status, target_status)


@pytest.mark.parametrize(
    "terminal_status",
    [
        OfferSignatureStatus.SIGNED,
        OfferSignatureStatus.DECLINED,
        OfferSignatureStatus.VOIDED,
        OfferSignatureStatus.EXPIRED,
    ],
)
def test_rejects_transitions_from_terminal_status(
    terminal_status: OfferSignatureStatus,
) -> None:
    """Completed signature outcomes cannot be changed."""
    with pytest.raises(InvalidOfferSignatureTransitionError):
        validate_offer_signature_transition(
            terminal_status,
            OfferSignatureStatus.SENT,
        )


def test_rejects_skipping_provider_submission() -> None:
    """A draft request cannot become signed without first being sent."""
    with pytest.raises(InvalidOfferSignatureTransitionError):
        validate_offer_signature_transition(
            OfferSignatureStatus.DRAFT,
            OfferSignatureStatus.SIGNED,
        )


def test_rejects_repeated_transition() -> None:
    """A request cannot transition to its existing status."""
    with pytest.raises(InvalidOfferSignatureTransitionError):
        validate_offer_signature_transition(
            OfferSignatureStatus.SENT,
            OfferSignatureStatus.SENT,
        )
