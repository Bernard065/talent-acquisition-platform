"""Controlled legal-hold reasons without free-text case narratives."""

from enum import StrEnum


class CandidateRetentionHoldReason(StrEnum):
    """High-level retention exception categories for an audited legal hold."""

    LEGAL_CLAIM = "legal_claim"
    STATUTORY_OBLIGATION = "statutory_obligation"
    REGULATORY_REQUEST = "regulatory_request"
    OTHER_EVIDENCE = "other_evidence"
