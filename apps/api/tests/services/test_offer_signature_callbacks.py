"""PostgreSQL tests for verified offer-signature provider callbacks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.db.models.offer_signature_callback import (
    OfferSignatureCallbackReceipt,
)
from app.domains.signatures.enums import (
    OfferSignatureCallbackEventType,
    OfferSignatureEventType,
    OfferSignatureStatus,
)
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerificationRequest,
    VerifiedOfferSignatureCallback,
)
from app.services.offer_signature_callbacks import (
    process_offer_signature_callback,
)
from app.services.offer_signature_errors import (
    OfferSignatureCallbackReplayMismatchError,
    OfferSignatureCallbackVerificationError,
)
from app.services.offer_signatures import (
    CreateOfferSignatureRequestCommand,
    create_offer_signature_request,
    send_offer_signature_request,
)
from tests.services.test_offer_signatures import _seed_approved_offer


class _FakeVerifier:
    """Test verifier that returns already-verified, privacy-safe event facts."""

    provider = "local"

    def __init__(
        self,
        *,
        event_id: str,
        envelope_reference: str,
        event_type: OfferSignatureCallbackEventType,
        occurred_at: datetime,
        error: Exception | None = None,
    ) -> None:
        self.event_id = event_id
        self.envelope_reference = envelope_reference
        self.event_type = event_type
        self.occurred_at = occurred_at
        self.error = error
        self.requests: list[OfferSignatureCallbackVerificationRequest] = []

    async def verify(
        self,
        request: OfferSignatureCallbackVerificationRequest,
    ) -> VerifiedOfferSignatureCallback:
        """Return verified data or simulate signature verification failure."""
        self.requests.append(request)

        if self.error is not None:
            raise self.error

        return VerifiedOfferSignatureCallback(
            provider_event_id=self.event_id,
            provider_envelope_reference=self.envelope_reference,
            event_type=self.event_type,
            occurred_at=self.occurred_at,
        )


def _context(tenant_id: UUID) -> TenantContext:
    """Build a trusted caller for initial signature-request setup."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="offer-signature-callback-test-request-id",
    )


def _verification_request(
    body: bytes = b'{"event":"signed","signer":"private@example.test"}',
) -> OfferSignatureCallbackVerificationRequest:
    """Build an intentionally private raw provider callback request."""
    return OfferSignatureCallbackVerificationRequest(
        raw_body=body,
        headers={
            "X-Provider-Signature": "must-never-be-persisted-or-logged",
        },
        received_at=datetime.now(UTC),
    )


async def _seed_sent_signature_request(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> OfferSignatureRequest:
    """Create an approved offer and a sent local-provider signature envelope."""
    offer = await _seed_approved_offer(session, tenant_id=tenant_id)
    context = _context(tenant_id)

    signature_request = await create_offer_signature_request(
        session,
        context=context,
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="local",
            document_reference="private-document-reference",
        ),
    )

    signature_request = await send_offer_signature_request(
        session,
        context=context,
        signature_request_id=signature_request.id,
        expected_version=signature_request.version,
        provider_envelope_reference=f"envelope-{signature_request.id}",
    )
    await session.commit()
    return signature_request


async def _install_receipt_immutability_trigger(
    session: AsyncSession,
) -> None:
    """Install production immutability enforcement for metadata-created tables."""
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION
            prevent_offer_signature_callback_receipt_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'offer signature callback receipts are immutable';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER trg_prevent_offer_signature_callback_receipt_mutation
            BEFORE UPDATE OR DELETE ON offer_signature_callback_receipts
            FOR EACH ROW
            EXECUTE FUNCTION prevent_offer_signature_callback_receipt_mutation();
            """
        )
    )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "expected_status"),
    [
        (
            OfferSignatureCallbackEventType.SIGNED,
            OfferSignatureStatus.SIGNED,
        ),
        (
            OfferSignatureCallbackEventType.DECLINED,
            OfferSignatureStatus.DECLINED,
        ),
        (
            OfferSignatureCallbackEventType.VOIDED,
            OfferSignatureStatus.VOIDED,
        ),
    ],
)
async def test_applies_verified_callback_lifecycle_outcomes(
    session: AsyncSession,
    event_type: OfferSignatureCallbackEventType,
    expected_status: OfferSignatureStatus,
) -> None:
    """Apply each verified provider outcome atomically."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )

    result = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id=f"event-{event_type.value}",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=event_type,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(),
        request_id="provider-request-id",
    )

    persisted = await session.get(OfferSignatureRequest, signature_request.id)
    receipt = await session.get(OfferSignatureCallbackReceipt, result.receipt_id)

    assert result.replayed is False
    assert result.applied is True
    assert persisted is not None
    assert persisted.status is expected_status
    assert receipt is not None
    assert receipt.event_type is event_type


