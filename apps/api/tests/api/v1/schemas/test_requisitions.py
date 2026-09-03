"""Tests for requisition API request and response schemas."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.requisitions import (
    RequisitionCreateRequest,
    RequisitionResponse,
    RequisitionTransitionRequest,
    RequisitionUpdateRequest,
)
from app.domains.requisitions.enums import RequisitionStatus


def test_create_request_accepts_valid_input() -> None:
    """Accept valid requisition creation input."""
    request = RequisitionCreateRequest(
        title="  Senior Backend Engineer  ",
        department=" Engineering ",
        headcount=2,
    )

    assert request.title == "Senior Backend Engineer"
    assert request.department == "Engineering"
    assert request.headcount == 2


def test_create_request_rejects_unknown_fields() -> None:
    """Reject fields not defined by the create schema."""
    with pytest.raises(ValidationError):
        RequisitionCreateRequest.model_validate(
            {"title": "Senior Backend Engineer", "tenant_id": str(uuid4())}
        )


def test_update_request_requires_at_least_one_field() -> None:
    """Reject an update request with no fields supplied."""
    with pytest.raises(ValidationError):
        RequisitionUpdateRequest()


def test_update_request_rejects_null_required_fields() -> None:
    """Reject null values for required requisition attributes."""
    with pytest.raises(ValidationError):
        RequisitionUpdateRequest(title=None)

    with pytest.raises(ValidationError):
        RequisitionUpdateRequest(headcount=None)


def test_update_request_excludes_status_changes() -> None:
    """Reject status changes through the update schema."""
    with pytest.raises(ValidationError):
        RequisitionUpdateRequest.model_validate(
            {"status": RequisitionStatus.OPEN}
        )


def test_transition_request_parses_workflow_status() -> None:
    """Parse a workflow status string into its enum value."""
    request = RequisitionTransitionRequest.model_validate(
        {"target_status": "pending_approval"}
    )

    assert request.target_status is RequisitionStatus.PENDING_APPROVAL


def test_response_serializes_orm_style_object() -> None:
    """Serialize an ORM-style object through the response schema."""
    timestamp = datetime.now(UTC)
    requisition_id = uuid4()

    response = RequisitionResponse.model_validate(
        SimpleNamespace(
            id=requisition_id,
            title="Senior Backend Engineer",
            description=None,
            department="Engineering",
            location="Nairobi",
            headcount=1,
            status=RequisitionStatus.DRAFT,
            version=1,
            created_by_subject="subject-123",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    assert response.id == requisition_id
    assert response.status is RequisitionStatus.DRAFT
    assert response.version == 1
