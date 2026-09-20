"""PostgreSQL integration tests for HRIS connection lifecycle operations."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.outbox import OutboxEvent
from app.domains.hris.enums import HrisConnectionStatus, HrisProvider
from app.services.hris_connection_lifecycle import (
    delete_hris_connection,
    disable_hris_connection,
    get_hris_connection,
    list_hris_connections,
)
from app.services.hris_errors import (
    HrisAccessDeniedError,
    HrisConnectionNotFoundError,
    HrisConnectionValidationError,
    HrisConnectionVersionConflictError,
)
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    create_onboarding_template,
    start_onboarding,
)
from tests.services.test_onboarding import _seed_hired_application


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
    subject: str = "tenant-admin-subject",
) -> TenantContext:
    """Build a tenant-scoped test caller."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="hris-connection-lifecycle-test-request-id",
    )


async def _seed_connection(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    name: str = "Primary HRIS",
) -> HrisConnection:
    """Create a tenant and one active HRIS connection."""
    await _seed_hired_application(session, tenant_id=tenant_id)

    connection = HrisConnection(
        tenant_id=tenant_id,
        name=name,
        provider=HrisProvider.BAMBOOHR,
        status=HrisConnectionStatus.ACTIVE,
        credential_reference=f"tap-hris-{uuid4().hex}",
        created_by_subject="tenant-admin-subject",
    )
    session.add(connection)
    await session.commit()
    await session.refresh(connection)

    return connection


@pytest.mark.asyncio
async def test_only_tenant_admin_can_view_or_change_connections(
    session: AsyncSession,
) -> None:
    """Reject HRIS management attempts from non-administrative roles."""
    tenant_id = uuid4()
    connection = await _seed_connection(session, tenant_id=tenant_id)
    recruiter_context = _context(
        tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    with pytest.raises(HrisAccessDeniedError):
        await list_hris_connections(
            session,
            context=recruiter_context,
        )

    with pytest.raises(HrisAccessDeniedError):
        await get_hris_connection(
            session,
            context=recruiter_context,
            connection_id=connection.id,
        )

    with pytest.raises(HrisAccessDeniedError):
        await disable_hris_connection(
            session,
            context=recruiter_context,
            connection_id=connection.id,
            expected_version=connection.version,
        )


@pytest.mark.asyncio
async def test_disable_requires_current_version_and_records_safe_audit(
    session: AsyncSession,
) -> None:
    """Disable active connections with optimistic concurrency and no secrets."""
    tenant_id = uuid4()
    connection = await _seed_connection(session, tenant_id=tenant_id)
    initial_version = connection.version

    disabled = await disable_hris_connection(
        session,
        context=_context(tenant_id),
        connection_id=connection.id,
        expected_version=initial_version,
    )

    with pytest.raises(HrisConnectionVersionConflictError):
        await disable_hris_connection(
            session,
            context=_context(tenant_id),
            connection_id=connection.id,
            expected_version=initial_version,
        )

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "hris_connection.disabled",
            AuditEvent.entity_id == str(connection.id),
        )
    )

    assert disabled.status is HrisConnectionStatus.DISABLED
    assert disabled.disabled_at is not None
    assert disabled.disabled_by_subject == "tenant-admin-subject"
    assert disabled.version == initial_version + 1

    assert audit is not None
    assert audit.details == {
        "status": "disabled",
        "version": disabled.version,
    }
    assert connection.credential_reference not in str(audit.details)


@pytest.mark.asyncio
async def test_requires_disable_before_logical_deletion(
    session: AsyncSession,
) -> None:
    """Preserve active integration safety by requiring an explicit disable."""
    tenant_id = uuid4()
    connection = await _seed_connection(session, tenant_id=tenant_id)

    with pytest.raises(HrisConnectionValidationError):
        await delete_hris_connection(
            session,
            context=_context(tenant_id),
            connection_id=connection.id,
            expected_version=connection.version,
        )

    persisted = await session.get(HrisConnection, connection.id)
    assert persisted is not None
    assert persisted.status is HrisConnectionStatus.ACTIVE
    assert persisted.deleted_at is None


