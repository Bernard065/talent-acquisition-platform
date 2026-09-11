"""Errors for tenant-scoped recruiter search read models."""


class InvalidRecruitingSearchCursorError(ValueError):
    """Raised when a recruiter search cursor is malformed or unsafe."""
