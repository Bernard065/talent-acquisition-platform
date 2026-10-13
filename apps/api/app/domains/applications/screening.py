"""Controlled choices for recruiter screening assessments."""

from enum import StrEnum


class ScreeningRecommendation(StrEnum):
    """A reviewer's recommendation after assessing an application."""

    ADVANCE = "advance"
    HOLD = "hold"
    REJECT = "reject"


class ApplicationScreeningProgress(StrEnum):
    """Recruiter inbox progress derived from submitted scorecards and stage."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