@pytest.mark.asyncio
async def test_logical_deletion_hides_connection_and_records_safe_audit(
    session: AsyncSession,
) -> None:
    """Keep retention-safe history while hiding deleted configuration."""
    tenant_id = uuid4()
    connection = await _seed_connection(session, tenant_id=tenant_id)

    disabled = await disable_hris_connection(
        session,
        context=_context(tenant_id),
        connection_id=connection.id,
        expected_version=connection.version,
    )
    deleted = await delete_hris_connection(
        session,
        context=_context(tenant_id),
        connection_id=connection.id,
        expected_version=disabled.version,
    )

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "hris_connection.deleted",
            AuditEvent.entity_id == str(connection.id),
        )
    )

    assert deleted.status is HrisConnectionStatus.DISABLED
    assert deleted.deleted_at is not None
    assert deleted.deleted_by_subject == "tenant-admin-subject"

    with pytest.raises(HrisConnectionNotFoundError):
        await get_hris_connection(
            session,
            context=_context(tenant_id),
            connection_id=connection.id,
        )

    listed = await list_hris_connections(
        session,
        context=_context(tenant_id),
    )
    assert listed == ()

    assert audit is not None
    assert audit.details == {
        "status": "disabled",
        "version": deleted.version,
    }
    assert connection.credential_reference not in str(audit.details)


@pytest.mark.asyncio
async def test_disabled_connection_does_not_queue_onboarding_handoff(
    session: AsyncSession,
) -> None:
    """Prevent new HRIS deliveries immediately after administrative disable."""
    application, _ = await _seed_hired_application(
        session,
        tenant_id=uuid4(),
    )

    # Use a separate complete tenant so one application owns one onboarding.
    onboarding_tenant_id = application.tenant_id
    onboarding_connection = HrisConnection(
        tenant_id=onboarding_tenant_id,
        name="Onboarding HRIS",
        provider=HrisProvider.BAMBOOHR,
        status=HrisConnectionStatus.ACTIVE,
        credential_reference=f"tap-hris-{uuid4().hex}",
        created_by_subject="tenant-admin-subject",
    )
    session.add(onboarding_connection)
    await session.commit()

    disabled = await disable_hris_connection(
        session,
        context=_context(onboarding_tenant_id),
        connection_id=onboarding_connection.id,
        expected_version=onboarding_connection.version,
    )

    template = await create_onboarding_template(
        session,
        context=_context(
            onboarding_tenant_id,
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
            subject="people-operations-subject",
        ),
        command=CreateOnboardingTemplateCommand(
            name="Standard onboarding",
            tasks=(
                OnboardingTemplateTaskDefinition(
                    title="Create employee account",
                    description="Provision employee access.",
                    due_offset_days=1,
                    default_assignee_role=Role.PEOPLE_OPERATIONS,
                ),
            ),
        ),
    )

    instance = await start_onboarding(
        session,
        context=_context(
            onboarding_tenant_id,
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
            subject="people-operations-subject",
        ),
        application_id=application.id,
        onboarding_template_id=template.id,
    )

    handoffs = list(
        await session.scalars(
            select(HrisHandoff).where(
                HrisHandoff.tenant_id == onboarding_tenant_id,
                HrisHandoff.onboarding_instance_id == instance.id,
            )
        )
    )
    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == onboarding_tenant_id,
                OutboxEvent.event_type == "hris.handoff_requested",
            )
        )
    )

    assert disabled.status is HrisConnectionStatus.DISABLED
    assert not handoffs
    assert not events


@pytest.mark.asyncio
async def test_connections_are_tenant_isolated(
    session: AsyncSession,
) -> None:
    """Treat another tenant's HRIS connection as absent."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()

    connection = await _seed_connection(
        session,
        tenant_id=owner_tenant_id,
    )
    await _seed_hired_application(
        session,
        tenant_id=other_tenant_id,
    )

    with pytest.raises(HrisConnectionNotFoundError):
        await get_hris_connection(
            session,
            context=_context(other_tenant_id),
            connection_id=connection.id,
        )

    with pytest.raises(HrisConnectionNotFoundError):
        await disable_hris_connection(
            session,
            context=_context(other_tenant_id),
            connection_id=connection.id,
            expected_version=connection.version,
        )

    persisted = await session.get(HrisConnection, connection.id)
    assert persisted is not None
    assert persisted.tenant_id == owner_tenant_id
    assert persisted.status is HrisConnectionStatus.ACTIVE
