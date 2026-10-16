"""Preference mapping for action-item email digests."""

from app.domains.notifications.enums import NotificationEventType

ACTION_ITEM_DIGEST_PREFERENCE_BY_KIND = {
    "overdue_follow_up": NotificationEventType.OVERDUE_FOLLOW_UP_DIGEST,
    "overdue_onboarding_task": NotificationEventType.OVERDUE_ONBOARDING_TASK_DIGEST,
    "pending_interview_feedback": (
        NotificationEventType.PENDING_INTERVIEW_FEEDBACK_DIGEST
    ),
}
ACTION_ITEM_DIGEST_PREFERENCES = tuple(
    ACTION_ITEM_DIGEST_PREFERENCE_BY_KIND.values()
)
