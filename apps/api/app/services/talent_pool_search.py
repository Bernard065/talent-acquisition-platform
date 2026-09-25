"""Tenant-scoped search over candidates with current purpose consent."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_talent_pool_consent import (
    CandidateTalentPoolConsentEvent,
)
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolConsentEventType,
)
from app.services.recruiting_search import (
    decode_search_cursor,
    encode_search_cursor,
)
from app.services.recruiting_search_errors import InvalidRecruitingSearchCursorError
from app.services.talent_pool_search_errors import (
    InvalidTalentPoolSearchCursorError,
    TalentPoolSearchAccessDeniedError,
)

_TALENT_POOL_READ_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)


@dataclass(frozen=True, slots=True)
class TalentPoolSearchFilters:
    """Bounded filters supported by talent-pool discovery."""

    query: str | None = None
    source: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class TalentPoolSearchItem:
    """Candidate plus the active immutable consent evidence that qualifies it."""

    candidate: Candidate
    consent_event: CandidateTalentPoolConsentEvent


@dataclass(frozen=True, slots=True)
class TalentPoolSearchPage:
    """Stable cursor-paginated page of consented candidates."""

    items: list[TalentPoolSearchItem]
    next_cursor: str | None


def _require_talent_pool_read_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_TALENT_POOL_READ_ROLES):
        raise TalentPoolSearchAccessDeniedError(
            "Caller is not permitted to search the talent pool."
        )


def _contains_pattern(value: str) -> str:
    """Escape SQL LIKE wildcards so search terms are interpreted literally."""
    escaped = (
        value.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


async def search_consented_talent_pool(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: TalentPoolSearchFilters | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> TalentPoolSearchPage:
    """Return only active, tenant-owned candidates with latest active consent.

    A consent grant or renewal qualifies a candidate only when no later consent
    event exists. Tenant and privacy-state constraints are part of the query,
    so callers cannot enumerate candidates from another tenant or retrieve
    erased/erasure-pending profiles through this read model.
    """
    _require_talent_pool_read_role(context)
    filters = filters or TalentPoolSearchFilters()
    if not 1 <= limit <= 100:
        raise ValueError("Talent-pool search limit must be between 1 and 100.")

    statement = _active_consented_candidate_statement(context.tenant_id)

    if filters.query is not None and filters.query.strip():
        pattern = _contains_pattern(filters.query)
        statement = statement.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
            )
        )

    if filters.source is not None and filters.source.strip():
        statement = statement.where(Candidate.source == filters.source.strip())

    if filters.location is not None and filters.location.strip():
        statement = statement.where(
            Candidate.location.ilike(_contains_pattern(filters.location), escape="\\")
        )

    if cursor is not None:
        try:
            cursor_created_at, cursor_id = decode_search_cursor(cursor)
        except InvalidRecruitingSearchCursorError as error:
            raise InvalidTalentPoolSearchCursorError(
                "Invalid talent-pool search cursor."
            ) from error
        statement = statement.where(
            or_(
                Candidate.created_at < cursor_created_at,
                and_(
                    Candidate.created_at == cursor_created_at,
                    Candidate.id < cursor_id,
                ),
            )
        )

    rows = list(
        (await session.execute(
            statement.order_by(Candidate.created_at.desc(), Candidate.id.desc())
            .limit(limit + 1)
        )).all()
    )
    has_next_page = len(rows) > limit
    items = [TalentPoolSearchItem(candidate=row[0], consent_event=row[1]) for row in rows[:limit]]

    return TalentPoolSearchPage(
        items=items,
        next_cursor=(
            encode_search_cursor(
                timestamp=items[-1].candidate.created_at,
                record_id=items[-1].candidate.id,
            )
            if has_next_page
            else None
        ),
    )


def _active_consented_candidate_statement(
    tenant_id: UUID,
) -> Select[tuple[Candidate, CandidateTalentPoolConsentEvent]]:
    """Build a query anchored to each candidate's latest consent event."""
    consent_event = aliased(CandidateTalentPoolConsentEvent)
    newer_event = aliased(CandidateTalentPoolConsentEvent)
    return (
        select(Candidate, consent_event)
        .join(
            consent_event,
            and_(
                consent_event.tenant_id == Candidate.tenant_id,
                consent_event.candidate_id == Candidate.id,
            ),
        )
        .where(
            Candidate.tenant_id == tenant_id,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            consent_event.event_type.in_(
                (
                    CandidateTalentPoolConsentEventType.GRANTED,
                    CandidateTalentPoolConsentEventType.RENEWED,
                )
            ),
            ~exists(
                select(1).where(
                    newer_event.tenant_id == consent_event.tenant_id,
                    newer_event.candidate_id == consent_event.candidate_id,
                    newer_event.event_version > consent_event.event_version,
                )
            ),
        )
    )
