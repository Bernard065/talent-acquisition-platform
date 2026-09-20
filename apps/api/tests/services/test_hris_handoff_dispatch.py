"""PostgreSQL integration tests for HRIS handoff outbox dispatch."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role
from app.db.models.audit import AuditEvent
from app.db.models.hris import HrisHandoff
from app.db.models.offer import Offer
from app.db.models.outbox import OutboxEvent
from app.domains.hris.enums import HrisHandoffStatus, HrisProvider
from app.domains.offers.enums import OfferPayPeriod, OfferStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.hris_connections import (
    CreateHrisConnectionCommand,
    create_hris_connection,
)
from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVaultError,
)
from app.services.hris_handoff_dispatch import dispatch_hris_handoff_events
from app.services.hris_handoff_workflow import prepare_hris_handoff_dispatch
from app.services.hris_provider import (
    HrisEmployeeHandoffCommand,
    HrisEmployeeHandoffResult,
    HrisProviderError,
)
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    create_onboarding_template,
    start_onboarding,
)
from app.services.outbox_worker import OutboxWorkerPolicy
from tests.services.test_onboarding import _context, _seed_hired_application


class _FakeHrisCredentialVault:
    """Fake vault that keeps credentials only in test-process memory."""

    def __init__(
        self,
        *,
        error: HrisCredentialVaultError | None = None,
    ) -> None:
        self.error = error
        self.references: list[str] = []

    async def store_hris_credentials(
        self,
        *,
        provider: str,
        tenant_id: str,
        credentials: HrisCredentials,  # pyright: ignore[reportUnusedParameter]
    ) -> str:
        """Return an opaque test-only credential reference."""
        del credentials
        return f"test-vault://{tenant_id}/{provider}"

    async def resolve_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> HrisCredentials:
        """Return test credentials or a classified vault failure."""
        self.references.append(credential_reference)

        if self.error is not None:
            raise self.error

        return HrisCredentials(
            values={"api_token": SecretStr("test-only-hris-token")}
        )

    async def delete_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> None:
        """Discard a test-only credential reference."""


async def _create_handoff(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> HrisHandoff:
    """Create an accepted onboarding handoff and its outbox event."""
    application, _ = await _seed_hired_application(session, tenant_id=tenant_id)
    now = datetime.now(UTC)
    session.add(
        Offer(
            tenant_id=tenant_id,
            application_id=application.id,
            status=OfferStatus.ACCEPTED,
            currency="kes",
            base_salary=Decimal("250000.00"),
            pay_period=OfferPayPeriod.MONTHLY,
            bonus_amount=None,
            equity_summary=None,
            proposed_start_date=now.date() + timedelta(days=30),
            expires_at=now + timedelta(days=14),
            accepted_at=now,
            created_by_subject="people-operations-subject",
        )
    )
    await session.commit()
    vault = _FakeHrisCredentialVault()
    connection = await create_hris_connection(
        session,
        context=_context(
            tenant_id,
            subject="tenant-admin-subject",
            roles=frozenset({Role.TENANT_ADMIN}),
        ),
        command=CreateHrisConnectionCommand(
            name="Primary HRIS",
            provider=HrisProvider.HIBOB,
            credentials=HrisCredentials(
                values={"api_token": SecretStr("test-only-token")}
            ),
        ),
        credential_vault=vault,
    )
    template = await create_onboarding_template(
        session,
        context=_context(tenant_id),
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
    instance = await start_onboarding(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        onboarding_template_id=template.id,
    )
    handoff = await session.scalar(
        select(HrisHandoff).where(
            HrisHandoff.tenant_id == tenant_id,
            HrisHandoff.onboarding_instance_id == instance.id,
        )
    )
    assert handoff is not None
    assert connection.id == handoff.hris_connection_id
    return handoff


async def _get_handoff(session: AsyncSession, handoff_id: UUID) -> HrisHandoff:
    """Load a handoff and fail clearly if the fixture is incomplete."""
    handoff = await session.get(HrisHandoff, handoff_id)
    assert handoff is not None
    return handoff


async def _get_event(session: AsyncSession, event_id: UUID) -> OutboxEvent:
    """Load an outbox event and fail clearly if the fixture is incomplete."""
    event = await session.get(OutboxEvent, event_id)
    assert event is not None
    return event


class _FakeHrisProvider:
    """Idempotent provider fake that records private in-memory input only."""

    provider = HrisProvider.HIBOB.value

    def __init__(
        self,
        *,
        error: HrisProviderError | None = None,
    ) -> None:
        self.error = error
        self.commands: list[HrisEmployeeHandoffCommand] = []
        self.idempotency_keys: list[str] = []

    async def create_or_update_employee(
        self,
        *,
        command: HrisEmployeeHandoffCommand,
        credentials: HrisCredentials,
    ) -> HrisEmployeeHandoffResult:
        """Return one opaque provider reference or raise a classified error."""
        self.commands.append(command)
        self.idempotency_keys.append(command.idempotency_key)

        assert credentials.values["api_token"].get_secret_value() == (
            "test-only-hris-token"
        )

        if self.error is not None:
            raise self.error

        return HrisEmployeeHandoffResult(
            external_employee_reference=f"employee:{command.hris_handoff_id}"
        )


def _policy() -> OutboxWorkerPolicy:
    """Use short bounded retry settings for deterministic tests."""
    return OutboxWorkerPolicy(
        batch_size=10,
        max_attempts=3,
        visibility_timeout=timedelta(minutes=1),
        base_retry_delay=timedelta(seconds=1),
        maximum_retry_delay=timedelta(seconds=5),
    )


async def _handoff_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> OutboxEvent:
    """Load the HRIS event generated atomically by onboarding startup."""
    event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_type == "hris.handoff_requested",
        )
    )
    assert event is not None
    return event


@pytest.mark.asyncio
async def test_dispatches_handoff_and_persists_only_safe_artifacts(
    session: AsyncSession,
) -> None:
    """Deliver one handoff while retaining candidate data only in memory."""
    tenant_id = uuid4()
    handoff = await _create_handoff(session, tenant_id=tenant_id)
    event = await _handoff_event(session, tenant_id=tenant_id)

    vault = _FakeHrisCredentialVault()
    provider = _FakeHrisProvider()

    result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=vault,
        providers={HrisProvider.HIBOB: provider},
        policy=_policy(),
    )

    persisted_handoff = await _get_handoff(session, handoff.id)
    await session.refresh(event)

    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_type == "hris_handoff",
            )
        )
    )
    persisted_text = " ".join(
        [
            str(event.payload),
            *(str(audit.details) for audit in audits),
            str(persisted_handoff.external_employee_reference),
        ]
    ).lower()

    assert result.claimed == 1
    assert result.processed == 1
    assert result.retried == 0
    assert result.dead_lettered == 0

    assert persisted_handoff.status is HrisHandoffStatus.SUCCEEDED
    assert persisted_handoff.succeeded_at is not None
    assert persisted_handoff.external_employee_reference == (
        f"employee:{handoff.id}"
    )

    assert event.status is OutboxEventStatus.PROCESSED
    assert event.processed_at is not None

    assert vault.references
    assert len(provider.commands) == 1
    assert provider.commands[0].hris_handoff_id == handoff.id
    assert provider.commands[0].idempotency_key == (
        handoff.external_idempotency_key
    )

    assert "ada lovelace" not in persisted_text
    assert "example.test" not in persisted_text
    assert "test-only-hris-token" not in persisted_text


@pytest.mark.asyncio
async def test_retryable_provider_failure_reuses_stable_idempotency_key(
    session: AsyncSession,
) -> None:
    """Retry provider outages without creating a new external employee."""
    tenant_id = uuid4()
    handoff = await _create_handoff(session, tenant_id=tenant_id)
    event = await _handoff_event(session, tenant_id=tenant_id)

    vault = _FakeHrisCredentialVault()
    failing_provider = _FakeHrisProvider(
        error=HrisProviderError(
            "provider_unavailable",
            retryable=True,
        )
    )

    first_result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=vault,
        providers={HrisProvider.HIBOB: failing_provider},
        policy=_policy(),
    )

    await session.refresh(event)
    retryable_handoff = await _get_handoff(session, handoff.id)

    assert first_result.retried == 1
    assert event.status is OutboxEventStatus.PENDING
    assert retryable_handoff.status is HrisHandoffStatus.RETRYABLE_FAILED
    assert retryable_handoff.last_error_code == "provider_unavailable"

    # Make the scheduled retry due immediately without waiting in a test.
    event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    succeeding_provider = _FakeHrisProvider()
    second_result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=vault,
        providers={HrisProvider.HIBOB: succeeding_provider},
        policy=_policy(),
    )

    recovered_handoff = await _get_handoff(session, handoff.id)
    event = await _get_event(session, event.id)

    assert second_result.processed == 1
    assert recovered_handoff.status is HrisHandoffStatus.SUCCEEDED
    assert event.status is OutboxEventStatus.PROCESSED
    assert succeeding_provider.idempotency_keys == [
        handoff.external_idempotency_key
    ]


@pytest.mark.asyncio
async def test_terminal_provider_failure_fails_handoff_and_dead_letters_event(
    session: AsyncSession,
) -> None:
    """Do not retry provider rejections that require human intervention."""
    tenant_id = uuid4()
    handoff = await _create_handoff(session, tenant_id=tenant_id)
    event = await _handoff_event(session, tenant_id=tenant_id)

    provider = _FakeHrisProvider(
        error=HrisProviderError(
            "provider_rejected_request",
            retryable=False,
        )
    )

    result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=_FakeHrisCredentialVault(),
        providers={HrisProvider.HIBOB: provider},
        policy=_policy(),
    )

    persisted_handoff = await _get_handoff(session, handoff.id)
    await session.refresh(event)

    assert result.dead_lettered == 1
    assert persisted_handoff.status is HrisHandoffStatus.FAILED
    assert persisted_handoff.last_error_code == "provider_rejected_request"
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "provider_rejected_request"


@pytest.mark.asyncio
async def test_recovers_stale_processing_handoff_with_same_provider_key(
    session: AsyncSession,
) -> None:
    """Recover safely after a worker crashes before acknowledging the event."""
    tenant_id = uuid4()
    handoff = await _create_handoff(session, tenant_id=tenant_id)
    event = await _handoff_event(session, tenant_id=tenant_id)

    # Simulates the prior worker starting work and crashing before provider call
    # completion or outbox acknowledgement.
    prepared = await prepare_hris_handoff_dispatch(
        session,
        context=_context(tenant_id),
        handoff_id=handoff.id,
    )

    provider = _FakeHrisProvider()
    result = await dispatch_hris_handoff_events(
        session,
        worker_id="recovery-worker",
        credential_vault=_FakeHrisCredentialVault(),
        providers={HrisProvider.HIBOB: provider},
        policy=_policy(),
    )

    persisted_handoff = await _get_handoff(session, handoff.id)
    await session.refresh(event)

    assert prepared.status is HrisHandoffStatus.PROCESSING
    assert result.processed == 1
    assert persisted_handoff.status is HrisHandoffStatus.SUCCEEDED
    assert persisted_handoff.attempt_count == 1
    assert provider.idempotency_keys == [handoff.external_idempotency_key]
    assert event.status is OutboxEventStatus.PROCESSED


@pytest.mark.asyncio
async def test_missing_provider_terminally_fails_handoff(
    session: AsyncSession,
) -> None:
    """Dead-letter unsupported provider configuration without unsafe retries."""
    tenant_id = uuid4()
    handoff = await _create_handoff(session, tenant_id=tenant_id)
    event = await _handoff_event(session, tenant_id=tenant_id)

    result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=_FakeHrisCredentialVault(),
        providers={},
        policy=_policy(),
    )

    persisted_handoff = await _get_handoff(session, handoff.id)
    await session.refresh(event)

    assert result.dead_lettered == 1
    assert persisted_handoff.status is HrisHandoffStatus.FAILED
    assert persisted_handoff.last_error_code == "hris_provider_not_configured"
    assert event.status is OutboxEventStatus.DEAD_LETTERED


@pytest.mark.asyncio
async def test_handoff_event_cannot_access_another_tenants_data(
    session: AsyncSession,
) -> None:
    """Tenant-scoped joins reject a malformed cross-tenant event safely."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()

    handoff = await _create_handoff(session, tenant_id=owner_tenant_id)
    await _seed_hired_application(session, tenant_id=other_tenant_id)

    event = await _handoff_event(session, tenant_id=owner_tenant_id)

    # Simulate a corrupted or malicious event without changing the handoff.
    event.tenant_id = other_tenant_id
    await session.commit()

    result = await dispatch_hris_handoff_events(
        session,
        worker_id="hris-test-worker",
        credential_vault=_FakeHrisCredentialVault(),
        providers={HrisProvider.HIBOB: _FakeHrisProvider()},
        policy=_policy(),
    )

    persisted_handoff = await _get_handoff(session, handoff.id)
    await session.refresh(event)

    assert result.dead_lettered == 1
    assert persisted_handoff.tenant_id == owner_tenant_id
    assert persisted_handoff.status is HrisHandoffStatus.PENDING
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "hris_handoff_source_not_found"
