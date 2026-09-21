"""PostgreSQL tests for private tenant-scoped HRIS handoff operations."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.identity import Tenant
from app.db.models.onboarding import OnboardingInstance, OnboardingTemplate
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.hris.enums import (
    HrisConnectionStatus,
    HrisHandoffStatus,
    HrisProvider,
)
from app.domains.onboarding.enums import OnboardingInstanceStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.hris_errors import HrisAccessDeniedError
from app.services.hris_handoff_errors import (
    HrisHandoffNotFoundError,
    InvalidHrisHandoffCursorError,
)
from app.services.hris_handoff_operations import (
    get_hris_handoff_operation,
    list_hris_handoff_operations,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
) -> TenantContext:
    """Build a verified tenant-scoped caller context."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="tenant-admin-subject",
        roles=roles,
        request_id="hris-handoff-operations-test-request-id",
    )


async def _seed_handoffs(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    entries: tuple[tuple[HrisHandoffStatus, datetime], ...],
) -> list[HrisHandoff]:
    """Persist safe operational handoff records for one tenant."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"HRIS Operations Tenant {tenant_id.hex[:12]}",
            slug=f"hris-operations-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    connection = HrisConnection(
        tenant_id=tenant_id,
        name="Primary HRIS",
        provider=HrisProvider.BAMBOOHR,
        status=HrisConnectionStatus.ACTIVE,
        credential_reference=f"infisical://hris/{tenant_id}/primary",
        created_by_subject="tenant-admin-subject",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    template = OnboardingTemplate(
        tenant_id=tenant_id,
        name="Standard onboarding",
        version=1,
        is_active=True,
        created_by_subject="people-operations-subject",
    )
    session.add_all([connection, requisition, template])
    await session.flush()

    handoffs: list[HrisHandoff] = []

    for position, (status, timestamp) in enumerate(entries, start=1):
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name=f"Candidate {position}",
            email=f"candidate-{position}-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"candidate-{position}-{tenant_id.hex[:8]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
        )
        session.add(candidate)
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.HIRED,
            created_by_subject="seed",
        )
        session.add(application)
        await session.flush()

        onboarding_instance = OnboardingInstance(
            tenant_id=tenant_id,
            application_id=application.id,
            onboarding_template_id=template.id,
            template_snapshot={
                "template_id": str(template.id),
                "tasks": [],
            },
            status=OnboardingInstanceStatus.ACTIVE,
            started_by_subject="people-operations-subject",
            started_at=timestamp,
        )
        session.add(onboarding_instance)
        await session.flush()

        handoff = HrisHandoff(
            tenant_id=tenant_id,
            hris_connection_id=connection.id,
            onboarding_instance_id=onboarding_instance.id,
            application_id=application.id,
            status=status,
            external_idempotency_key=f"handoff-{tenant_id}-{position}",
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(handoff)
        handoffs.append(handoff)

    await session.commit()
    return handoffs


@pytest.mark.asyncio
async def test_requires_tenant_admin_role(
    session: AsyncSession,
) -> None:
    """Reject operational handoff inspection by non-administrator roles."""
    tenant_id = uuid4()
    now = datetime.now(UTC)

    await _seed_handoffs(
        session,
        tenant_id=tenant_id,
        entries=((HrisHandoffStatus.PENDING, now),),
    )

    with pytest.raises(HrisAccessDeniedError):
        await list_hris_handoff_operations(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.RECRUITER}),
            ),
        )


@pytest.mark.asyncio
async def test_tenant_isolation_hides_other_tenant_handoffs(
    session: AsyncSession,
) -> None:
    """Return only handoffs owned by the authenticated tenant."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    now = datetime.now(UTC)

    owned_handoff = (
        await _seed_handoffs(
            session,
            tenant_id=owner_tenant_id,
            entries=((HrisHandoffStatus.PENDING, now),),
        )
    )[0]
    other_handoff = (
        await _seed_handoffs(
            session,
            tenant_id=other_tenant_id,
            entries=((HrisHandoffStatus.FAILED, now + timedelta(minutes=1)),),
        )
    )[0]

    page = await list_hris_handoff_operations(
        session,
        context=_context(owner_tenant_id),
    )

    assert [item.handoff.id for item in page.items] == [owned_handoff.id]
    assert page.items[0].provider is HrisProvider.BAMBOOHR

    with pytest.raises(HrisHandoffNotFoundError):
        await get_hris_handoff_operation(
            session,
            context=_context(owner_tenant_id),
            handoff_id=other_handoff.id,
        )


@pytest.mark.asyncio
async def test_filters_handoffs_by_status_and_created_at_range(
    session: AsyncSession,
) -> None:
    """Apply status and inclusive UTC creation-time filters tenant-locally."""
    tenant_id = uuid4()
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    handoffs = await _seed_handoffs(
        session,
        tenant_id=tenant_id,
        entries=(
            (HrisHandoffStatus.PENDING, base_time),
            (HrisHandoffStatus.RETRYABLE_FAILED, base_time + timedelta(days=1)),
            (HrisHandoffStatus.FAILED, base_time + timedelta(days=2)),
        ),
    )

    failed_page = await list_hris_handoff_operations(
        session,
        context=_context(tenant_id),
        status=HrisHandoffStatus.FAILED,
    )
    date_page = await list_hris_handoff_operations(
        session,
        context=_context(tenant_id),
        created_from=base_time + timedelta(hours=12),
        created_to=base_time + timedelta(days=1, hours=12),
    )

    assert [item.handoff.id for item in failed_page.items] == [handoffs[2].id]
    assert [item.handoff.id for item in date_page.items] == [handoffs[1].id]


@pytest.mark.asyncio
async def test_uses_stable_non_duplicating_keyset_cursor_pages(
    session: AsyncSession,
) -> None:
    """Use updated_at and UUID tie-breaking to prevent page duplication."""
    tenant_id = uuid4()
    shared_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    handoffs = await _seed_handoffs(
        session,
        tenant_id=tenant_id,
        entries=(
            (HrisHandoffStatus.PENDING, shared_timestamp),
            (HrisHandoffStatus.PENDING, shared_timestamp),
            (HrisHandoffStatus.PENDING, shared_timestamp),
        ),
    )

    first_page = await list_hris_handoff_operations(
        session,
        context=_context(tenant_id),
        limit=2,
    )
    second_page = await list_hris_handoff_operations(
        session,
        context=_context(tenant_id),
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [
        item.handoff.id
        for item in first_page.items + second_page.items
    ]

    assert returned_ids == sorted(
        [handoff.id for handoff in handoffs],
        reverse=True,
    )
    assert len(returned_ids) == len(set(returned_ids))
    assert first_page.next_cursor is not None
    assert second_page.next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        "e30",  # "{}"
        "eyJoYW5kb2ZmX2lkIjoibm90LWEtdXVpZCJ9",
    ],
)
async def test_rejects_invalid_cursor(
    session: AsyncSession,
    cursor: str,
) -> None:
    """Reject malformed pagination state rather than using partial data."""
    tenant_id = uuid4()
    now = datetime.now(UTC)

    await _seed_handoffs(
        session,
        tenant_id=tenant_id,
        entries=((HrisHandoffStatus.PENDING, now),),
    )

    with pytest.raises(InvalidHrisHandoffCursorError):
        await list_hris_handoff_operations(
            session,
            context=_context(tenant_id),
            cursor=cursor,
        )
