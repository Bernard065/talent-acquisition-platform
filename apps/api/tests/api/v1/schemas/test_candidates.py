"""Contract tests for candidate and application API schemas."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.applications import (
    ApplicationCreateRequest,
    ApplicationResponse,
)
from app.api.v1.schemas.candidates import (
    CandidateCreateRequest,
    CandidateResponse,
)
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)


def test_candidate_create_request_accepts_valid_input() -> None:
    """Accept and normalize valid candidate creation data."""
    request = CandidateCreateRequest(
        full_name="  Ada Lovelace  ",
        email="Ada.Lovelace@Acme.IO",
        phone="  +254700000000  ",
        location="  Nairobi  ",
        source="  employee_referral  ",
        source_metadata={"campaign": "engineering-q3"},
        consent_status=CandidateConsentStatus.GRANTED,
    )

    assert request.full_name == "Ada Lovelace"
    assert str(request.email) == "Ada.Lovelace@acme.io"
    assert request.phone == "+254700000000"
    assert request.location == "Nairobi"
    assert request.source == "employee_referral"
    assert request.source_metadata == {"campaign": "engineering-q3"}
    assert request.consent_status is CandidateConsentStatus.GRANTED


def test_candidate_create_request_converts_blank_optional_fields_to_null() -> None:
    """Convert blank optional candidate fields to null values."""
    request = CandidateCreateRequest(
        full_name="Ada Lovelace",
        email="ada@acme.io",
        phone="   ",
        location="",
        source="employee_referral",
    )

    assert request.phone is None
    assert request.location is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "full_name": "Ada Lovelace",
            "email": "not-an-email",
            "source": "employee_referral",
        },
        {
            "full_name": "Ada Lovelace",
            "email": "ada@acme.io",
            "source": "",
        },
        {
            "full_name": "Ada Lovelace",
            "email": "ada@acme.io",
            "source": "employee_referral",
            "tenant_id": str(uuid4()),
        },
    ],
)
def test_candidate_create_request_rejects_invalid_or_untrusted_input(
    payload: dict[str, str],
) -> None:
    """Reject invalid candidate data and client-controlled tenant IDs."""
    with pytest.raises(ValidationError):
        CandidateCreateRequest.model_validate(payload)


def test_candidate_create_request_rejects_non_json_source_metadata() -> None:
    """Reject source metadata containing values that are not JSON serializable."""
    with pytest.raises(ValidationError):
        CandidateCreateRequest(
            full_name="Ada Lovelace",
            email="ada@acme.io",
            source="employee_referral",
            source_metadata=cast(Any, {"invalid": {"a", "set"}}),
        )


def test_candidate_create_request_defaults_consent_to_unknown() -> None:
    """Default omitted candidate consent status to unknown."""
    request = CandidateCreateRequest(
        full_name="Ada Lovelace",
        email="ada@acme.io",
        source="employee_referral",
    )

    assert request.consent_status is CandidateConsentStatus.UNKNOWN


def test_candidate_response_serializes_orm_style_object() -> None:
    """Serialize an ORM-style candidate object into the response schema."""
    candidate_id = uuid4()
    timestamp = datetime.now(UTC)

    response = CandidateResponse.model_validate(
        SimpleNamespace(
            id=candidate_id,
            full_name="Ada Lovelace",
            email="ada@acme.io",
            phone=None,
            location="Nairobi",
            source="employee_referral",
            source_metadata={"campaign": "engineering-q3"},
            consent_status=CandidateConsentStatus.GRANTED,
            consent_updated_at=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
            version=1,
        )
    )

    assert response.id == candidate_id
    assert str(response.email) == "ada@acme.io"
    assert response.consent_status is CandidateConsentStatus.GRANTED
    assert response.version == 1


def test_application_create_request_rejects_unknown_fields() -> None:
    """Reject application creation fields outside the public schema."""
    with pytest.raises(ValidationError):
        ApplicationCreateRequest.model_validate(
            {
                "candidate_id": uuid4(),
                "requisition_id": uuid4(),
                "status": "applied",
            }
        )


def test_application_response_serializes_orm_style_object() -> None:
    """Serialize an ORM-style application object into the response schema."""
    application_id = uuid4()
    candidate_id = uuid4()
    requisition_id = uuid4()
    timestamp = datetime.now(UTC)

    response = ApplicationResponse.model_validate(
        SimpleNamespace(
            id=application_id,
            candidate_id=candidate_id,
            requisition_id=requisition_id,
            status=ApplicationStatus.APPLIED,
            applied_at=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
            version=1,
        )
    )

    assert response.id == application_id
    assert response.candidate_id == candidate_id
    assert response.requisition_id == requisition_id
    assert response.status is ApplicationStatus.APPLIED
