"""Errors for anonymous public job discovery."""


class PublicJobNotFoundError(LookupError):
    """Raised without revealing whether a posting ever existed."""


class InvalidPublicJobCursorError(ValueError):
    """Raised for a malformed public-jobs pagination cursor."""
