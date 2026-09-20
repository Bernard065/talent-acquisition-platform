"""Outbox-driven, retry-safe dispatch of onboarding handoffs to HRIS providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.offer import Offer
from app.db.models.outbox import OutboxEvent
from app.domains.hris.enums import (
    HrisConnectionStatus,
    HrisHandoffStatus,
    HrisProvider,
)
from app.domains.offers.enums import OfferStatus
from app.services.hris_credentials import (
    HrisCredentialVault,
    HrisCredentialVaultError,
)
from app.services.hris_handoff_errors import (
    HrisHandoffNotFoundError,
    HrisHandoffValidationError,
)
from app.services.hris_handoff_workflow import (
    mark_hris_handoff_failed,
    mark_hris_handoff_retryable_failure,
    mark_hris_handoff_succeeded,
    prepare_hris_handoff_dispatch,
)
from app.services.hris_provider import (
    HrisEmployeeHandoffCommand,
    HrisProviderAdapter,
    HrisProviderError,
)
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

_HRIS_HANDOFF_REQUESTED_EVENT = "hris.handoff_requested"
_SAFE_FAILURE_CODE = "hris_dispatch_unexpected_error"


@dataclass(frozen=True, slots=True)
class HrisHandoffDispatchResult:
    """Counters from one bounded HRIS handoff worker poll."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class _LoadedHrisHandoff:
    """Private data needed only while calling the external HRIS provider."""

    handoff: HrisHandoff
    connection: HrisConnection
    candidate: Candidate
    proposed_start_date: date


def _worker_context(event: OutboxEvent, worker_id: str) -> TenantContext:
    """Build a tenant-scoped internal caller identity for audit records."""
    return TenantContext(
        tenant_id=event.tenant_id,
        subject=f"system:hris-handoff-dispatch:{worker_id}",
        roles=frozenset({Role.PEOPLE_OPERATIONS}),
        request_id=f"outbox:{event.id}",
    )


def _safe_failure_code(code: str) -> str:
    """Return only a classified failure code safe for persistence."""
    normalized = code.strip().lower()

    if (
        normalized
        and len(normalized) <= 100
        and all(
            character.islower()
            or character.isdigit()
            or character == "_"
            for character in normalized
        )
    ):
        return normalized

    return _SAFE_FAILURE_CODE


def _event_handoff_id(event: OutboxEvent) -> UUID | None:
    """Validate the identifier-only HRIS outbox event payload."""
    if event.event_type != _HRIS_HANDOFF_REQUESTED_EVENT:
        return None

    if event.aggregate_type != "hris_handoff":
        return None

    raw_handoff_id = event.payload.get("hris_handoff_id")
    if not isinstance(raw_handoff_id, str):
        return None

    try:
        handoff_id = UUID(raw_handoff_id)
    except ValueError:
        return None

    if event.aggregate_id != str(handoff_id):
        return None

    return handoff_id


async def _load_private_handoff(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    handoff_id: UUID,
) -> _LoadedHrisHandoff | None:
    """
    Load provider input through tenant-scoped joins.

    Candidate data is used in memory only. It must never be placed in outbox
    payloads, audit events, worker logs, exception messages, or retry records.
    """
    result = await session.execute(
        select(HrisHandoff, HrisConnection, Candidate, Offer.proposed_start_date)
        .join(
            HrisConnection,
            and_(
                HrisConnection.id == HrisHandoff.hris_connection_id,
                HrisConnection.tenant_id == HrisHandoff.tenant_id,
            ),
        )
        .join(
            Application,
            and_(
                Application.id == HrisHandoff.application_id,
                Application.tenant_id == HrisHandoff.tenant_id,
            ),
        )
        .join(
            Candidate,
            and_(
                Candidate.id == Application.candidate_id,
                Candidate.tenant_id == HrisHandoff.tenant_id,
            ),
        )
        .join(
            Offer,
            and_(
                Offer.application_id == Application.id,
                Offer.tenant_id == HrisHandoff.tenant_id,
                Offer.status == OfferStatus.ACCEPTED,
            ),
        )
        .where(
            HrisHandoff.id == handoff_id,
            HrisHandoff.tenant_id == tenant_id,
        )
    )

    row = result.one_or_none()
    if row is None:
        return None

    return _LoadedHrisHandoff(
        handoff=row[0],
        connection=row[1],
        candidate=row[2],
        proposed_start_date=row[3],
    )


async def _record_failure(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    worker_id: str,
    context: TenantContext,
    handoff: HrisHandoff,
    failure_code: str,
    retryable: bool,
    policy: OutboxWorkerPolicy,
) -> Literal["retried", "dead_lettered"]:
    """Persist a classified handoff failure and release or close its outbox lease."""
    if retryable:
        updated_handoff = await mark_hris_handoff_retryable_failure(
            session,
            context=context,
            handoff_id=handoff.id,
            expected_version=handoff.version,
            failure_code=failure_code,
        )
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code=updated_handoff.last_error_code or _SAFE_FAILURE_CODE,
            policy=policy,
        )
        return "retried"

    updated_handoff = await mark_hris_handoff_failed(
        session,
        context=context,
        handoff_id=handoff.id,
        expected_version=handoff.version,
        failure_code=failure_code,
    )
    await dead_letter_outbox_event(
        session,
        event_id=event.id,
        worker_id=worker_id,
        failure_code=updated_handoff.last_error_code or _SAFE_FAILURE_CODE,
    )
    return "dead_lettered"


