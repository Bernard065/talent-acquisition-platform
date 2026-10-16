"""Read-only action items that need the authenticated workspace user's attention."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationActionItem(BaseModel):
    """One overdue follow-up, onboarding task, or interview feedback action."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    kind: Literal[
        "overdue_follow_up",
        "pending_interview_feedback",
        "overdue_onboarding_task",
    ]
    title: str
    candidate_name: str
    requisition_title: str
    due_at: datetime
    href: str
    application_id: UUID


class NotificationActionItemsResponse(BaseModel):
    """Current unresolved attention items for one authenticated user."""

    items: list[NotificationActionItem]
