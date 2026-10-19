"""Tenant-scoped follow-ups, onboarding, and interviewer dashboard alerts."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_follow_up import ApplicationFollowUp
from app.db.models.candidate import Candidate
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.interview_feedback import InterviewFeedback
from app.db.models.onboarding import OnboardingInstance, OnboardingTask
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidatePrivacyStatus,
)
from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskStatus,
)
from app.services.application_follow_up_errors import (
    ApplicationFollowUpAccessDeniedError,
)
from app.services.onboarding_documents import list_onboarding_document_review_queue

_FOLLOW_UP_READ_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)
_DOCUMENT_REVIEW_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})
_OPEN_APPLICATION_STATUSES = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
)
_FEEDBACK_APPLICATION_STATUSES = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
)
_ONBOARDING_TASK_DUE_SOON_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class NotificationActionItemRecord:
    """One unresolved follow-up, review, deadline, or feedback action."""

    id: str
    kind: Literal[
        "overdue_follow_up",
        "pending_interview_feedback",
        "overdue_onboarding_task",
        "due_soon_onboarding_task",
        "pending_onboarding_document_review",
    ]
    title: str
    candidate_name: str
    requisition_title: str
    due_at: datetime
    href: str
    application_id: UUID


async def list_notification_action_items(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> list[NotificationActionItemRecord]:
    """Return unresolved items for the caller, never tenant-wide reminders."""
    user = await session.scalar(
        select(User).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user is None:
        raise ApplicationFollowUpAccessDeniedError(
            "The caller does not have a workspace user identity."
        )

    now = datetime.now(UTC)
    items: list[NotificationActionItemRecord] = []

    if not context.roles.isdisjoint(_FOLLOW_UP_READ_ROLES):
        follow_up_rows = await session.execute(
            select(
                ApplicationFollowUp,
                Candidate.full_name,
                Requisition.title,
            )
            .join(
                Application,
                and_(
                    Application.id == ApplicationFollowUp.application_id,
                    Application.tenant_id == ApplicationFollowUp.tenant_id,
                ),
            )
            .join(
                Candidate,
                and_(
                    Candidate.id == Application.candidate_id,
                    Candidate.tenant_id == Application.tenant_id,
                ),
            )
            .join(
                Requisition,
                and_(
                    Requisition.id == Application.requisition_id,
                    Requisition.tenant_id == Application.tenant_id,
                ),
            )
            .where(
                ApplicationFollowUp.tenant_id == context.tenant_id,
                ApplicationFollowUp.completed_at.is_(None),
                ApplicationFollowUp.due_at <= now,
                Application.status.in_(_OPEN_APPLICATION_STATUSES),
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
                or_(
                    Application.assigned_to_user_id == user.id,
                    and_(
                        Application.assigned_to_user_id.is_(None),
                        ApplicationFollowUp.created_by_subject == context.subject,
                    ),
                ),
            )
            .order_by(ApplicationFollowUp.due_at, ApplicationFollowUp.id)
            .limit(50)
        )
        for follow_up, candidate_name, requisition_title in follow_up_rows.all():
            items.append(
                NotificationActionItemRecord(
                    id=f"follow-up:{follow_up.id}",
                    kind="overdue_follow_up",
                    title=follow_up.action,
                    candidate_name=candidate_name,
                    requisition_title=requisition_title,
                    due_at=follow_up.due_at,
                    href=f"/dashboard/applications/{follow_up.application_id}",
                    application_id=follow_up.application_id,
                )
            )

    feedback_rows = await session.execute(
        select(
            InterviewSession,
            Application.id,
            Candidate.full_name,
            Requisition.title,
        )
        .join(
            InterviewParticipant,
            and_(
                InterviewParticipant.interview_session_id == InterviewSession.id,
                InterviewParticipant.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .join(
            Application,
            and_(
                Application.id == InterviewSession.application_id,
                Application.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .join(
            Candidate,
            and_(
                Candidate.id == Application.candidate_id,
                Candidate.tenant_id == Application.tenant_id,
            ),
        )
        .join(
            Requisition,
            and_(
                Requisition.id == Application.requisition_id,
                Requisition.tenant_id == Application.tenant_id,
            ),
        )
        .outerjoin(
            InterviewFeedback,
            and_(
                InterviewFeedback.interview_session_id == InterviewSession.id,
                InterviewFeedback.interviewer_user_id == user.id,
                InterviewFeedback.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .where(
            InterviewSession.tenant_id == context.tenant_id,
            InterviewSession.status.in_(
                (InterviewSessionStatus.SCHEDULED, InterviewSessionStatus.COMPLETED)
            ),
            InterviewSession.scheduled_end_at <= now,
            InterviewParticipant.user_id == user.id,
            InterviewParticipant.role == InterviewParticipantRole.INTERVIEWER,
            Application.status.in_(_FEEDBACK_APPLICATION_STATUSES),
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            or_(
                InterviewFeedback.id.is_(None),
                InterviewFeedback.status != InterviewFeedbackStatus.SUBMITTED,
            ),
        )
        .order_by(InterviewSession.scheduled_end_at, InterviewSession.id)
        .limit(50)
    )
    for interview, application_id, candidate_name, requisition_title in feedback_rows.all():
        items.append(
            NotificationActionItemRecord(
                id=f"interview-feedback:{interview.id}",
                kind="pending_interview_feedback",
                title="Submit interview feedback",
                candidate_name=candidate_name,
                requisition_title=requisition_title,
                due_at=interview.scheduled_end_at,
                href=f"/dashboard/interviews/{interview.id}",
                application_id=application_id,
            )
        )

    onboarding_rows = await session.execute(
        select(
            OnboardingTask,
            Application.id,
            Candidate.full_name,
            Requisition.title,
        )
        .join(
            OnboardingInstance,
            and_(
                OnboardingInstance.id == OnboardingTask.onboarding_instance_id,
                OnboardingInstance.tenant_id == OnboardingTask.tenant_id,
            ),
        )
        .join(
            Application,
            and_(
                Application.id == OnboardingInstance.application_id,
                Application.tenant_id == OnboardingInstance.tenant_id,
            ),
        )
        .join(
            Candidate,
            and_(
                Candidate.id == Application.candidate_id,
                Candidate.tenant_id == Application.tenant_id,
            ),
        )
        .join(
            Requisition,
            and_(
                Requisition.id == Application.requisition_id,
                Requisition.tenant_id == Application.tenant_id,
            ),
        )
        .where(
            OnboardingTask.tenant_id == context.tenant_id,
            OnboardingTask.assignee_user_id == user.id,
            OnboardingTask.due_at <= now + _ONBOARDING_TASK_DUE_SOON_WINDOW,
            OnboardingTask.status.in_(
                (
                    OnboardingTaskStatus.NOT_STARTED,
                    OnboardingTaskStatus.IN_PROGRESS,
                    OnboardingTaskStatus.BLOCKED,
                )
            ),
            OnboardingInstance.status == OnboardingInstanceStatus.ACTIVE,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
        )
        .order_by(OnboardingTask.due_at, OnboardingTask.id)
        .limit(50)
    )
    for task, application_id, candidate_name, requisition_title in onboarding_rows.all():
        if task.due_at is None:
            continue
        items.append(
            NotificationActionItemRecord(
                id=f"onboarding-task:{task.id}",
                kind=(
                    "overdue_onboarding_task"
                    if task.due_at <= now
                    else "due_soon_onboarding_task"
                ),
                title=task.title,
                candidate_name=candidate_name,
                requisition_title=requisition_title,
                due_at=task.due_at,
                href=f"/dashboard/applications/{application_id}",
                application_id=application_id,
            )
        )

    if not context.roles.isdisjoint(_DOCUMENT_REVIEW_ROLES):
        review_items, _ = await list_onboarding_document_review_queue(
            session,
            context=context,
            page=1,
            limit=50,
        )
        items.extend(
            NotificationActionItemRecord(
                id=f"onboarding-document-review:{review_item.document.id}",
                kind="pending_onboarding_document_review",
                title=review_item.task_title,
                candidate_name=review_item.employee_name,
                requisition_title=review_item.job_title,
                due_at=(
                    review_item.document.uploaded_at
                    or review_item.document.created_at
                ),
                href="/dashboard/onboarding/document-reviews",
                application_id=review_item.application_id,
            )
            for review_item in review_items
        )

    return sorted(items, key=lambda item: item.due_at)[:100]
