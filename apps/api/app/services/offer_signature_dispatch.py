"""Reliable outbox dispatch for offer-signature requests."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.offer import Offer
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.models.outbox import OutboxEvent
from app.domains.signatures.enums import OfferSignatureStatus
from app.services.offer_signature_provider import (
    CreateOfferSignatureEnvelopeCommand,
    OfferSignatureProvider,
    OfferSignatureProviderError,
    OfferSignatureRecipient,
)
from app.services.offer_signatures import send_offer_signature_request
from app.services.outbox_worker import (
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

SIGNATURE_REQUESTED_EVENT = "offer_signature.requested"


@dataclass(frozen=True, slots=True)
class OfferSignatureDispatchResult:
    """Counters from one bounded dispatch-worker poll."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


async def dispatch_offer_signature_requests(
    session: AsyncSession,
    *,
    worker_id: str,
    providers: Mapping[str, OfferSignatureProvider],
    policy: OutboxWorkerPolicy,
) -> OfferSignatureDispatchResult:
    """Dispatch claimed signature requests using idempotent provider calls."""

    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({SIGNATURE_REQUESTED_EVENT}),
    )

    processed = 0
    retried = 0
    dead_lettered = 0

    for event in events:
        outcome = await _dispatch_event(
            session,
            event=event,
            worker_id=worker_id,
            providers=providers,
            policy=policy,
        )

        if outcome == "processed":
            processed += 1
        elif outcome == "retried":
            retried += 1
        else:
            dead_lettered += 1

    return OfferSignatureDispatchResult(
        claimed=len(events),
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
    )


async def _dispatch_event(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    worker_id: str,
    providers: Mapping[str, OfferSignatureProvider],
    policy: OutboxWorkerPolicy,
) -> Literal["processed", "retried", "dead_lettered"]:
    """Process exactly one claimed signature-request event."""

    signature_request_id = _event_signature_request_id(event)
    if signature_request_id is None:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="invalid_signature_event",
        )
        return "dead_lettered"

    loaded = await _load_signature_request_and_candidate(
        session,
        tenant_id=event.tenant_id,
        signature_request_id=signature_request_id,
    )
    if loaded is None:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_request_not_found",
        )
        return "dead_lettered"

    signature_request, candidate = loaded

    if event.aggregate_id != str(signature_request.id):
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_event_aggregate_mismatch",
        )
        return "dead_lettered"

    event_provider = event.payload.get("provider")
    if not isinstance(event_provider, str) or event_provider != signature_request.provider:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_event_provider_mismatch",
        )
        return "dead_lettered"

    # A previous attempt may have completed the database transition before the
    # worker crashed while acknowledging the outbox event.
    if (
        signature_request.status is OfferSignatureStatus.SENT
        and signature_request.provider_envelope_reference is not None
    ):
        await mark_outbox_event_processed(
            session,
            event_id=event.id,
            worker_id=worker_id,
        )
        return "processed"

    if signature_request.status is not OfferSignatureStatus.DRAFT:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_request_not_dispatchable",
        )
        return "dead_lettered"

    provider = providers.get(signature_request.provider)
    if provider is None or provider.provider != signature_request.provider:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_provider_not_configured",
        )
        return "dead_lettered"

    try:
        envelope = await provider.create_envelope(
            command=CreateOfferSignatureEnvelopeCommand(
                signature_request_id=signature_request.id,
                document_reference=signature_request.document_reference,
                recipient=OfferSignatureRecipient(
                    full_name=candidate.full_name,
                    email=candidate.email,
                ),
                expires_at=signature_request.expires_at,
                # Stable across retries: safe after a provider success/database
                # failure crash window.
                idempotency_key=str(signature_request.id),
            )
        )
    except OfferSignatureProviderError as error:
        if error.retryable:
            await schedule_outbox_event_retry(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="signature_provider_retryable_error",
                policy=policy,
            )
            return "retried"

        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_provider_terminal_error",
        )
        return "dead_lettered"
    except Exception:  # pylint: disable=broad-exception-caught
        # Never persist provider exception text; it can contain sensitive
        # recipient or provider details.
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_provider_unexpected_error",
            policy=policy,
        )
        return "retried"

    context = TenantContext(
        tenant_id=event.tenant_id,
        subject=f"system:offer-signature-dispatch:{worker_id}",
        roles=frozenset({Role.PEOPLE_OPERATIONS}),
        request_id=f"outbox:{event.id}",
    )

    try:
        await send_offer_signature_request(
            session,
            context=context,
            signature_request_id=signature_request.id,
            expected_version=signature_request.version,
            provider_envelope_reference=envelope.provider_envelope_reference,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # The external provider may already have accepted the request. A retry
        # calls it with the same idempotency key, then completes the DB update.
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="signature_dispatch_persistence_error",
            policy=policy,
        )
        return "retried"

    await mark_outbox_event_processed(
        session,
        event_id=event.id,
        worker_id=worker_id,
    )
    return "processed"


def _event_signature_request_id(event: OutboxEvent) -> UUID | None:
    """Safely parse and validate the minimal public outbox payload."""

    if event.aggregate_type != "offer_signature_request":
        return None

    raw_identifier = event.payload.get("offer_signature_request_id")
    if not isinstance(raw_identifier, str):
        return None

    try:
        return UUID(raw_identifier)
    except ValueError:
        return None


async def _load_signature_request_and_candidate(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    signature_request_id: UUID,
) -> tuple[OfferSignatureRequest, Candidate] | None:
    """Load the dispatch target through fully tenant-scoped joins."""

    result = await session.execute(
        select(OfferSignatureRequest, Candidate)
        .join(Offer, Offer.id == OfferSignatureRequest.offer_id)
        .join(Application, Application.id == Offer.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(
            OfferSignatureRequest.id == signature_request_id,
            OfferSignatureRequest.tenant_id == tenant_id,
            Offer.tenant_id == tenant_id,
            Application.tenant_id == tenant_id,
            Candidate.tenant_id == tenant_id,
        )
    )

    row = result.one_or_none()
    if row is None:
        return None

    return row[0], row[1]
