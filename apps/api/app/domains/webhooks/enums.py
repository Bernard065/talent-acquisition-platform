"""Webhook delivery lifecycle enumerations."""

from enum import StrEnum


class WebhookEndpointStatus(StrEnum):
    """Administrative lifecycle state for a tenant webhook endpoint."""

    ACTIVE = "active"
    DISABLED = "disabled"


class WebhookDeliveryStatus(StrEnum):
    """Delivery lifecycle state for one endpoint and source event."""

    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    DISABLED = "disabled"
