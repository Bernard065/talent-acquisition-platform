"""Controlled choices for recruiter screening assessments."""

from enum import StrEnum


class ScreeningRecommendation(StrEnum):
    """A reviewer's recommendation after assessing an application."""

    ADVANCE = "advance"
    HOLD = "hold"
    REJECT = "reject"
