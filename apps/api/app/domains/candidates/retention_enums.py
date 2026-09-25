"""Candidate-retention policy lifecycle values."""

from enum import StrEnum


class CandidateRetentionPolicyStatus(StrEnum):
    """Draft, active, and superseded versions of a tenant's retention policy."""

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"
