"""Safe errors for anonymous public job application submission."""


class PublicApplicationJobNotFoundError(LookupError):
    """Raised when a job is not currently eligible for public applications."""
