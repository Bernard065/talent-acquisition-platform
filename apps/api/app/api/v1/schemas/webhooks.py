"""Strict HTTP contracts for tenant-managed outbound webhooks."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.webhooks.enums import WebhookEndpointStatus

WebhookEventType = Annotated[
    str,
    Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
    ),
]


class CreateWebhookEndpointRequest(BaseModel):
    """Create one HTTPS endpoint and its outbound event subscriptions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    event_types: list[WebhookEventType] = Field(min_length=1, max_length=100)


class UpdateWebhookEndpointRequest(BaseModel):
    """Replace endpoint configuration and its full subscription set."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    event_types: list[WebhookEventType] = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class ExpectedWebhookEndpointVersionRequest(BaseModel):
    """Optimistic-concurrency version for one endpoint lifecycle mutation."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class WebhookEndpointResponse(BaseModel):
    """
    Safe endpoint metadata.

    The signing secret, credential reference, creator subject, delivery state,
    and provider details are deliberately excluded.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    url: str
    status: WebhookEndpointStatus
    event_types: list[str]
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class WebhookEndpointListResponse(BaseModel):
    """Bounded tenant endpoint collection."""

    model_config = ConfigDict(extra="forbid")

    items: list[WebhookEndpointResponse]


class WebhookEndpointDeletedResponse(BaseModel):
    """Idempotent logical-deletion acknowledgement."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str = "deleted"