async def _dispatch_event(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    worker_id: str,
    credential_vault: HrisCredentialVault,
    providers: Mapping[HrisProvider, HrisProviderAdapter],
    policy: OutboxWorkerPolicy,
) -> Literal["processed", "retried", "dead_lettered"]:
    """Process one leased handoff event without exposing private employee data."""
    handoff_id = _event_handoff_id(event)
    if handoff_id is None:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="invalid_hris_handoff_event",
        )
        return "dead_lettered"

    loaded = await _load_private_handoff(
        session,
        tenant_id=event.tenant_id,
        handoff_id=handoff_id,
    )
    if loaded is None:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="hris_handoff_source_not_found",
        )
        return "dead_lettered"

    handoff = loaded.handoff
    context = _worker_context(event, worker_id)

    # Recovery after provider success but before event acknowledgement.
    if handoff.status is HrisHandoffStatus.SUCCEEDED:
        await mark_outbox_event_processed(
            session,
            event_id=event.id,
            worker_id=worker_id,
        )
        return "processed"

    if handoff.status is HrisHandoffStatus.FAILED:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="hris_handoff_terminally_failed",
        )
        return "dead_lettered"

    if loaded.connection.status is not HrisConnectionStatus.ACTIVE:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="hris_connection_inactive",
        )
        return "dead_lettered"

    provider = providers.get(loaded.connection.provider)
    if (
        provider is None
        or provider.provider != loaded.connection.provider.value
    ):
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="hris_provider_not_configured",
        )
        return "dead_lettered"

    try:
        prepared = await prepare_hris_handoff_dispatch(
            session,
            context=context,
            handoff_id=handoff.id,
        )
    except (HrisHandoffNotFoundError, HrisHandoffValidationError):
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="hris_handoff_not_dispatchable",
        )
        return "dead_lettered"

    try:
        credentials = await credential_vault.resolve_hris_credentials(
            credential_reference=loaded.connection.credential_reference,
        )
        result = await provider.create_or_update_employee(
            command=HrisEmployeeHandoffCommand(
                hris_handoff_id=prepared.id,
                application_id=prepared.application_id,
                onboarding_instance_id=prepared.onboarding_instance_id,
                full_name=loaded.candidate.full_name,
                email=loaded.candidate.email,
                proposed_start_date=loaded.proposed_start_date,
                idempotency_key=prepared.external_idempotency_key,
            ),
            credentials=credentials,
        )
    except HrisCredentialVaultError as error:
        return await _record_failure(
            session,
            event=event,
            worker_id=worker_id,
            context=context,
            handoff=prepared,
            failure_code=_safe_failure_code(error.code),
            retryable=error.retryable,
            policy=policy,
        )
    except HrisProviderError as error:
        return await _record_failure(
            session,
            event=event,
            worker_id=worker_id,
            context=context,
            handoff=prepared,
            failure_code=_safe_failure_code(error.code),
            retryable=error.retryable,
            policy=policy,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Never persist raw exception text: it can contain provider or employee data.
        return await _record_failure(
            session,
            event=event,
            worker_id=worker_id,
            context=context,
            handoff=prepared,
            failure_code=_SAFE_FAILURE_CODE,
            retryable=True,
            policy=policy,
        )

    try:
        await mark_hris_handoff_succeeded(
            session,
            context=context,
            handoff_id=prepared.id,
            expected_version=prepared.version,
            external_employee_reference=result.external_employee_reference,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Provider success may already be durable remotely. Retry with the stable
        # handoff idempotency key to recover safely.
        return await _record_failure(
            session,
            event=event,
            worker_id=worker_id,
            context=context,
            handoff=prepared,
            failure_code="hris_handoff_persistence_error",
            retryable=True,
            policy=policy,
        )

    await mark_outbox_event_processed(
        session,
        event_id=event.id,
        worker_id=worker_id,
    )
    return "processed"


async def dispatch_hris_handoff_events(
    session: AsyncSession,
    *,
    worker_id: str,
    credential_vault: HrisCredentialVault,
    providers: Mapping[HrisProvider, HrisProviderAdapter],
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> HrisHandoffDispatchResult:
    """Claim and dispatch one bounded batch of HRIS handoff events."""
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({_HRIS_HANDOFF_REQUESTED_EVENT}),
    )

    processed = 0
    retried = 0
    dead_lettered = 0

    for event in events:
        outcome = await _dispatch_event(
            session,
            event=event,
            worker_id=worker_id,
            credential_vault=credential_vault,
            providers=providers,
            policy=policy,
        )

        if outcome == "processed":
            processed += 1
        elif outcome == "retried":
            retried += 1
        else:
            dead_lettered += 1

    return HrisHandoffDispatchResult(
        claimed=len(events),
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
    )
