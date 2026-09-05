"""PostgreSQL integration tests for candidate and application services."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_errors import (
    ApplicationAlreadyExistsError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
    RequisitionNotAcceptingApplicationsError,
)
from app.services.candidates import (
    CreateApplicationCommand,
    CreateCandidateCommand,
    create_application,
    create_candidate,
    get_candidate,
)


def _context(tenant_id: UUID) -> TenantContext:
    """Build a recruiter context for candidate service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Create one tenant required by candidate and requisition foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


async def _create_requisition(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    status: RequisitionStatus,
) -> Requisition:
    """Create a requisition directly for application-service preconditions."""
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=status,
        created_by_subject="recruiter-subject",
    )
    session.add(requisition)
    await session.commit()

    return requisition


def _candidate_command(email: str) -> CreateCandidateCommand:
    """Create representative candidate input without adding PII to audit tests."""
    return CreateCandidateCommand(
        full_name="Ada Lovelace",
        email=email,
        source="employee_referral",
        phone="+254700000000",
        location="Nairobi",
        source_metadata={"referral_program": "engineering-q3"},
        consent_status=CandidateConsentStatus.GRANTED,
    )


@pytest.mark.asyncio
async def test_deduplicates_canonical_email_within_a_tenant(
    session: AsyncSession,
) -> None:
    """Reject duplicate candidate emails within the same tenant."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    candidate = await create_candidate(
        session,
        context=context,
        command=_candidate_command("Ada.Lovelace@Acme.IO"),
    )
    await session.refresh(candidate)
    candidate_id = candidate.id
    candidate_email = candidate.email
    normalized_email = candidate.normalized_email

    with pytest.raises(CandidateAlreadyExistsError):
        await create_candidate(
            session,
            context=context,
            command=_candidate_command("  ada.lovelace@acme.io  "),
        )

    candidate_count = await session.scalar(
        select(count()).select_from(Candidate)
    )
    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == str(candidate_id))
        )
    )

    assert candidate_email == "Ada.Lovelace@acme.io"
    assert normalized_email == "ada.lovelace@acme.io"
    assert candidate_count == 1
    assert [event.action for event in audit_events] == ["candidate.created"]


@pytest.mark.asyncio
async def test_hides_candidate_owned_by_another_tenant(
    session: AsyncSession,
) -> None:
    """Hide candidates that belong to another tenant."""
    owning_tenant_id = uuid4()
    await _create_tenant(session, owning_tenant_id)

    candidate = await create_candidate(
        session,
        context=_context(owning_tenant_id),
        command=_candidate_command("ada@acme.io"),
    )

    with pytest.raises(CandidateNotFoundError):
        await get_candidate(
            session,
            context=_context(uuid4()),
            candidate_id=candidate.id,
        )


@pytest.mark.asyncio
async def test_rejects_application_to_requisition_that_is_not_open(
    session: AsyncSession,
) -> None:
    """Reject applications for requisitions that are not open."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    candidate = await create_candidate(
        session,
        context=context,
        command=_candidate_command("ada@acme.io"),
    )
    requisition = await _create_requisition(
        session,
        tenant_id=tenant_id,
        status=RequisitionStatus.DRAFT,
    )

    with pytest.raises(RequisitionNotAcceptingApplicationsError):
        await create_application(
            session,
            context=context,
            command=CreateApplicationCommand(
                candidate_id=candidate.id,
                requisition_id=requisition.id,
            ),
        )

    application_count = await session.scalar(
        select(count()).select_from(Application)
    )

    assert application_count == 0


@pytest.mark.asyncio
async def test_creates_one_application_and_records_privacy_safe_audit_event(
    session: AsyncSession,
) -> None:
    """Create one application and record a privacy-safe audit event."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    candidate = await create_candidate(
        session,
        context=context,
        command=_candidate_command("ada@acme.io"),
    )
    requisition = await _create_requisition(
        session,
        tenant_id=tenant_id,
        status=RequisitionStatus.OPEN,
    )

    application = await create_application(
        session,
        context=context,
        command=CreateApplicationCommand(
            candidate_id=candidate.id,
            requisition_id=requisition.id,
        ),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(application.id),
            AuditEvent.action == "application.created",
        )
    )

    assert application.candidate_id == candidate.id
    assert application.requisition_id == requisition.id
    assert audit_event is not None
    assert audit_event.details == {
        "candidate_id": str(candidate.id),
        "requisition_id": str(requisition.id),
        "status": "applied",
    }
    assert "email" not in audit_event.details
    assert "phone" not in audit_event.details


@pytest.mark.asyncio
async def test_rejects_duplicate_application_for_same_candidate_and_requisition(
    session: AsyncSession,
) -> None:
    """Reject duplicate applications for a candidate and requisition pair."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    candidate = await create_candidate(
        session,
        context=context,
        command=_candidate_command("ada@acme.io"),
    )
    requisition = await _create_requisition(
        session,
        tenant_id=tenant_id,
        status=RequisitionStatus.OPEN,
    )
    command = CreateApplicationCommand(
        candidate_id=candidate.id,
        requisition_id=requisition.id,
    )

    await create_application(
        session,
        context=context,
        command=command,
    )

    with pytest.raises(ApplicationAlreadyExistsError):
        await create_application(
            session,
            context=context,
            command=command,
        )

    application_count = await session.scalar(
        select(count()).select_from(Application)
    )
    application_audit_count = await session.scalar(
        select(count()).select_from(AuditEvent).where(
            AuditEvent.action == "application.created"
        )
    )

    assert application_count == 1
    assert application_audit_count == 1


@pytest.mark.asyncio
async def test_does_not_allow_cross_tenant_candidate_application(
    session: AsyncSession,
) -> None:
    """Reject applications using a candidate from another tenant."""
    candidate_tenant_id = uuid4()
    requisition_tenant_id = uuid4()

    await _create_tenant(session, candidate_tenant_id)
    await _create_tenant(session, requisition_tenant_id)

    candidate = await create_candidate(
        session,
        context=_context(candidate_tenant_id),
        command=_candidate_command("ada@acme.io"),
    )
    requisition = await _create_requisition(
        session,
        tenant_id=requisition_tenant_id,
        status=RequisitionStatus.OPEN,
    )

    with pytest.raises(CandidateNotFoundError):
        await create_application(
            session,
            context=_context(requisition_tenant_id),
            command=CreateApplicationCommand(
                candidate_id=candidate.id,
                requisition_id=requisition.id,
            ),
        )

    application_count = await session.scalar(
        select(count()).select_from(Application)
    )

    assert application_count == 0
