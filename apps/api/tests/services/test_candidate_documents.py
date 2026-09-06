"""PostgreSQL integration tests for candidate document upload intents."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.candidate_document import CandidateDocument
from app.db.models.identity import Tenant
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.candidate_documents import (
    CreateCandidateDocumentUploadIntentCommand,
    create_candidate_document_upload_intent,
)
from app.services.candidate_errors import CandidateAccessDeniedError, CandidateNotFoundError
from app.services.candidates import (
    CreateCandidateCommand,
    create_candidate,
)


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for document-service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Create the tenant required by document foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


async def _create_candidate_for_tenant(
    session: AsyncSession,
    tenant_id: UUID,
):
    """Create a candidate using the production candidate service."""
    return await create_candidate(
        session,
        context=_context(tenant_id),
        command=CreateCandidateCommand(
            full_name="Ada Lovelace",
            email="ada.lovelace@acme.io",
            source="employee_referral",
        ),
    )


def _command(*, candidate_id: UUID) -> CreateCandidateDocumentUploadIntentCommand:
    """Build representative safe document-upload metadata."""
    return CreateCandidateDocumentUploadIntentCommand(
        candidate_id=candidate_id,
        original_filename="Ada-Lovelace-Resume.pdf",
        declared_content_type="application/pdf",
        expected_byte_size=512_000,
        checksum_sha256="a" * 64,
    )


@pytest.mark.asyncio
async def test_creates_pending_upload_intent_with_server_owned_key_and_audit_event(
    session: AsyncSession,
) -> None:
    """Create a pending record without placing PII in its storage key or audit event."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate_for_tenant(session, tenant_id)

    document = await create_candidate_document_upload_intent(
        session,
        context=_context(tenant_id),
        command=_command(candidate_id=candidate.id),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate_document.upload_intent_created",
            AuditEvent.entity_id == str(document.id),
        )
    )

    assert document.tenant_id == tenant_id
    assert document.candidate_id == candidate.id
    assert document.status is CandidateDocumentStatus.PENDING_UPLOAD
    assert document.storage_key == (
        f"v1/tenants/{tenant_id}/candidates/{candidate.id}/"
        f"documents/{document.id}/content"
    )
    assert "Ada-Lovelace-Resume.pdf" not in document.storage_key
    assert "ada.lovelace@acme.io" not in document.storage_key

    assert audit_event is not None
    assert audit_event.details == {
        "candidate_id": str(candidate.id),
        "content_type": "application/pdf",
        "expected_byte_size": 512_000,
    }
    assert "filename" not in audit_event.details
    assert "checksum" not in audit_event.details


@pytest.mark.asyncio
async def test_hides_candidate_from_another_tenant_when_creating_upload_intent(
    session: AsyncSession,
) -> None:
    """Prevent document creation for a candidate owned by a different tenant."""
    owning_tenant_id = uuid4()
    caller_tenant_id = uuid4()

    await _create_tenant(session, owning_tenant_id)
    await _create_tenant(session, caller_tenant_id)
    candidate = await _create_candidate_for_tenant(session, owning_tenant_id)

    with pytest.raises(CandidateNotFoundError):
        await create_candidate_document_upload_intent(
            session,
            context=_context(caller_tenant_id),
            command=_command(candidate_id=candidate.id),
        )

    documents = list(await session.scalars(select(CandidateDocument)))
    document_audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate_document.upload_intent_created"
            )
        )
    )

    assert not documents
    assert not document_audits


@pytest.mark.asyncio
async def test_rejects_unauthorized_role_without_creating_document(
    session: AsyncSession,
) -> None:
    """Allow only recruiting and people-operations roles to manage documents."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate_for_tenant(session, tenant_id)

    with pytest.raises(CandidateAccessDeniedError):
        await create_candidate_document_upload_intent(
            session,
            context=_context(tenant_id, frozenset({Role.INTERVIEWER})),
            command=_command(candidate_id=candidate.id),
        )

    documents = list(await session.scalars(select(CandidateDocument)))
    assert not documents


@pytest.mark.parametrize(
    ("content_type", "expected_byte_size", "checksum_sha256"),
    [
        ("image/png", 512_000, "a" * 64),
        ("application/pdf", 0, "a" * 64),
        ("application/pdf", (10 * 1024 * 1024) + 1, "a" * 64),
        ("application/pdf", 512_000, "not-a-sha256-checksum"),
    ],
)
def test_rejects_invalid_upload_intent_metadata(
    content_type: str,
    expected_byte_size: int,
    checksum_sha256: str,
) -> None:
    """Reject unsupported types, invalid sizes, and malformed checksums."""
    with pytest.raises(ValueError):
        CreateCandidateDocumentUploadIntentCommand(
            candidate_id=uuid4(),
            original_filename="resume.pdf",
            declared_content_type=content_type,
            expected_byte_size=expected_byte_size,
            checksum_sha256=checksum_sha256,
        )


@pytest.mark.parametrize(
    "content_type",
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
)
def test_accepts_supported_document_content_types(content_type: str) -> None:
    """Allow only the explicit resume document formats."""
    command = CreateCandidateDocumentUploadIntentCommand(
        candidate_id=uuid4(),
        original_filename="resume",
        declared_content_type=content_type,
        expected_byte_size=512_000,
        checksum_sha256="a" * 64,
    )

    assert command.declared_content_type == content_type
