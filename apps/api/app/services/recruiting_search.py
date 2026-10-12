"""Tenant-scoped, cursor-paginated recruiter candidate and application search."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import User
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
    query: str | None = None
    status: ApplicationStatus | None = None
    applied_after: datetime | None = None
    applied_before: datetime | None = None
    assigned_to_subject: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateSearchPage:
    """Cursor-paginated candidate search results."""

    items: list[Candidate]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CandidateFilterOptions:
    """Distinct tenant-wide filter values for candidate discovery."""

    sources: list[str]
    locations: list[str]


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
    assigned_to_display_name: str | None


@dataclass(frozen=True, slots=True)
class ApplicationPipelinePage:
    """Cursor-paginated application summaries for pipeline views."""

    items: list[ApplicationPipelineRecord]
    next_cursor: str | None
    stage_counts: dict[ApplicationStatus, int]


@dataclass(slots=True)
class ApplicationPipelineJobSummary:
    """Tenant-safe application counts for one requisition."""

    requisition_id: UUID
    requisition_title: str
    total_count: int
    stage_counts: dict[ApplicationStatus, int]


@dataclass(frozen=True, slots=True)
class ApplicationPipelineSummary:
    """Filtered pipeline totals grouped by requisition."""

    total_count: int
    stage_counts: dict[ApplicationStatus, int]
    jobs: list[ApplicationPipelineJobSummary]


def _require_recruiting_read_role(context: TenantContext) -> None:
    """Protect candidate PII from roles without broad recruiting access."""
    if context.roles.isdisjoint(_RECRUITING_READ_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to search recruiting records."
        )


async def get_candidate_filter_options(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> CandidateFilterOptions:
    """Return distinct filter values across active candidates in this tenant."""
    _require_recruiting_read_role(context)
    base_conditions = (
        Candidate.tenant_id == context.tenant_id,
        Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
    )
    sources = list(
        await session.scalars(
            select(Candidate.source)
            .where(*base_conditions)
            .distinct()
            .order_by(Candidate.source)
        )
    )
    locations = list(
        await session.scalars(
            select(Candidate.location)
            .where(*base_conditions, Candidate.location.is_not(None))
            .distinct()
            .order_by(Candidate.location)
        )
    )
    return CandidateFilterOptions(
        sources=sources,
        locations=[location for location in locations if location is not None],
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

    _validate_application_search_filters(filters)

    statement = _application_search_statement(context=context, filters=filters)

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


def _validate_application_search_filters(filters: ApplicationSearchFilters) -> None:
    """Validate the date bounds shared by application searches and summaries."""
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


async def summarize_application_pipeline(
    session: AsyncSession,
    *,
    context: TenantContext,
    filters: ApplicationSearchFilters | None = None,
) -> ApplicationPipelineSummary:
    """Return tenant-scoped application totals grouped by job and stage."""
    _require_recruiting_read_role(context)
    normalized_filters = filters or ApplicationSearchFilters()
    _validate_application_search_filters(normalized_filters)

    filtered_applications = _application_search_statement(
        context=context,
        filters=normalized_filters,
    ).with_only_columns(
        Application.requisition_id,
        Application.status,
    ).order_by(None).subquery()

    rows = await session.execute(
        select(
            filtered_applications.c.requisition_id,
            Requisition.title,
            filtered_applications.c.status,
            count(),
        )
        .join(
            Requisition,
            and_(
                Requisition.id == filtered_applications.c.requisition_id,
                Requisition.tenant_id == context.tenant_id,
            ),
        )
        .group_by(
            filtered_applications.c.requisition_id,
            Requisition.title,
            filtered_applications.c.status,
        )
        .order_by(Requisition.title, filtered_applications.c.requisition_id)
    )

    jobs: dict[UUID, ApplicationPipelineJobSummary] = {}
    total_stage_counts = {application_status: 0 for application_status in ApplicationStatus}
    for requisition_id, requisition_title, application_status, application_count in rows:
        job = jobs.get(requisition_id)
        if job is None:
            job = ApplicationPipelineJobSummary(
                requisition_id=requisition_id,
                requisition_title=requisition_title,
                total_count=0,
                stage_counts={status: 0 for status in ApplicationStatus},
            )
            jobs[requisition_id] = job
        job.stage_counts[application_status] = application_count
        job.total_count += application_count
        total_stage_counts[application_status] += application_count

    return ApplicationPipelineSummary(
        total_count=sum(total_stage_counts.values()),
        stage_counts=total_stage_counts,
        jobs=list(jobs.values()),
    )


def _application_search_statement(
    *,
    context: TenantContext,
    filters: ApplicationSearchFilters,
) -> Select[tuple[Application]]:
    """Build the tenant-scoped application query shared by list and count reads."""
    statement = select(Application).where(Application.tenant_id == context.tenant_id)

    if filters.query is not None and filters.query.strip():
        pattern = _contains_pattern(filters.query)
        statement = (
            statement.join(
                Candidate,
                and_(
                    Candidate.id == Application.candidate_id,
                    Candidate.tenant_id == context.tenant_id,
                ),
            )
            .join(
                Requisition,
                and_(
                    Requisition.id == Application.requisition_id,
                    Requisition.tenant_id == context.tenant_id,
                ),
            )
            .where(
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
                or_(
                    Candidate.full_name.ilike(pattern, escape="\\"),
                    Candidate.email.ilike(pattern, escape="\\"),
                    Requisition.title.ilike(pattern, escape="\\"),
                ),
            )
        )

    if filters.requisition_id is not None:
        statement = statement.where(
            Application.requisition_id == filters.requisition_id
        )

    if filters.candidate_id is not None:
        statement = statement.where(
            Application.candidate_id == filters.candidate_id
        )

    if filters.assigned_to_subject is not None:
        assigned_user_id = (
            select(User.id)
            .where(
                User.tenant_id == context.tenant_id,
                User.external_subject == filters.assigned_to_subject,
            )
            .scalar_subquery()
        )
        statement = statement.where(
            Application.assigned_to_user_id == assigned_user_id
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

    return statement


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
    if filters is None:
        filters = ApplicationSearchFilters()
    filtered_applications = _application_search_statement(
        context=context,
        filters=filters,
    ).with_only_columns(Application.id, Application.status).order_by(None).subquery()
    count_rows = await session.execute(
        select(filtered_applications.c.status, count())
        .group_by(filtered_applications.c.status)
    )
    stage_counts = {application_status: 0 for application_status in ApplicationStatus}
    stage_counts.update({status: count for status, count in count_rows})
    if not page.items:
        return ApplicationPipelinePage(
            items=[],
            next_cursor=page.next_cursor,
            stage_counts=stage_counts,
        )

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

    assigned_user_ids = {
        application.assigned_to_user_id
        for application in page.items
        if application.assigned_to_user_id is not None
    }
    assigned_users: dict[UUID, str] = {}
    if assigned_user_ids:
        assigned_user_rows = await session.execute(
            select(User.id, User.display_name).where(
                User.tenant_id == context.tenant_id,
                User.id.in_(assigned_user_ids),
            )
        )
        assigned_users = {
            user_id: display_name for user_id, display_name in assigned_user_rows
        }

    records: list[ApplicationPipelineRecord] = []
    for application in page.items:
        candidate = candidates.get(application.candidate_id)
        requisition_title = requisitions.get(application.requisition_id)
        if candidate is not None and candidate[2] is CandidatePrivacyStatus.ACTIVE:
            candidate_name = candidate[0]
            candidate_email = candidate[1]
        else:
            candidate_name = "Candidate unavailable"
            candidate_email = None
        records.append(
            ApplicationPipelineRecord(
                application=application,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                requisition_title=requisition_title or "Job unavailable",
                assigned_to_display_name=assigned_users.get(
                    application.assigned_to_user_id
                )
                if application.assigned_to_user_id is not None
                else None,
            )
        )

    return ApplicationPipelinePage(
        items=records,
        next_cursor=page.next_cursor,
        stage_counts=stage_counts,
    )
