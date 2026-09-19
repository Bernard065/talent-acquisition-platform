"""PostgreSQL integration tests for HRIS configuration and onboarding handoffs."""

from typing import NoReturn
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.hris_connections as hris_connections
import app.services.onboarding as onboarding
from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.onboarding import OnboardingInstance
from app.db.models.outbox import OutboxEvent
from app.domains.hris.enums import HrisConnectionStatus, HrisHandoffStatus, HrisProvider
from app.services.hris_connections import (
    CreateHrisConnectionCommand,
    create_hris_connection,
)
from app.services.hris_credentials import HrisCredentials
from app.services.hris_errors import (
    HrisAccessDeniedError,
    HrisActiveConnectionExistsError,
)
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    create_onboarding_template,
    start_onboarding,
)
from tests.services.test_onboarding import _seed_hired_application


class _FakeHrisCredentialVault:
    """In-memory vault proving no credentials enter PostgreSQL."""

    def __init__(self) -> None:
        self.stored: dict[str, HrisCredentials] = {}
        self.deleted_references: list[str] = []
        self._counter = 0

    async def store_hris_credentials(
        self,
        *,
        provider: str,
        tenant_id: str,
        credentials: HrisCredentials,
    ) -> str:
        """Store a secret and return an opaque reference."""
        self._counter += 1
        reference = f"infisical://hris/{tenant_id}/{provider}/{self._counter}"
        self.stored[reference] = credentials
        return reference

    async def resolve_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> HrisCredentials:
        """Resolve a previously stored secret."""
        return self.stored[credential_reference]

    async def delete_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> None:
        """Delete a stored secret during compensation."""
        self.deleted_references.append(credential_reference)
        self.stored.pop(credential_reference, None)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "tenant-admin-subject",
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
) -> TenantContext:
    """Build a verified tenant context for service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="hris-service-test-request-id",
    )


def _command(
    *,
    name: str = "Primary HRIS",
    provider: HrisProvider = HrisProvider.HIBOB,
) -> CreateHrisConnectionCommand:
    """Build valid HRIS configuration input."""
    return CreateHrisConnectionCommand(
        name=name,
        provider=provider,
        credentials=HrisCredentials(
            values={
                "api_token": SecretStr("test-only-token"),
            }
        ),
    )


async def _create_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
):
    """Create a minimal active onboarding template."""
    return await create_onboarding_template(
        session,
        context=_context(
            tenant_id,
            subject="people-operations-subject",
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
        ),
        command=CreateOnboardingTemplateCommand(
            name="Standard onboarding",
            tasks=(
                OnboardingTemplateTaskDefinition(
                    title="Create employee account",
                    description="Provision the employee account.",
                    due_offset_days=1,
                    default_assignee_role=Role.PEOPLE_OPERATIONS,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_only_tenant_admin_can_configure_hris(
    session: AsyncSession,
) -> None:
    """Reject HRIS configuration before any vault operation for non-admin users."""
    tenant_id = uuid4()
    await _seed_hired_application(session, tenant_id=tenant_id)

    vault = _FakeHrisCredentialVault()

    with pytest.raises(HrisAccessDeniedError):
        await create_hris_connection(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.RECRUITER}),
            ),
            command=_command(),
            credential_vault=vault,
        )

    assert not vault.stored
    assert not vault.deleted_references


@pytest.mark.asyncio
async def test_cleans_up_vault_secret_when_database_transaction_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compensate for a created external secret if database work rolls back."""
    tenant_id = uuid4()
    await _seed_hired_application(session, tenant_id=tenant_id)
    vault = _FakeHrisCredentialVault()

    def fail_audit(*_: object, **__: object) -> NoReturn:
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(hris_connections, "record_audit_event", fail_audit)

    with pytest.raises(RuntimeError, match="simulated database failure"):
        await create_hris_connection(
            session,
            context=_context(tenant_id),
            command=_command(),
            credential_vault=vault,
        )

    connections = list(
        await session.scalars(
            select(HrisConnection).where(HrisConnection.tenant_id == tenant_id)
        )
    )

    assert not connections
    assert not vault.stored
    assert len(vault.deleted_references) == 1


@pytest.mark.asyncio
async def test_enforces_one_active_hris_connection_per_tenant(
    session: AsyncSession,
) -> None:
    """Permit one active target only and remove a rejected second secret."""
    tenant_id = uuid4()
    await _seed_hired_application(session, tenant_id=tenant_id)
    vault = _FakeHrisCredentialVault()

    first = await create_hris_connection(
        session,
        context=_context(tenant_id),
        command=_command(),
        credential_vault=vault,
    )

    with pytest.raises(HrisActiveConnectionExistsError):
        await create_hris_connection(
            session,
            context=_context(tenant_id),
            command=_command(
                name="Secondary HRIS",
                provider=HrisProvider.WORKDAY,
            ),
            credential_vault=vault,
        )

    connections = list(
        await session.scalars(
            select(HrisConnection)
            .where(HrisConnection.tenant_id == tenant_id)
            .order_by(HrisConnection.created_at)
        )
    )

    assert len(connections) == 1
    assert connections[0].id == first.id
    assert connections[0].status is HrisConnectionStatus.ACTIVE
    assert len(vault.stored) == 1
    assert len(vault.deleted_references) == 1


