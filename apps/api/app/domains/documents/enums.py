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
