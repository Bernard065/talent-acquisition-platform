"""Tenant-scoped, cursor-paginated recruiter candidate and application search."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.services.candidate_errors import CandidateAccessDeniedError
from app.services.recruiting_search_errors import (
    InvalidRecruitingSearchCursorError,
)

_RECRUITING_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)


@dataclass(frozen=True, slots=True)
class CandidateSearchFilters:
    """Safe filters for tenant-scoped candidate discovery."""

    query: str | None = None
    source: str | None = None
    location: str | None = None
    consent_status: CandidateConsentStatus | None = None


@dataclass(frozen=True, slots=True)
class ApplicationSearchFilters:
    """Safe filters for tenant-scoped application discovery."""

    requisition_id: UUID | None = None
    candidate_id: UUID | None = None
    status: ApplicationStatus | None = None
    applied_after: datetime | None = None
    applied_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class CandidateSearchPage:
    """Cursor-paginated candidate search results."""

    items: list[Candidate]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ApplicationSearchPage:
    """Cursor-paginated application search results."""

    items: list[Application]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ApplicationPipelineRecord:
    """One application with the minimal recruiter-facing card details."""

    application: Application
    candidate_name: str
    candidate_email: str | None
    requisition_title: str


@dataclass(frozen=True, slots=True)
class ApplicationPipelinePage:
    """Cursor-paginated application summaries for pipeline views."""

    items: list[ApplicationPipelineRecord]
    next_cursor: str | None


def _require_recruiting_read_role(context: TenantContext) -> None:
    """Protect candidate PII from roles without broad recruiting access."""
    if context.roles.isdisjoint(_RECRUITING_READ_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to search recruiting records."
        )


def _normalize_aware_datetime(value: datetime, *, field_name: str) -> datetime:
    """Require UTC-aware filter values and normalize equivalent offsets."""
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a UTC offset.")

    return value.astimezone(UTC)


def _contains_pattern(value: str) -> str:
    """Build a literal case-insensitive SQL LIKE pattern safely."""
    escaped = (
        value.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def encode_search_cursor(*, timestamp: datetime, record_id: UUID) -> str:
    """Encode a final page record as opaque keyset pagination state."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    payload = json.dumps(
        {
            "timestamp": timestamp.astimezone(UTC).isoformat(),
            "id": str(record_id),
        },
        separators=(",", ":"),
    ).encode("utf-8")

    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_search_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode and validate opaque recruiter-search pagination state."""
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor))
        timestamp = datetime.fromisoformat(payload["timestamp"])
        record_id = UUID(payload["id"])

        if timestamp.tzinfo is None:
            raise ValueError("Cursor timestamp must include a timezone.")

        return timestamp.astimezone(UTC), record_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise InvalidRecruitingSearchCursorError(
            "Invalid recruiter search cursor."
        ) from error


async def search_candidates(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: CandidateSearchFilters | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> CandidateSearchPage:
    """Search tenant candidates without crossing the candidate-data boundary."""
    _require_recruiting_read_role(context)
    if filters is None:
        filters = CandidateSearchFilters()

    if not 1 <= limit <= 100:
        raise ValueError("Candidate search limit must be between 1 and 100.")

    statement = select(Candidate).where(
        Candidate.tenant_id == context.tenant_id,
        Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
    )

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
            Candidate.location.ilike(
                _contains_pattern(filters.location),
                escape="\\",
            )
        )

    if filters.consent_status is not None:
        statement = statement.where(
            Candidate.consent_status == filters.consent_status
        )

    if cursor is not None:
        cursor_created_at, cursor_id = decode_search_cursor(cursor)
        statement = statement.where(
            or_(
                Candidate.created_at < cursor_created_at,
                and_(
                    Candidate.created_at == cursor_created_at,
                    Candidate.id < cursor_id,
                ),
            )
        )

    candidates = list(
        await session.scalars(
            statement.order_by(
                Candidate.created_at.desc(),
                Candidate.id.desc(),
            ).limit(limit + 1)
        )
    )

    has_next_page = len(candidates) > limit
    items = candidates[:limit]

    return CandidateSearchPage(
        items=items,
        next_cursor=(
            encode_search_cursor(
                timestamp=items[-1].created_at,
                record_id=items[-1].id,
            )
            if has_next_page
            else None
        ),
    )


async def search_applications(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: ApplicationSearchFilters | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> ApplicationSearchPage:
    """Search tenant applications with stable ordering and bounded filters."""
    _require_recruiting_read_role(context)
    if filters is None:
        filters = ApplicationSearchFilters()

    if not 1 <= limit <= 100:
        raise ValueError("Application search limit must be between 1 and 100.")

    if (
        filters.applied_after is not None
        and filters.applied_before is not None
        and _normalize_aware_datetime(
            filters.applied_after,
            field_name="applied_after",
        )
        > _normalize_aware_datetime(
            filters.applied_before,
            field_name="applied_before",
        )
    ):
        raise ValueError("applied_after must not be later than applied_before.")

    statement = select(Application).where(
        Application.tenant_id == context.tenant_id
    )

    if filters.requisition_id is not None:
        statement = statement.where(
            Application.requisition_id == filters.requisition_id
        )

    if filters.candidate_id is not None:
        statement = statement.where(
            Application.candidate_id == filters.candidate_id
        )

    if filters.status is not None:
        statement = statement.where(Application.status == filters.status)

    if filters.applied_after is not None:
        statement = statement.where(
            Application.applied_at
            >= _normalize_aware_datetime(
                filters.applied_after,
                field_name="applied_after",
            )
        )

    if filters.applied_before is not None:
        statement = statement.where(
            Application.applied_at
            <= _normalize_aware_datetime(
                filters.applied_before,
                field_name="applied_before",
            )
        )

    if cursor is not None:
        cursor_applied_at, cursor_id = decode_search_cursor(cursor)
        statement = statement.where(
            or_(
                Application.applied_at < cursor_applied_at,
                and_(
                    Application.applied_at == cursor_applied_at,
                    Application.id < cursor_id,
                ),
            )
        )

    applications = list(
        await session.scalars(
            statement.order_by(
                Application.applied_at.desc(),
                Application.id.desc(),
            ).limit(limit + 1)
        )
    )

    has_next_page = len(applications) > limit
    items = applications[:limit]

    return ApplicationSearchPage(
        items=items,
        next_cursor=(
            encode_search_cursor(
                timestamp=items[-1].applied_at,
                record_id=items[-1].id,
            )
            if has_next_page
            else None
        ),
    )


async def search_application_pipeline(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: ApplicationSearchFilters | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> ApplicationPipelinePage:
    """Search applications and hydrate card labels in two bounded queries."""

    page = await search_applications(
        session,
        context=context,
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    if not page.items:
        return ApplicationPipelinePage(items=[], next_cursor=page.next_cursor)

    candidate_ids = {application.candidate_id for application in page.items}
    requisition_ids = {application.requisition_id for application in page.items}

    candidate_rows = await session.execute(
        select(
            Candidate.id,
            Candidate.full_name,
            Candidate.email,
            Candidate.privacy_status,
        ).where(
            Candidate.tenant_id == context.tenant_id,
            Candidate.id.in_(candidate_ids),
        )
    )
    candidates = {
        candidate_id: (name, email, privacy_status)
        for candidate_id, name, email, privacy_status in candidate_rows
    }

    requisition_rows = await session.execute(
        select(Requisition.id, Requisition.title).where(
            Requisition.tenant_id == context.tenant_id,
            Requisition.id.in_(requisition_ids),
        )
    )
    requisitions = {
        requisition_id: title for requisition_id, title in requisition_rows
    }

    records: list[ApplicationPipelineRecord] = []
    for application in page.items:
        candidate = candidates.get(application.candidate_id)
        requisition_title = requisitions.get(application.requisition_id)
        candidate_is_active = (
            candidate is not None and candidate[2] is CandidatePrivacyStatus.ACTIVE
        )
        records.append(
            ApplicationPipelineRecord(
                application=application,
                candidate_name=(
                    candidate[0] if candidate_is_active else "Candidate unavailable"
                ),
                candidate_email=(candidate[1] if candidate_is_active else None),
                requisition_title=requisition_title or "Job unavailable",
            )
        )

    return ApplicationPipelinePage(items=records, next_cursor=page.next_cursor)
