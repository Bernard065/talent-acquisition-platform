"""Enumerations for application debrief and hiring decisions."""

from enum import StrEnum


class HiringDecision(StrEnum):
    """Controlled outcomes available after an application debrief."""

    ADVANCE_TO_OFFER = "advance_to_offer"
    REJECT = "reject"