@pytest.mark.asyncio
async def test_hris_connections_are_tenant_isolated(
    session: AsyncSession,
) -> None:
    """Allow separate tenants to configure independent HRIS destinations."""
    first_tenant_id = uuid4()
    second_tenant_id = uuid4()
    await _seed_hired_application(session, tenant_id=first_tenant_id)
    await _seed_hired_application(session, tenant_id=second_tenant_id)

    vault = _FakeHrisCredentialVault()

    first = await create_hris_connection(
        session,
        context=_context(first_tenant_id),
        command=_command(),
        credential_vault=vault,
    )
    second = await create_hris_connection(
        session,
        context=_context(second_tenant_id),
        command=_command(),
        credential_vault=vault,
    )

    assert first.tenant_id == first_tenant_id
    assert second.tenant_id == second_tenant_id
    assert first.credential_reference != second.credential_reference


@pytest.mark.asyncio
async def test_starting_onboarding_creates_private_atomic_hris_handoff(
    session: AsyncSession,
) -> None:
    """Create the handoff, outbox event, and audit event in one transaction."""
    tenant_id = uuid4()
    application, _ = await _seed_hired_application(session, tenant_id=tenant_id)
    vault = _FakeHrisCredentialVault()

    connection = await create_hris_connection(
        session,
        context=_context(tenant_id),
        command=_command(),
        credential_vault=vault,
    )
    template = await _create_template(session, tenant_id=tenant_id)

    instance = await start_onboarding(
        session,
        context=_context(
            tenant_id,
            subject="people-operations-subject",
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
        ),
        application_id=application.id,
        onboarding_template_id=template.id,
    )

    handoff = await session.scalar(
        select(HrisHandoff).where(
            HrisHandoff.tenant_id == tenant_id,
            HrisHandoff.onboarding_instance_id == instance.id,
        )
    )
    event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == "hris.handoff_requested",
            OutboxEvent.tenant_id == tenant_id,
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "hris_handoff.requested",
            AuditEvent.tenant_id == tenant_id,
        )
    )

    assert handoff is not None
    assert handoff.status is HrisHandoffStatus.PENDING
    assert handoff.hris_connection_id == connection.id
    assert handoff.application_id == application.id
    assert handoff.onboarding_instance_id == instance.id

    assert event is not None
    assert event.aggregate_type == "hris_handoff"
    assert event.aggregate_id == str(handoff.id)
    assert event.payload == {
        "hris_handoff_id": str(handoff.id),
        "onboarding_instance_id": str(instance.id),
        "handoff_version": handoff.version,
    }

    assert audit is not None
    assert audit.entity_id == str(handoff.id)
    assert audit.details == {
        "status": "pending",
        "version": handoff.version,
    }

    serialized_payload = str(event.payload).lower()
    serialized_audit = str(audit.details).lower()
    for prohibited_value in (
        "ada lovelace",
        "example.test",
        "employee_referral",
        "test-only-token",
    ):
        assert prohibited_value not in serialized_payload
        assert prohibited_value not in serialized_audit


@pytest.mark.asyncio
async def test_failed_onboarding_rolls_back_hris_handoff_and_outbox(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep onboarding, handoff, audit, and outbox changes transactionally atomic."""
    tenant_id = uuid4()
    application, _ = await _seed_hired_application(session, tenant_id=tenant_id)
    vault = _FakeHrisCredentialVault()

    await create_hris_connection(
        session,
        context=_context(tenant_id),
        command=_command(),
        credential_vault=vault,
    )
    template = await _create_template(session, tenant_id=tenant_id)

    async def fail_notifications(*_: object, **__: object) -> None:
        raise RuntimeError("simulated notification persistence failure")

    monkeypatch.setattr(
        onboarding,
        "enqueue_notifications_for_roles",
        fail_notifications,
    )

    with pytest.raises(RuntimeError, match="simulated notification persistence failure"):
        await start_onboarding(
            session,
            context=_context(
                tenant_id,
                subject="people-operations-subject",
                roles=frozenset({Role.PEOPLE_OPERATIONS}),
            ),
            application_id=application.id,
            onboarding_template_id=template.id,
        )

    instances = list(
        await session.scalars(
            select(OnboardingInstance).where(
                OnboardingInstance.tenant_id == tenant_id
            )
        )
    )
    handoffs = list(
        await session.scalars(
            select(HrisHandoff).where(HrisHandoff.tenant_id == tenant_id)
        )
    )
    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "hris.handoff_requested",
                OutboxEvent.tenant_id == tenant_id,
            )
        )
    )

    assert not instances
    assert not handoffs
    assert not events
