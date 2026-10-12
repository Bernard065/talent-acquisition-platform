"""Queue interview schedule email notifications through the transactional outbox."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.application import Application
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.domains.interviews.enums import InterviewParticipantRole
from app.domains.notifications.enums import NotificationEventType
from app.services.notification_publishing import enqueue_notification_request

_TEMPLATE_KEYS = {
    NotificationEventType.INTERVIEW_SCHEDULED: "interview_scheduled",
    NotificationEventType.INTERVIEW_RESCHEDULED: "interview_rescheduled",
    NotificationEventType.INTERVIEW_CANCELLED: "interview_cancelled",
}


async def enqueue_interview_notifications(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session: InterviewSession,
    event_type: NotificationEventType,
) -> None:
    """Queue candidate and participant emails atomically with the change."""
    template_key = _TEMPLATE_KEYS[event_type]
    candidate_id = await session.scalar(
        select(Application.candidate_id).where(
            Application.id == interview_session.application_id,
            Application.tenant_id == context.tenant_id,
        )
    )
    if candidate_id is not None:
        enqueue_notification_request(
            session,
            context=context,
            recipient_candidate_id=candidate_id,
            notification_event_type=event_type,
            entity_type="interview_session",
            entity_id=interview_session.id,
            template_key=template_key,
            occurrence_key=interview_session.version,
        )

    participant_ids = await session.scalars(
        select(InterviewParticipant.user_id).where(
            InterviewParticipant.tenant_id == context.tenant_id,
            InterviewParticipant.interview_session_id == interview_session.id,
            InterviewParticipant.role == InterviewParticipantRole.INTERVIEWER,
        )
    )
    for participant_id in participant_ids:
        enqueue_notification_request(
            session,
            context=context,
            recipient_user_id=participant_id,
            notification_event_type=event_type,
            entity_type="interview_session",
            entity_id=interview_session.id,
            template_key=template_key,
            occurrence_key=interview_session.version,
        )

