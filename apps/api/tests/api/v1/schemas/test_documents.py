"""Schema-contract tests for candidate document API models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.documents import (
    CandidateDocumentConfirmUploadRequest,
    CandidateDocumentCreateRequest,
    CandidateDocumentResponse,
    CandidateDocumentUploadAuthorizationRequest,
)
from app.db.models.candidate_document import CandidateDocument
from app.domains.documents.enums import CandidateDocumentStatus


def _create_payload() -> dict[str, object]:
    """Build valid document-creation input."""
    return {
        "candidate_id": str(uuid4()),
        "original_filename": "resume.pdf",
        "declared_content_type": "application/pdf",
        "expected_byte_size": 512_000,
        "checksum_sha256": "A" * 64,
    }


def test_document_creation_rejects_unknown_fields() -> None:
    """Reject server-owned and unrecognized client input."""
    payload = {
        **_create_payload(),
        "storage_key": "clients-must-not-control-this",
    }

    with pytest.raises(ValidationError):
        CandidateDocumentCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    "filename",
    [
        "../resume.pdf",
        "folder/resume.pdf",
        r"folder\resume.pdf",
        "resume\x00.pdf",
    ],
)
def test_document_creation_rejects_paths_and_control_characters(
    filename: str,
) -> None:
    """Prevent filenames from being interpreted as object-storage paths."""
    payload = {
        **_create_payload(),
        "original_filename": filename,
    }

    with pytest.raises(ValidationError):
        CandidateDocumentCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    "content_type",
    [
        "image/png",
        "text/plain",
        "application/msword",
    ],
)
def test_document_creation_allows_only_supported_content_types(
    content_type: str,
) -> None:
    """Reject document types outside the explicit PDF and DOCX allow-list."""
    payload = {
        **_create_payload(),
        "declared_content_type": content_type,
    }

    with pytest.raises(ValidationError):
        CandidateDocumentCreateRequest.model_validate(payload)


def test_document_creation_normalizes_checksum_and_filename() -> None:
    """Use one canonical checksum format before calling application services."""
    document = CandidateDocumentCreateRequest.model_validate(
        {
            **_create_payload(),
            "original_filename": "  resume.pdf  ",
        }
    )

    assert document.original_filename == "resume.pdf"
    assert document.checksum_sha256 == "a" * 64


@pytest.mark.parametrize(
    "checksum",
    [
        "a" * 63,
        "a" * 65,
        "g" * 64,
    ],
)
def test_document_creation_rejects_invalid_sha256_checksum(checksum: str) -> None:
    """Require exactly 64 hexadecimal SHA-256 characters."""
    payload = {
        **_create_payload(),
        "checksum_sha256": checksum,
    }

    with pytest.raises(ValidationError):
        CandidateDocumentCreateRequest.model_validate(payload)


def test_upload_authorization_and_confirmation_accept_empty_bodies() -> None:
    """Ensure clients cannot provide storage or verification metadata."""
    authorization = CandidateDocumentUploadAuthorizationRequest.model_validate({})
    confirmation = CandidateDocumentConfirmUploadRequest.model_validate({})

    assert authorization.model_dump() == {}
    assert confirmation.model_dump() == {}


@pytest.mark.parametrize(
    "model",
    [
        CandidateDocumentUploadAuthorizationRequest,
        CandidateDocumentConfirmUploadRequest,
    ],
)
def test_empty_document_workflow_requests_reject_client_supplied_fields(
    model: type[
        CandidateDocumentUploadAuthorizationRequest
        | CandidateDocumentConfirmUploadRequest
    ],
) -> None:
    """Reject client-controlled object keys, hashes, and scan results."""
    with pytest.raises(ValidationError):
        model.model_validate({"storage_key": "untrusted-value"})


def test_document_response_serializes_only_safe_orm_metadata() -> None:
    """Exclude tenant, object key, checksum, and actor identity from responses."""
    now = datetime.now(UTC)
    document = CandidateDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        candidate_id=uuid4(),
        storage_key="v1/tenants/internal/candidates/internal/documents/internal/content",
        original_filename="resume.pdf",
        declared_content_type="application/pdf",
        expected_byte_size=512_000,
        checksum_sha256="a" * 64,
        status=CandidateDocumentStatus.UPLOADED,
        uploaded_at=now,
        scan_started_at=None,
        scan_completed_at=None,
        expires_at=None,
        deleted_at=None,
        created_by_subject="internal-subject",
        created_at=now,
        updated_at=now,
        version=1,
    )

    response = CandidateDocumentResponse.model_validate(document)
    payload = response.model_dump(mode="json")

    assert payload["id"] == str(document.id)
    assert payload["candidate_id"] == str(document.candidate_id)
    assert payload["status"] == "uploaded"
    assert "storage_key" not in payload
    assert "checksum_sha256" not in payload
    assert "tenant_id" not in payload
    assert "created_by_subject" not in payload
