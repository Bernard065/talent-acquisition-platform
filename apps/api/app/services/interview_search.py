"""Tenant-scoped, calendar-oriented interview schedule read models."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.domains.interviews.enums import InterviewSessionStatus
from app.services.interview_search_errors import (
    InterviewSearchAccessDeniedError,
    InvalidInterviewSearchCursorError,
)

_BROAD_INTERVIEW_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)


@dataclass(frozen=True, slots=True)
class InterviewSearchFilters:
    """Safe filters for one tenant's interview calendar."""

    application_id: UUID | None = None
    status: InterviewSessionStatus | None = None
    participant_user_id: UUID | None = None
    scheduled_after: datetime | None = None
    scheduled_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class InterviewSearchPage:
    """Cursor-paginated interview schedule results."""

    items: list[InterviewSession]
    next_cursor: str | None


def _normalize_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> datetime:
    """Require timezone-aware schedule range filters."""
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a UTC offset.")

    return value.astimezone(UTC)


def _encode_cursor(session: InterviewSession) -> str:
    """Encode the final scheduled session as opaque cursor state."""
    scheduled_start_at = session.scheduled_start_at
    if scheduled_start_at.tzinfo is None:
        scheduled_start_at = scheduled_start_at.replace(tzinfo=UTC)

    payload = json.dumps(
        {
            "scheduled_start_at": scheduled_start_at.astimezone(UTC).isoformat(),
            "id": str(session.id),
        },
        separators=(",", ":"),
    ).encode("utf-8")

    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode and validate opaque interview calendar pagination state."""
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor))
        scheduled_start_at = datetime.fromisoformat(
            payload["scheduled_start_at"]
        )
        interview_session_id = UUID(payload["id"])

        if scheduled_start_at.tzinfo is None:
            raise ValueError("Cursor timestamp must include a timezone.")

        return scheduled_start_at.astimezone(UTC), interview_session_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise InvalidInterviewSearchCursorError(
            "Invalid interview search cursor."
        ) from error


async def _resolve_interviewer_user_id(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> UUID:
    """Resolve an interviewer JWT subject to its tenant-local user identity."""
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user_id is None:
        raise InterviewSearchAccessDeniedError(
            "Caller has no internal interview-user identity."
        )

    return user_id


async def _authorized_participant_filter(
    session: AsyncSession,
    *,
    context: TenantContext,
    requested_participant_user_id: UUID | None,
) -> UUID | None:
    """
    Return an enforced participant filter for interviewer-only access.

    Broad operational roles may inspect a tenant calendar and optionally filter
    by any tenant participant. Interviewers may inspect only their own sessions.
    """
    if not context.roles.isdisjoint(_BROAD_INTERVIEW_READ_ROLES):
        return requested_participant_user_id

    if Role.INTERVIEWER not in context.roles:
        raise InterviewSearchAccessDeniedError(
            "Caller is not permitted to view interview schedules."
        )

    interviewer_user_id = await _resolve_interviewer_user_id(
        session,
        context=context,
    )

    if (
        requested_participant_user_id is not None
        and requested_participant_user_id != interviewer_user_id
    ):
        raise InterviewSearchAccessDeniedError(
            "Interviewers may view only their own sessions."
        )

    return interviewer_user_id


async def search_interviews(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: InterviewSearchFilters | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> InterviewSearchPage:
    """Return authorized tenant interview sessions with stable keyset paging."""
    if filters is None:
        filters = InterviewSearchFilters()

    if not 1 <= limit <= 100:
        raise ValueError("Interview search limit must be between 1 and 100.")

    if (
        filters.scheduled_after is not None
        and filters.scheduled_before is not None
        and _normalize_aware_datetime(
            filters.scheduled_after,
            field_name="scheduled_after",
        )
        > _normalize_aware_datetime(
            filters.scheduled_before,
            field_name="scheduled_before",
        )
    ):
        raise ValueError(
            "scheduled_after must not be later than scheduled_before."
        )

    participant_user_id = await _authorized_participant_filter(
        session,
        context=context,
        requested_participant_user_id=filters.participant_user_id,
    )

    statement = select(InterviewSession).where(
        InterviewSession.tenant_id == context.tenant_id
    )

    if participant_user_id is not None:
        statement = statement.join(
            InterviewParticipant,
            InterviewParticipant.interview_session_id == InterviewSession.id,
        ).where(
            InterviewParticipant.tenant_id == context.tenant_id,
            InterviewParticipant.user_id == participant_user_id,
        )

    if filters.application_id is not None:
        statement = statement.where(
            InterviewSession.application_id == filters.application_id
        )

    if filters.status is not None:
        statement = statement.where(InterviewSession.status == filters.status)

    if filters.scheduled_after is not None:
        statement = statement.where(
            InterviewSession.scheduled_start_at
            >= _normalize_aware_datetime(
                filters.scheduled_after,
                field_name="scheduled_after",
            )
        )

    if filters.scheduled_before is not None:
        statement = statement.where(
            InterviewSession.scheduled_start_at
            <= _normalize_aware_datetime(
                filters.scheduled_before,
                field_name="scheduled_before",
            )
        )

    if cursor is not None:
        cursor_start_at, cursor_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                InterviewSession.scheduled_start_at < cursor_start_at,
                and_(
                    InterviewSession.scheduled_start_at == cursor_start_at,
                    InterviewSession.id < cursor_id,
                ),
            )
        )

    sessions = list(
        await session.scalars(
            statement.order_by(
                InterviewSession.scheduled_start_at.desc(),
                InterviewSession.id.desc(),
            ).limit(limit + 1)
        )
    )

    has_next_page = len(sessions) > limit
    items = sessions[:limit]

    return InterviewSearchPage(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if has_next_page else None,
    )
