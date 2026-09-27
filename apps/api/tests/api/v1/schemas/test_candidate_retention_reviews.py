"""Request contract tests for private candidate retention reviews."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.candidate_retention_reviews import (
    CandidateRetentionExecutionRequest,
    CandidateRetentionReviewCreateRequest,
)


def _valid_payload() -> dict[str, object]:
    """Return a payload as it arrives from a normal JSON HTTP client."""
    return {
        "policy_id": str(uuid4()),
        "purpose": "unsuccessful_applicant",
        "disposition": "retain",
        "reason_code": "not_yet_due",
        "checklist": {
            "active_matters_reviewed": True,
            "legal_holds_reviewed": True,
            "other_lawful_basis_reviewed": True,
            "employee_obligations_reviewed": True,
            "external_processors_reviewed": True,
            "backup_restore_safeguards_reviewed": True,
        },
        "next_review_at": datetime.now(UTC).isoformat(),
    }


def test_create_request_accepts_valid_json_uuid_enum_and_datetime_strings() -> None:
    """Strict object shape must still support JSON's string representations."""
    request = CandidateRetentionReviewCreateRequest.model_validate(_valid_payload())

    assert request.policy_id.version == 4
    assert request.purpose.value == "unsuccessful_applicant"
    assert request.next_review_at is not None


def test_create_request_rejects_non_boolean_checklist_values() -> None:
    """Checklist attestations must not coerce strings or integers to booleans."""
    payload = _valid_payload()
    checklist = payload["checklist"]
    assert isinstance(checklist, dict)
    checklist["legal_holds_reviewed"] = "true"

    with pytest.raises(ValidationError):
        CandidateRetentionReviewCreateRequest.model_validate(payload)


def test_create_request_rejects_unknown_fields() -> None:
    """Review requests cannot smuggle free-form or unsupported metadata."""
    payload = _valid_payload()
    payload["notes"] = "Do not persist free-form candidate notes."

    with pytest.raises(ValidationError):
        CandidateRetentionReviewCreateRequest.model_validate(payload)


def test_execution_request_requires_explicit_true_confirmation() -> None:
    """Execution must require an affirmative, typed confirmation field."""
    request = CandidateRetentionExecutionRequest.model_validate(
        {"confirm_erasure": True}
    )

    assert request.confirm_erasure is True
    with pytest.raises(ValidationError):
        CandidateRetentionExecutionRequest.model_validate({"confirm_erasure": False})
    with pytest.raises(ValidationError):
        CandidateRetentionExecutionRequest.model_validate({})


def test_execution_request_rejects_unknown_fields() -> None:
    """Execution requests cannot smuggle candidate data into stored idempotency."""
    with pytest.raises(ValidationError):
        CandidateRetentionExecutionRequest.model_validate(
            {
                "confirm_erasure": True,
                "candidate_email": "candidate@example.test",
            }
        )