@pytest.mark.asyncio
async def test_replays_same_callback_without_duplicate_history_or_audit(
    session: AsyncSession,
) -> None:
    """A provider retry returns the original receipt without another mutation."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )
    request = _verification_request()
    verifier = _FakeVerifier(
        event_id="provider-event-1",
        envelope_reference=signature_request.provider_envelope_reference or "",
        event_type=OfferSignatureCallbackEventType.SIGNED,
        occurred_at=datetime.now(UTC),
    )

    first = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=verifier,
        verification_request=request,
        request_id="provider-request-1",
    )
    replay = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=verifier,
        verification_request=request,
        request_id="provider-request-2",
    )

    receipt_count = len(
        (
            await session.execute(
                select(OfferSignatureCallbackReceipt.id).where(
                    OfferSignatureCallbackReceipt.offer_signature_request_id
                    == signature_request.id
                )
            )
        )
        .scalars()
        .all()
    )
    signed_history_count = len(
        (
            await session.execute(
                select(OfferSignatureHistory.id).where(
                    OfferSignatureHistory.offer_signature_request_id
                    == signature_request.id,
                    OfferSignatureHistory.to_status == OfferSignatureStatus.SIGNED,
                )
            )
        )
        .scalars()
        .all()
    )

    assert first.replayed is False
    assert first.applied is True
    assert replay.replayed is True
    assert replay.applied is False
    assert replay.receipt_id == first.receipt_id
    assert receipt_count == 1
    assert signed_history_count == 1


@pytest.mark.asyncio
async def test_rejects_mutated_replay_with_same_provider_event_id(
    session: AsyncSession,
) -> None:
    """A reused provider event ID must retain exactly the original content."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )

    await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="provider-event-1",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=OfferSignatureCallbackEventType.SIGNED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(b'{"event":"signed"}'),
        request_id="provider-request-1",
    )

    with pytest.raises(OfferSignatureCallbackReplayMismatchError):
        await process_offer_signature_callback(
            session,
            provider="local",
            verifier=_FakeVerifier(
                event_id="provider-event-1",
                envelope_reference=signature_request.provider_envelope_reference or "",
                event_type=OfferSignatureCallbackEventType.DECLINED,
                occurred_at=datetime.now(UTC),
            ),
            verification_request=_verification_request(b'{"event":"declined"}'),
            request_id="provider-request-2",
        )


@pytest.mark.asyncio
async def test_retains_late_callback_but_does_not_overwrite_terminal_status(
    session: AsyncSession,
) -> None:
    """A valid late provider event is receipted but cannot alter a terminal state."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )

    await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="signed-event",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=OfferSignatureCallbackEventType.SIGNED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(b'{"event":"signed"}'),
        request_id="provider-request-1",
    )

    late = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="declined-event",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=OfferSignatureCallbackEventType.DECLINED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(b'{"event":"declined"}'),
        request_id="provider-request-2",
    )

    persisted = await session.get(OfferSignatureRequest, signature_request.id)
    receipt_count = len(
        (
            await session.execute(
                select(OfferSignatureCallbackReceipt.id).where(
                    OfferSignatureCallbackReceipt.offer_signature_request_id
                    == signature_request.id
                )
            )
        )
        .scalars()
        .all()
    )

    assert late.replayed is False
    assert late.applied is False
    assert persisted is not None
    assert persisted.status is OfferSignatureStatus.SIGNED
    assert receipt_count == 2


@pytest.mark.asyncio
async def test_rejects_verification_failure_without_persisting_callback(
    session: AsyncSession,
) -> None:
    """Unverified data cannot create receipts or mutate signature state."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )

    with pytest.raises(OfferSignatureCallbackVerificationError):
        await process_offer_signature_callback(
            session,
            provider="local",
            verifier=_FakeVerifier(
                event_id="ignored",
                envelope_reference=signature_request.provider_envelope_reference or "",
                event_type=OfferSignatureCallbackEventType.SIGNED,
                occurred_at=datetime.now(UTC),
                error=OfferSignatureCallbackVerificationError(
                    "provider_signature_invalid"
                ),
            ),
            verification_request=_verification_request(),
            request_id="provider-request-id",
        )

    receipt_count = len(
        (
            await session.execute(
                select(OfferSignatureCallbackReceipt.id)
            )
        )
        .scalars()
        .all()
    )
    persisted = await session.get(OfferSignatureRequest, signature_request.id)

    assert receipt_count == 0
    assert persisted is not None
    assert persisted.status is OfferSignatureStatus.SENT


