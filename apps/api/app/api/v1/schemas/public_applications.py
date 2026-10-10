"""Strict anonymous request contracts for public job applications."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SubmitPublicApplicationRequest(BaseModel):
    """Candidate-supplied data accepted from a published job application form."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    source_reference: str | None = Field(default=None, max_length=100)
    privacy_consent: Literal[True]
    challenge_token: str | None = Field(default=None, max_length=2_048)


class PublicApplicationAcceptedResponse(BaseModel):
    """Generic acknowledgement that never reveals candidate or application state."""

    model_config = ConfigDict(extra="forbid")

    message: Literal["Application received."] = "Application received."


class PublicApplicationResumeScanResponse(BaseModel):
    """Short-lived proof that one exact résumé file passed scanning."""

    scan_token: str = Field(min_length=1, max_length=255)
    expires_at: datetime
