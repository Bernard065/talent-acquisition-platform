"""Private API schemas for calendar connection authorization."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
)


class CalendarAuthorizationUrlResponse(BaseModel):
    """A provider URL for one short-lived PKCE authorization attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_url: str = Field(min_length=1, max_length=4096)
    expires_in_seconds: int = Field(ge=1, le=600)


class CalendarConnectionResponse(BaseModel):
    """Safe calendar connection metadata; credentials are never exposed."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    provider: CalendarProvider
    status: CalendarConnectionStatus
    version: int
    created_at: datetime
    updated_at: datetime
