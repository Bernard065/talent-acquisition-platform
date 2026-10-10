"""Strict request and response schemas for candidate document workflows."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.documents.enums import CandidateDocumentStatus

AllowedDocumentContentType = Literal[
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


class CandidateDocumentCreateRequest(BaseModel):
    """Immutable metadata required before creating an upload intent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    candidate_id: UUID
    original_filename: str = Field(min_length=1, max_length=255)
    declared_content_type: AllowedDocumentContentType
    expected_byte_size: int = Field(ge=1, le=_MAX_DOCUMENT_BYTES)
    checksum_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
    )

    @field_validator("original_filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Reject paths and control characters in a display filename."""
        if "/" in value or "\\" in value:
            raise ValueError("Document filename must not contain a path.")

        if any(ord(character) < 32 for character in value):
            raise ValueError("Document filename contains invalid characters.")

        return value

    @field_validator("checksum_sha256")
    @classmethod
    def normalize_checksum(cls, value: str) -> str:
        """Store SHA-256 values in one canonical lowercase representation."""
        return value.lower()


class CandidateDocumentUploadAuthorizationRequest(BaseModel):
    """
    Deliberately empty request body.

    The document ID is supplied through the path. The server derives every
    storage parameter from immutable persisted metadata.
    """

    model_config = ConfigDict(extra="forbid")


class CandidateDocumentConfirmUploadRequest(BaseModel):
    """
    Deliberately empty request body.

    The API verifies content type, size, and checksum directly with object
    storage rather than trusting values submitted by a client.
    """

    model_config = ConfigDict(extra="forbid")


class CandidateDocumentResponse(BaseModel):
    """Safe document metadata for authorized tenant users."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    original_filename: str
    declared_content_type: str
    expected_byte_size: int
    status: CandidateDocumentStatus
    uploaded_at: datetime | None
    scan_started_at: datetime | None
    scan_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class CandidateDocumentUploadAuthorizationResponse(BaseModel):
    """One short-lived direct-upload authorization; never cache this response."""

    upload_url: str = Field(min_length=1)
    required_headers: dict[str, str]
    expires_at: datetime


class CandidateDocumentDownloadAuthorizationResponse(BaseModel):
    """Short-lived authorization to download a scanned candidate document."""

    url: str = Field(min_length=1)
    expires_at: datetime
