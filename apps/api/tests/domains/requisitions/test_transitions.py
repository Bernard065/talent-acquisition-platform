"""Tests for requisition workflow transitions."""

import pytest

from app.domains.requisitions.enums import RequisitionStatus
from app.domains.requisitions.transitions import (
    InvalidRequisitionTransition,
    transition_requisition,
)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (RequisitionStatus.DRAFT, RequisitionStatus.PENDING_APPROVAL),
        (RequisitionStatus.DRAFT, RequisitionStatus.CANCELLED),
        (RequisitionStatus.PENDING_APPROVAL, RequisitionStatus.DRAFT),
        (RequisitionStatus.PENDING_APPROVAL, RequisitionStatus.APPROVED),
        (RequisitionStatus.PENDING_APPROVAL, RequisitionStatus.CANCELLED),
        (RequisitionStatus.APPROVED, RequisitionStatus.OPEN),
        (RequisitionStatus.APPROVED, RequisitionStatus.CANCELLED),
        (RequisitionStatus.OPEN, RequisitionStatus.ON_HOLD),
        (RequisitionStatus.OPEN, RequisitionStatus.CLOSED),
        (RequisitionStatus.OPEN, RequisitionStatus.CANCELLED),
        (RequisitionStatus.ON_HOLD, RequisitionStatus.OPEN),
        (RequisitionStatus.ON_HOLD, RequisitionStatus.CLOSED),
        (RequisitionStatus.ON_HOLD, RequisitionStatus.CANCELLED),
        (RequisitionStatus.CLOSED, RequisitionStatus.OPEN),
    ],
)
def test_allows_valid_transition(
    current_status: RequisitionStatus,
    target_status: RequisitionStatus,
) -> None:
    """Allow every transition explicitly defined by the workflow."""
    assert transition_requisition(current_status, target_status) == target_status


def test_rejects_repeated_status() -> None:
    """Reject a transition when the target matches the current status."""
    with pytest.raises(InvalidRequisitionTransition):
        transition_requisition(
            RequisitionStatus.DRAFT,
            RequisitionStatus.DRAFT,
        )


def test_rejects_invalid_transition() -> None:
    """Reject a transition that is not allowed by the workflow."""
    with pytest.raises(InvalidRequisitionTransition):
        transition_requisition(
            RequisitionStatus.DRAFT,
            RequisitionStatus.OPEN,
        )


def test_rejects_any_transition_from_cancelled() -> None:
    """Reject every transition originating from a cancelled requisition."""
    with pytest.raises(InvalidRequisitionTransition):
        transition_requisition(
            RequisitionStatus.CANCELLED,
            RequisitionStatus.DRAFT,
        )
