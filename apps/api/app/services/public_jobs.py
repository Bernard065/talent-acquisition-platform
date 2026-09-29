"""Anonymous, read-only discovery of currently public job postings."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import EmploymentType, JobPostingStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.public_job_errors import (
    InvalidPublicJobCursorError,
    PublicJobNotFoundError,
)


@dataclass(frozen=True, slots=True)
class PublicJobPage:
    """One cursor-paginated page of candidate-visible job postings."""

    items: list[JobPosting]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PublicJobPageDetail:
    """Public posting and employer display name needed by job-detail pages."""

    posting: JobPosting
    employer_name: str


@dataclass(frozen=True, slots=True)
class PublicJobSitemapEntry:
    """Public URL metadata for one currently visible posting."""

    public_id: UUID
    slug: str
    updated_at: datetime


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _public_visibility_conditions(now: datetime) -> ColumnElement[bool]:
    """Return conditions that make a posting safe to expose anonymously."""
    return and_(
        JobPosting.status == JobPostingStatus.PUBLISHED,
        JobPosting.published_at.is_not(None),
        or_(
            JobPosting.expires_at.is_(None),
            JobPosting.expires_at > now,
        ),
        Requisition.status == RequisitionStatus.OPEN,
    )


def _encode_cursor(posting: JobPosting) -> str:
    """Encode the final ordered posting as an opaque public cursor."""
    if posting.published_at is None:
        raise ValueError("Published job posting requires published_at.")

    published_at = posting.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)

    payload = json.dumps(
        {
            "published_at": published_at.isoformat(),
            "public_id": str(posting.public_id),
        },
        separators=(",", ":"),
    ).encode("utf-8")

    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode and validate an opaque public-job cursor."""
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor))
        published_at = datetime.fromisoformat(payload["published_at"])
        public_id = UUID(payload["public_id"])

        if published_at.tzinfo is None:
            raise ValueError("Cursor timestamp must include a timezone.")

        return published_at, public_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise InvalidPublicJobCursorError(
            "Invalid public job cursor."
        ) from error


async def list_public_jobs(
    session: AsyncSession,
    *,
    limit: int = 20,
    cursor: str | None = None,
    query: str | None = None,
    location: str | None = None,
    department: str | None = None,
    employment_type: EmploymentType | None = None,
) -> PublicJobPage:
    """Return only currently visible jobs using stable keyset pagination."""
    if not 1 <= limit <= 50:
        raise ValueError("Public job limit must be between 1 and 50.")

    now = _now()
    statement = (
        select(JobPosting)
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .where(_public_visibility_conditions(now))
    )

    if query is not None and query.strip():
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                JobPosting.title.ilike(pattern),
                JobPosting.department.ilike(pattern),
                JobPosting.location.ilike(pattern),
            )
        )

    if location is not None and location.strip():
        statement = statement.where(
            JobPosting.location.ilike(f"%{location.strip()}%")
        )

    if department is not None and department.strip():
        statement = statement.where(
            JobPosting.department.ilike(f"%{department.strip()}%")
        )

    if employment_type is not None:
        statement = statement.where(
            JobPosting.employment_type == employment_type
        )

    if cursor is not None:
        cursor_published_at, cursor_public_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                JobPosting.published_at < cursor_published_at,
                and_(
                    JobPosting.published_at == cursor_published_at,
                    JobPosting.public_id < cursor_public_id,
                ),
            )
        )

    postings = list(
        await session.scalars(
            statement.order_by(
                JobPosting.published_at.desc(),
                JobPosting.public_id.desc(),
            ).limit(limit + 1)
        )
    )

    has_next_page = len(postings) > limit
    items = postings[:limit]

    return PublicJobPage(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if has_next_page else None,
    )


async def get_public_job(
    session: AsyncSession,
    *,
    public_id: UUID,
) -> JobPosting:
    """Return a posting only when it is currently eligible for public display."""
    posting = await session.scalar(
        select(JobPosting)
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .where(
            JobPosting.public_id == public_id,
            _public_visibility_conditions(_now()),
        )
    )

    if posting is None:
        raise PublicJobNotFoundError("Public job was not found.")

    return posting


async def get_public_job_page_detail(
    session: AsyncSession,
    *,
    public_id: UUID,
) -> PublicJobPageDetail:
    """Load a currently visible posting with its tenant's public employer name."""
    result = await session.execute(
        select(JobPosting, Tenant.name)
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .join(Tenant, Tenant.id == JobPosting.tenant_id)
        .where(
            JobPosting.public_id == public_id,
            _public_visibility_conditions(_now()),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise PublicJobNotFoundError("Public job was not found.")

    posting, employer_name = row
    return PublicJobPageDetail(posting=posting, employer_name=employer_name)


async def list_public_job_sitemap_entries(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 40_000,
) -> list[PublicJobSitemapEntry]:
    """List a bounded, stable slice of currently visible sitemap entries."""
    if offset < 0 or not 1 <= limit <= 50_000:
        raise ValueError("Invalid sitemap offset or limit.")

    rows = await session.execute(
        select(JobPosting.public_id, JobPosting.slug, JobPosting.updated_at)
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .where(_public_visibility_conditions(_now()))
        .order_by(JobPosting.public_id.asc())
        .offset(offset)
        .limit(limit)
    )
    return [
        PublicJobSitemapEntry(
            public_id=public_id,
            slug=slug,
            updated_at=updated_at,
        )
        for public_id, slug, updated_at in rows
    ]


async def count_public_job_sitemap_entries(session: AsyncSession) -> int:
    """Count jobs currently eligible for sitemap inclusion."""
    count = await session.scalar(
        select(func.count(JobPosting.id))
        .join(Requisition, Requisition.id == JobPosting.requisition_id)
        .where(_public_visibility_conditions(_now()))
    )
    return count or 0
