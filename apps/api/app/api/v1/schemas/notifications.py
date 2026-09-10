"""Strict HTTP contracts for private notification preferences."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationEventType,
)


class UpdateNotificationPreferenceRequest(BaseModel):
    """Input for creating or updating one self-service preference."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_version: int = Field(ge=0)


class NotificationPreferenceResponse(BaseModel):
    """Effective preference state for the authenticated tenant user."""

    model_config = ConfigDict(from_attributes=True)

    event_type: NotificationEventType
    channel: NotificationChannel
    enabled: bool
    version: int
    updated_at: datetime | None
