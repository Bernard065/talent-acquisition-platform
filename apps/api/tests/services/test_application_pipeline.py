"""PostgreSQL integration tests for application pipeline transitions."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.application_pipeline import (
    TransitionApplicationStageCommand,
    transition_application_stage,
)
from app.services.application_pipeline_errors import (
    ApplicationPipelineAccessDeniedError,
    ApplicationRejectionReasonError,
    ApplicationVersionConflictError,
)
from app.services.candidate_errors import ApplicationNotFoundError


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for pipeline-service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="application-pipeline-test-request-id",
    )


async def _create_application(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> Application:
    """Seed one applied application and its immutable initial history event."""
    candidate_id = uuid4()
    requisition_id = uuid4()
    application_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name=f"Pipeline Tenant {tenant_id.hex[:12]}",
        slug=f"pipeline-{tenant_id.hex[:12]}",
    )
    session.add(tenant)
    await session.flush()

    session.add(
        Candidate(
            id=candidate_id,
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:10]}@example.test",
            normalized_email=f"ada-{tenant_id.hex[:10]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="recruiter-subject",
        )
    )
    session.add(
        Requisition(
            id=requisition_id,
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="recruiter-subject",
        )
    )
    await session.flush()

    application = Application(
        id=application_id,
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        requisition_id=requisition_id,
        status=ApplicationStatus.APPLIED,
        created_by_subject="recruiter-subject",
    )
    session.add(application)
    await session.flush()

    session.add(
        ApplicationStageHistory(
            tenant_id=tenant_id,
            application_id=application.id,
            from_status=None,
            to_status=ApplicationStatus.APPLIED,
            transitioned_by_subject="recruiter-subject",
        )
    )
    await session.commit()

    return application


@pytest.mark.asyncio
async def test_transitions_application_and_appends_history_and_audit_event(
    session: AsyncSession,
) -> None:
    """Move an application forward with versioned state, history, and audit data."""
    tenant_id = uuid4()
    application = await _create_application(session, tenant_id=tenant_id)

    transitioned = await transition_application_stage(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        command=TransitionApplicationStageCommand(
            target_status=ApplicationStatus.SCREENING,
            expected_version=1,
        ),
    )

    histories = list(
        await session.scalars(
            select(ApplicationStageHistory).where(
                ApplicationStageHistory.application_id == application.id
            )
        )
    )
    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(application.id),
            AuditEvent.action == "application.stage_changed",
        )
    )

    assert transitioned.status is ApplicationStatus.SCREENING
    assert transitioned.version == 2
    assert len(histories) == 2

    initial_history = next(
        item for item in histories if item.to_status is ApplicationStatus.APPLIED
    )
    transition_history = next(
        item for item in histories if item.to_status is ApplicationStatus.SCREENING
    )

    assert initial_history.from_status is None
    assert transition_history.from_status is ApplicationStatus.APPLIED
    assert transition_history.rejection_reason is None

    assert audit_event is not None
    assert audit_event.details == {
        "previous_status": "applied",
        "target_status": "screening",
        "rejection_reason": None,
        "version": 2,
    }


@pytest.mark.asyncio
async def test_requires_controlled_reason_when_rejecting() -> None:
    """Require a reason only for the rejected terminal stage."""
    with pytest.raises(ApplicationRejectionReasonError):
        TransitionApplicationStageCommand(
            target_status=ApplicationStatus.REJECTED,
            expected_version=1,
        )

    with pytest.raises(ApplicationRejectionReasonError):
        TransitionApplicationStageCommand(
            target_status=ApplicationStatus.SCREENING,
            expected_version=1,
            rejection_reason=ApplicationRejectionReason.NOT_QUALIFIED,
        )


@pytest.mark.asyncio
async def test_records_rejection_reason_in_history_and_audit(
    session: AsyncSession,
) -> None:
    """Persist controlled rejection metadata without candidate PII."""
    tenant_id = uuid4()
    application = await _create_application(session, tenant_id=tenant_id)

    rejected = await transition_application_stage(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        command=TransitionApplicationStageCommand(
            target_status=ApplicationStatus.REJECTED,
            expected_version=1,
            rejection_reason=ApplicationRejectionReason.NOT_QUALIFIED,
        ),
    )

    history = await session.scalar(
        select(ApplicationStageHistory).where(
            ApplicationStageHistory.application_id == application.id,
            ApplicationStageHistory.to_status == ApplicationStatus.REJECTED,
        )
    )
    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(application.id),
            AuditEvent.action == "application.stage_changed",
        )
    )

    assert rejected.status is ApplicationStatus.REJECTED
    assert history is not None
    assert history.rejection_reason is ApplicationRejectionReason.NOT_QUALIFIED
    assert audit_event is not None
    assert audit_event.details["rejection_reason"] == "not_qualified"


@pytest.mark.asyncio
async def test_rejects_stale_application_version(
    session: AsyncSession,
) -> None:
    """Require callers to transition the version they actually read."""
    tenant_id = uuid4()
    application = await _create_application(session, tenant_id=tenant_id)

    with pytest.raises(ApplicationVersionConflictError):
        await transition_application_stage(
            session,
            context=_context(tenant_id),
            application_id=application.id,
            command=TransitionApplicationStageCommand(
                target_status=ApplicationStatus.SCREENING,
                expected_version=2,
            ),
        )

    await session.refresh(application)
    assert application.status is ApplicationStatus.APPLIED
    assert application.version == 1


@pytest.mark.asyncio
async def test_requires_pipeline_write_role(
    session: AsyncSession,
) -> None:
    """Reject stage changes by roles without candidate workflow access."""
    tenant_id = uuid4()
    application = await _create_application(session, tenant_id=tenant_id)

    with pytest.raises(ApplicationPipelineAccessDeniedError):
        await transition_application_stage(
            session,
            context=_context(
                tenant_id,
                frozenset({Role.INTERVIEWER}),
            ),
            application_id=application.id,
            command=TransitionApplicationStageCommand(
                target_status=ApplicationStatus.SCREENING,
                expected_version=1,
            ),
        )

    await session.refresh(application)
    assert application.status is ApplicationStatus.APPLIED


@pytest.mark.asyncio
async def test_hides_application_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Return not-found when another tenant tries to transition an application."""
    owner_tenant_id = uuid4()
    caller_tenant_id = uuid4()
    application = await _create_application(
        session,
        tenant_id=owner_tenant_id,
    )

    with pytest.raises(ApplicationNotFoundError):
        await transition_application_stage(
            session,
            context=_context(caller_tenant_id),
            application_id=application.id,
            command=TransitionApplicationStageCommand(
                target_status=ApplicationStatus.SCREENING,
                expected_version=1,
            ),
        )
