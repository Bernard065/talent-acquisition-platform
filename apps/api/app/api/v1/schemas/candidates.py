"""Request and response schemas for candidate endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from email_validator import validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)

from app.domains.candidates.enums import CandidateConsentStatus, CandidatePrivacyStatus


def _validate_email_address(value: str) -> str:
    """Allow RFC 2606 test domains used by local/test fixtures.

    Malformed addresses are still rejected.
    """
    validated = validate_email(
        value,
        check_deliverability=False,
        test_environment=True,
    )
    return str(validated.normalized)


class CandidateCreateRequest(BaseModel):
    """Input for a tenant-scoped candidate profile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: Annotated[str, AfterValidator(_validate_email_address)] = Field(
        min_length=3,
        max_length=254,
    )
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    source: str = Field(min_length=1, max_length=100)
    source_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        max_length=50,
    )
    consent_status: CandidateConsentStatus = CandidateConsentStatus.UNKNOWN

    @field_validator("phone", "location", mode="before")
    @classmethod
    def empty_optional_text_is_null(cls, value: object) -> object:
        """Normalize blank optional strings to null."""
        if isinstance(value, str) and not value.strip():
            return None

        return value


class CandidateResponse(BaseModel):
    """Internal tenant-scoped representation of a candidate profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: Annotated[str, AfterValidator(_validate_email_address)]
    phone: str | None
    location: str | None
    source: str
    source_metadata: dict[str, JsonValue]
    consent_status: CandidateConsentStatus
    consent_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class CandidateListResponse(BaseModel):
    """Cursor-paginated internal candidate search results."""

    model_config = ConfigDict(extra="forbid")

    items: list[CandidateResponse]
    next_cursor: str | None = None


class CandidateFilterOptionsResponse(BaseModel):
    """Tenant-wide source and location values for candidate filters."""

    model_config = ConfigDict(extra="forbid")

    sources: list[str]
    locations: list[str]


class CandidatePrivacyOperationResponse(BaseModel):
    """PII-free acknowledgement for a consent or erasure operation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: UUID
    consent_status: CandidateConsentStatus
    privacy_status: CandidatePrivacyStatus
    erasure_requested_at: datetime | None
    erased_at: datetime | None
