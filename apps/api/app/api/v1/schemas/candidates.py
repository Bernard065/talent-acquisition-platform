"""Request and response schemas for candidate endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    JsonValue,
    field_validator,
)

from app.domains.candidates.enums import CandidateConsentStatus


class CandidateCreateRequest(BaseModel):
    """Input for a tenant-scoped candidate profile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
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
    email: EmailStr
    phone: str | None
    location: str | None
    source: str
    source_metadata: dict[str, JsonValue]
    consent_status: CandidateConsentStatus
    consent_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
