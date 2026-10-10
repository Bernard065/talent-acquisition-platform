"""Safe errors for anonymous public job application submission."""


class PublicApplicationJobNotFoundError(LookupError):
    """Raised when a job is not currently eligible for public applications."""


class PublicApplicationResumeRejectedError(ValueError):
    """Raised when an uploaded résumé fails the malware scan."""


class PublicApplicationResumeScanProofError(ValueError):
    """Raised when a clean scan proof is expired, altered, or already used."""


class PublicApplicationScanUnavailableError(RuntimeError):
    """Raised when a résumé cannot be scanned before submission."""