@pytest.mark.asyncio
async def test_implicitly_marks_draft_requests_sent_before_final_callback_state(
    session: AsyncSession,
) -> None:
    """A valid callback can advance a draft request through the required send step."""
    tenant_id = uuid4()
    offer = await _seed_approved_offer(session, tenant_id=tenant_id)
    context = _context(tenant_id)

    signature_request = await create_offer_signature_request(
        session,
        context=context,
        offer_id=offer.id,
        expected_offer_version=offer.version,
        command=CreateOfferSignatureRequestCommand(
            provider="local",
            document_reference="private-document-reference",
        ),
    )
    signature_request.provider_envelope_reference = "envelope-draft-request"
    await session.commit()

    result = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="draft-callback-event",
            envelope_reference="envelope-draft-request",
            event_type=OfferSignatureCallbackEventType.SIGNED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(),
        request_id="provider-request-id",
    )

    persisted = await session.get(OfferSignatureRequest, signature_request.id)
    sent_history = await session.scalar(
        select(OfferSignatureHistory).where(
            OfferSignatureHistory.offer_signature_request_id == signature_request.id,
            OfferSignatureHistory.event_type == OfferSignatureEventType.SENT,
        )
    )

    assert result.applied is True
    assert persisted is not None
    assert persisted.status is OfferSignatureStatus.SIGNED
    assert sent_history is not None
    assert sent_history.from_status is OfferSignatureStatus.DRAFT
    assert sent_history.to_status is OfferSignatureStatus.SENT


@pytest.mark.asyncio
async def test_receipt_and_audit_never_store_raw_callback_or_signer_pii(
    session: AsyncSession,
) -> None:
    """Persist only safe callback metadata and a non-reversible body digest."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )
    raw_body = (
        b'{"event":"signed","signer_email":"private@example.test",'
        b'"signing_url":"https://private.example.test/sign"}'
    )

    result = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="privacy-event",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=OfferSignatureCallbackEventType.SIGNED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(raw_body),
        request_id="provider-request-id",
    )

    receipt = await session.get(OfferSignatureCallbackReceipt, result.receipt_id)
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "offer_signature.signed",
            AuditEvent.entity_id == str(signature_request.id),
        )
    )

    assert receipt is not None
    assert audit is not None

    serialized_receipt = str(
        {
            "provider": receipt.provider,
            "provider_event_id": receipt.provider_event_id,
            "provider_envelope_reference": receipt.provider_envelope_reference,
            "event_type": receipt.event_type.value,
            "payload_sha256": receipt.payload_sha256,
        }
    )
    serialized_audit = str(audit.details)

    for prohibited_value in (
        "private@example.test",
        "https://private.example.test/sign",
        "X-Provider-Signature",
        "must-never-be-persisted-or-logged",
        "signer_email",
    ):
        assert prohibited_value not in serialized_receipt
        assert prohibited_value not in serialized_audit


@pytest.mark.asyncio
async def test_database_trigger_rejects_callback_receipt_mutation(
    session: AsyncSession,
) -> None:
    """Callback receipts remain append-only under direct SQL access."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )
    await _install_receipt_immutability_trigger(session)

    result = await process_offer_signature_callback(
        session,
        provider="local",
        verifier=_FakeVerifier(
            event_id="immutable-event",
            envelope_reference=signature_request.provider_envelope_reference or "",
            event_type=OfferSignatureCallbackEventType.SIGNED,
            occurred_at=datetime.now(UTC),
        ),
        verification_request=_verification_request(),
        request_id="provider-request-id",
    )

    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                """
                UPDATE offer_signature_callback_receipts
                SET provider_event_id = 'mutated'
                WHERE id = :receipt_id
                """
            ),
            {"receipt_id": result.receipt_id},
        )

    await session.rollback()


@pytest_asyncio.fixture(name="callback_session_factory")
async def callback_session_factory_fixture(
    database_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide independent sessions for concurrent provider delivery tests."""
    yield async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.mark.asyncio
async def test_concurrent_duplicate_delivery_creates_one_receipt_and_one_transition(
    session: AsyncSession,
    callback_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Concurrent provider retries serialize safely on the signature request row."""
    tenant_id = uuid4()
    signature_request = await _seed_sent_signature_request(
        session,
        tenant_id=tenant_id,
    )
    raw_request = _verification_request(b'{"event":"signed","event_id":"same"}')

    async def deliver(request_id: str):
        async with callback_session_factory() as callback_session:
            return await process_offer_signature_callback(
                callback_session,
                provider="local",
                verifier=_FakeVerifier(
                    event_id="concurrent-event",
                    envelope_reference=signature_request.provider_envelope_reference
                    or "",
                    event_type=OfferSignatureCallbackEventType.SIGNED,
                    occurred_at=datetime.now(UTC),
                ),
                verification_request=raw_request,
                request_id=request_id,
            )

    first, second = await asyncio.gather(
        deliver("provider-request-1"),
        deliver("provider-request-2"),
    )

    verification_session_factory = callback_session_factory
    async with verification_session_factory() as verification_session:
        receipt_count = len(
            (
                await verification_session.execute(
                    select(OfferSignatureCallbackReceipt.id)
                )
            )
            .scalars()
            .all()
        )
        signed_history_count = len(
            (
                await verification_session.execute(
                    select(OfferSignatureHistory.id).where(
                        OfferSignatureHistory.offer_signature_request_id
                        == signature_request.id,
                        OfferSignatureHistory.to_status
                        == OfferSignatureStatus.SIGNED,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert {first.replayed, second.replayed} == {False, True}
    assert receipt_count == 1
    assert signed_history_count == 1
