"""Document lifecycle enumerations."""

from enum import StrEnum


class CandidateDocumentStatus(StrEnum):
    """Security lifecycle for a candidate-owned uploaded document."""

    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    SCANNING = "scanning"
    AVAILABLE = "available"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    DELETED = "deleted"


class CandidateDocumentScanStatus(StrEnum):
    """Lifecycle state for one malware-scanning attempt."""

    SCANNING = "scanning"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"


class MalwareScanVerdict(StrEnum):
    """Safe scanner outcomes that may affect document availability."""

    CLEAN = "clean"
    INFECTED = "infected"
