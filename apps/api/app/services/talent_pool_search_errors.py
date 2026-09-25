"""Errors raised by the private consented talent-pool search."""


class TalentPoolSearchAccessDeniedError(PermissionError):
    """Raised when a caller lacks permission to search the talent pool."""


class InvalidTalentPoolSearchCursorError(ValueError):
    """Raised when a talent-pool pagination cursor is malformed."""
