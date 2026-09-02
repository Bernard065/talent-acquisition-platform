"""Business rules for requisition workflow transitions."""

from collections.abc import Mapping

from app.domains.requisitions.enums import RequisitionStatus


class InvalidRequisitionTransition(ValueError):
    """Raised when a requisition status change violates workflow rules."""


_ALLOWED_TRANSITIONS: Mapping[RequisitionStatus, frozenset[RequisitionStatus]] = {
    RequisitionStatus.DRAFT: frozenset(
        {
            RequisitionStatus.PENDING_APPROVAL,
            RequisitionStatus.CANCELLED,
        }
    ),
    RequisitionStatus.PENDING_APPROVAL: frozenset(
        {
            RequisitionStatus.DRAFT,
            RequisitionStatus.APPROVED,
            RequisitionStatus.CANCELLED,
        }
    ),
    RequisitionStatus.APPROVED: frozenset(
        {
            RequisitionStatus.OPEN,
            RequisitionStatus.CANCELLED,
        }
    ),
    RequisitionStatus.OPEN: frozenset(
        {
            RequisitionStatus.ON_HOLD,
            RequisitionStatus.CLOSED,
            RequisitionStatus.CANCELLED,
        }
    ),
    RequisitionStatus.ON_HOLD: frozenset(
        {
            RequisitionStatus.OPEN,
            RequisitionStatus.CLOSED,
            RequisitionStatus.CANCELLED,
        }
    ),
    RequisitionStatus.CLOSED: frozenset(
        {
            RequisitionStatus.OPEN,
        }
    ),
    RequisitionStatus.CANCELLED: frozenset(),
}


def transition_requisition(
    current_status: RequisitionStatus,
    target_status: RequisitionStatus,
) -> RequisitionStatus:
    """Validate and return an allowed target requisition status.

    A caller must explicitly request a meaningful state change. Repeating the
    current status and transitions not listed in the workflow are rejected.
    """

    if current_status == target_status:
        raise InvalidRequisitionTransition(
            f"Requisition is already in the '{current_status.value}' status."
        )

    allowed_target_statuses = _ALLOWED_TRANSITIONS[current_status]
    if target_status not in allowed_target_statuses:
        raise InvalidRequisitionTransition(
            "Cannot transition requisition from "
            f"'{current_status.value}' to '{target_status.value}'."
        )

    return target_status
