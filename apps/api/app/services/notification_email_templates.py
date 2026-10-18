"""Allow-listed, privacy-safe plain-text notification email templates."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domains.notifications.enums import (
    NotificationDigestFrequency,
    NotificationEventType,
)
from app.services.email_sender import EmailMessage


class UnsupportedNotificationTemplateError(ValueError):
    """Raised when an event and template key are not an approved pair."""


@dataclass(frozen=True, slots=True)
class NotificationEmailTemplate:
    """Static copy for one internal workflow notification."""

    subject: str
    text_body: str


@dataclass(frozen=True, slots=True)
class InterviewNotificationDetails:
    """Current, tenant-verified data rendered into an interview email."""

    role_title: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    interview_format: str | None
    location: str | None
    meeting_url: str | None
    interview_url: str
    role_url: str | None
    is_candidate: bool


_TEMPLATES: dict[tuple[NotificationEventType, str], NotificationEmailTemplate] = {
    (
        NotificationEventType.OFFER_APPROVAL_REQUESTED,
        "offer_approval_requested",
    ): NotificationEmailTemplate(
        subject="Offer review requested",
        text_body=(
            "An offer is ready for your review in the Talent Acquisition Platform.\n\n"
            "Sign in to review the offer and record your decision."
        ),
    ),
    (NotificationEventType.OFFER_APPROVED, "offer_approved"): NotificationEmailTemplate(
        subject="Offer approval complete",
        text_body=(
            "An offer has completed its approval workflow.\n\n"
            "Sign in to the Talent Acquisition Platform to review its current status."
        ),
    ),
    (NotificationEventType.OFFER_SENT, "offer_sent"): NotificationEmailTemplate(
        subject="Offer update",
        text_body=(
            "An offer has been sent to a candidate.\n\n"
            "Sign in to the Talent Acquisition Platform to review its status."
        ),
    ),
    (NotificationEventType.OFFER_ACCEPTED, "offer_accepted"): NotificationEmailTemplate(
        subject="Offer accepted",
        text_body=(
            "A candidate has accepted an offer.\n\n"
            "Sign in to the Talent Acquisition Platform to review the hiring workflow."
        ),
    ),
    (
        NotificationEventType.ONBOARDING_STARTED,
        "onboarding_started",
    ): NotificationEmailTemplate(
        subject="Onboarding started",
        text_body=(
            "An onboarding workflow has started.\n\n"
            "Sign in to the Talent Acquisition Platform to review its tasks."
        ),
    ),
    (
        NotificationEventType.ONBOARDING_TASK_ASSIGNED,
        "onboarding_task_assigned",
    ): NotificationEmailTemplate(
        subject="Onboarding task assigned",
        text_body=(
            "A new onboarding task has been assigned to you.\n\n"
            "Sign in to the Talent Acquisition Platform to view the task instructions."
        ),
    ),
    (
        NotificationEventType.ONBOARDING_TASK_BLOCKED,
        "onboarding_task_blocked",
    ): NotificationEmailTemplate(
        subject="Onboarding task needs attention",
        text_body=(
            "An onboarding task needs attention.\n\n"
            "Sign in to the Talent Acquisition Platform to review the task."
        ),
    ),
    (
        NotificationEventType.ONBOARDING_TASK_COMPLETED,
        "onboarding_task_completed",
    ): NotificationEmailTemplate(
        subject="Onboarding task completed",
        text_body=(
            "An onboarding task has been completed.\n\n"
            "Sign in to the Talent Acquisition Platform for details."
        ),
    ),
    (
        NotificationEventType.ONBOARDING_TASK_UNBLOCKED,
        "onboarding_task_unblocked",
    ): NotificationEmailTemplate(
        subject="Update to your onboarding help request",
        text_body=(
            "People Operations responded to your onboarding help request.\n\n"
            "Sign in to review the response and continue your onboarding checklist."
        ),
    ),
    (
        NotificationEventType.INTERVIEW_SCHEDULED,
        "interview_scheduled",
    ): NotificationEmailTemplate(
        subject="Interview scheduled",
        text_body="An interview has been scheduled.",
    ),
    (
        NotificationEventType.INTERVIEW_RESCHEDULED,
        "interview_rescheduled",
    ): NotificationEmailTemplate(
        subject="Interview rescheduled",
        text_body="An interview has been rescheduled.",
    ),
    (
        NotificationEventType.INTERVIEW_CANCELLED,
        "interview_cancelled",
    ): NotificationEmailTemplate(
        subject="Interview cancelled",
        text_body="An interview has been cancelled.",
    ),
    (
        NotificationEventType.INTERVIEW_REMINDER,
        "interview_reminder",
    ): NotificationEmailTemplate(
        subject="Interview reminder",
        text_body="Your interview is coming up.",
    ),
    (
        NotificationEventType.INTERVIEW_CALENDAR_SYNC_FAILED,
        "interview_calendar_sync_failed",
    ): NotificationEmailTemplate(
        subject="Interview calendar sync needs attention",
        text_body=(
            "Calendar delivery for an interview could not be completed "
            "automatically. Sign in to your hiring workspace to review the "
            "calendar status and retry it if appropriate."
        ),
    ),
}


def resolve_notification_email_template(
    *,
    event_type: NotificationEventType,
    template_key: str,
) -> NotificationEmailTemplate:
    """Return approved static copy for an exact event/template pair."""
    template = _TEMPLATES.get((event_type, template_key))
    if template is None:
        raise UnsupportedNotificationTemplateError(
            "Notification event and template key are not supported."
        )
    return template


def render_notification_email(
    *,
    notification_id: UUID,
    idempotency_key: str,
    recipient_email: str,
    event_type: str,
    template_key: str,
) -> EmailMessage:
    """Render approved static copy without embedding workflow or candidate data."""
    try:
        normalized_event_type = NotificationEventType(event_type)
    except ValueError as error:
        raise UnsupportedNotificationTemplateError(
            "Notification event and template key are not supported."
        ) from error

    template = resolve_notification_email_template(
        event_type=normalized_event_type,
        template_key=template_key,
    )
    return EmailMessage(
        notification_id=notification_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
        subject=template.subject,
        text_body=template.text_body,
    )


def render_calendar_sync_failure_email(
    *,
    notification_id: UUID,
    idempotency_key: str,
    recipient_email: str,
    interview_url: str,
) -> EmailMessage:
    """Render a terminal calendar failure alert with its authorized interview link."""
    template = resolve_notification_email_template(
        event_type=NotificationEventType.INTERVIEW_CALENDAR_SYNC_FAILED,
        template_key="interview_calendar_sync_failed",
    )
    return EmailMessage(
        notification_id=notification_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
        subject=template.subject,
        text_body=f"{template.text_body}\n\nReview interview: {interview_url}",
    )


def render_interview_notification_email(
    *,
    notification_id: UUID,
    idempotency_key: str,
    recipient_email: str,
    event_type: str,
    template_key: str,
    details: InterviewNotificationDetails,
) -> EmailMessage:
    """Render schedule details only from current, tenant-verified records."""
    try:
        normalized_event_type = NotificationEventType(event_type)
    except ValueError as error:
        raise UnsupportedNotificationTemplateError(
            "Notification event and template key are not supported."
        ) from error

    template = resolve_notification_email_template(
        event_type=normalized_event_type,
        template_key=template_key,
    )
    start_at = details.scheduled_start_at.astimezone(UTC)
    end_at = details.scheduled_end_at.astimezone(UTC)
    lines = [
        "Hello,",
        "",
        template.subject
        + (f" for {details.role_title}." if details.role_title else "."),
        "",
        "When: "
        f"{start_at.isoformat(timespec='minutes')} to "
        f"{end_at.isoformat(timespec='minutes')} (UTC)",
        f"Format: {details.interview_format or 'Not specified'}",
    ]
    if details.location:
        lines.append(f"Location: {details.location}")
    if (
        details.meeting_url
        and normalized_event_type is not NotificationEventType.INTERVIEW_CANCELLED
    ):
        lines.append(f"Join the interview: {details.meeting_url}")
    lines.append("")

    if details.is_candidate:
        if details.role_url:
            lines.extend((f"Job details: {details.role_url}", ""))
        lines.append("Keep this email for the interview schedule and joining details.")
    else:
        lines.append(f"View interview details: {details.interview_url}")

    return EmailMessage(
        notification_id=notification_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
        subject=template.subject,
        text_body="\n".join(lines),
    )


def render_action_item_digest_email(
    *,
    notification_id: UUID,
    idempotency_key: str,
    recipient_email: str,
    overdue_follow_up_count: int,
    overdue_onboarding_task_count: int,
    pending_feedback_count: int,
    frequency: NotificationDigestFrequency,
    web_app_base_url: str,
) -> EmailMessage:
    """Render a privacy-minimal digest with authenticated workspace links."""
    if (
        overdue_follow_up_count < 0
        or overdue_onboarding_task_count < 0
        or pending_feedback_count < 0
    ):
        raise ValueError("Digest counts cannot be negative.")

    base_url = web_app_base_url.rstrip("/")
    subject = (
        "Your weekly recruiting action items"
        if frequency is NotificationDigestFrequency.WEEKLY
        else "Your daily recruiting action items"
    )
    lines = [
        "Hello,",
        "",
        f"Here is your {frequency.value} recruiting action summary:",
        "",
    ]
    if overdue_follow_up_count:
        follow_up_word = "follow-up" if overdue_follow_up_count == 1 else "follow-ups"
        lines.append(
            f"- {overdue_follow_up_count} overdue {follow_up_word}: "
            f"{base_url}/dashboard/applications"
        )
    if overdue_onboarding_task_count:
        task_word = "task" if overdue_onboarding_task_count == 1 else "tasks"
        lines.append(
            f"- {overdue_onboarding_task_count} overdue onboarding {task_word}: "
            f"{base_url}/dashboard/onboarding"
        )
    if pending_feedback_count:
        feedback_word = "interview" if pending_feedback_count == 1 else "interviews"
        lines.append(
            f"- Feedback is pending for {pending_feedback_count} {feedback_word}: "
            f"{base_url}/dashboard/interviews"
        )
    lines.extend(("", "Sign in to your workspace to review and complete these actions."))

    return EmailMessage(
        notification_id=notification_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
        subject=subject,
        text_body="\n".join(lines),
    )
