"""PostgreSQL tests for human-approved candidate-retention execution."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_retention_execution import CandidateRetentionExecution
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.domains.candidates.retention_review import CandidateRetentionReviewChecklist
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewPurpose,
    CandidateRetentionReviewReason,
)
from app.domains.documents.enums import CandidateDocumentStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_retention_execution import (
    execute_candidate_retention_recommendation,
)
from app.services.candidate_retention_execution_errors import (
    CandidateRetentionExecutionAccessDeniedError,
    CandidateRetentionExecutionNotFoundError,
    CandidateRetentionExecutionStateError,
)
from app.services.candidate_retention_holds import place_candidate_retention_hold
from app.services.candidate_retention_reviews import (
    RecordCandidateRetentionReviewCommand,
    record_candidate_retention_review,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id=f"retention-execution-{uuid4().hex}",
    )


async def _seed_review(
    session: AsyncSession,
    *,
    add_document: bool = False,
) -> tuple[UUID, Candidate, CandidateRetentionReview]:
    tenant_id = uuid4()
    now = datetime.now(UTC)
    candidate_id = uuid4()
    email = f"private-{candidate_id.hex}@example.test"
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Retention execution {tenant_id.hex[:10]}",
            slug=f"retention-exec-{tenant_id.hex[:10]}",
        )
    )
    await session.flush()

    candidate = Candidate(
        id=candidate_id,
        tenant_id=tenant_id,
        full_name="Private retention candidate",
        email=email,
        normalized_email=email.casefold(),
        source="direct",
        source_metadata={"private_marker": "must-not-enter-audit"},
        consent_status=CandidateConsentStatus.UNKNOWN,
        privacy_status=CandidatePrivacyStatus.ACTIVE,
        created_by_subject="candidate-creator",
    )
    policy = CandidateRetentionPolicy(
        tenant_id=tenant_id,
        policy_version=1,
        status=CandidateRetentionPolicyStatus.ACTIVE,
        unsuccessful_applicant_days=365,
        withdrawn_applicant_days=365,
        talent_pool_days=365,
        hired_recruiting_copy_days=90,
        created_by_subject="policy-admin",
        activated_by_subject="policy-admin",
        activated_at=now,
    )
    session.add_all([candidate, policy])
    await session.flush()

    if add_document:
        document_id = uuid4()
        session.add(
            CandidateDocument(
                id=document_id,
                tenant_id=tenant_id,
                candidate_id=candidate.id,
                storage_key=(
                    f"v1/tenants/{tenant_id}/candidates/{candidate.id}/"
                    f"documents/{document_id}/content"
                ),
                original_filename="resume.pdf",
                declared_content_type="application/pdf",
                expected_byte_size=100,
                checksum_sha256="a" * 64,
                status=CandidateDocumentStatus.AVAILABLE,
                uploaded_at=now,
                created_by_subject="candidate-creator",
            )
        )
        await session.flush()

    reviewer = _context(
        tenant_id,
        subject="retention-reviewer",
        roles=frozenset({Role.PEOPLE_OPERATIONS}),
    )
    review = await record_candidate_retention_review(
        session,
        context=reviewer,
        candidate_id=candidate.id,
        command=RecordCandidateRetentionReviewCommand(
            policy_id=policy.id,
            purpose=CandidateRetentionReviewPurpose.UNSUCCESSFUL_APPLICANT,
            disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
            reason_code=CandidateRetentionReviewReason.REVIEW_COMPLETE,
            checklist=CandidateRetentionReviewChecklist(
                active_matters_reviewed=True,
                legal_holds_reviewed=True,
                other_lawful_basis_reviewed=True,
                employee_obligations_reviewed=True,
                external_processors_reviewed=True,
                backup_restore_safeguards_reviewed=True,
            ),
            next_review_at=None,
        ),
        reviewed_at=now,
    )
    return tenant_id, candidate, review


@pytest.mark.asyncio
async def test_execution_is_atomic_private_and_idempotent(session: AsyncSession) -> None:
    tenant_id, candidate, review = await _seed_review(session, add_document=True)
    executor = _context(tenant_id, subject="independent-executor")

    execution = await execute_candidate_retention_recommendation(
        session,
        context=executor,
        candidate_id=candidate.id,
        review_id=review.id,
        executed_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    replay = await execute_candidate_retention_recommendation(
        session,
        context=executor,
        candidate_id=candidate.id,
        review_id=review.id,
    )

    assert replay.id == execution.id
    assert execution.review_number == review.review_number
    assert execution.policy_version == review.policy_version
    assert execution.executed_by_subject == executor.subject
    assert execution.executed_at == datetime(2026, 9, 27, tzinfo=UTC)

    stored_candidate = await session.get(Candidate, candidate.id)
    assert stored_candidate is not None
    assert stored_candidate.privacy_status is CandidatePrivacyStatus.ERASURE_PENDING
    assert stored_candidate.email.endswith("@privacy.invalid")

    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "candidate_document.privacy_delete_requested",
            )
        )
    )
    assert len(events) == 1

    executions = list(
        await session.scalars(
            select(CandidateRetentionExecution).where(
                CandidateRetentionExecution.tenant_id == tenant_id,
                CandidateRetentionExecution.candidate_id == candidate.id,
            )
        )
    )
    assert len(executions) == 1

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate.retention_erasure_executed",
            AuditEvent.entity_id == str(execution.id),
        )
    )
    assert audit is not None
    assert audit.details == {
        "review_id": str(review.id),
        "review_number": review.review_number,
        "policy_version": review.policy_version,
    }
    assert "Private retention candidate" not in str(audit.details)
    assert "private-" not in str(audit.details)


@pytest.mark.asyncio
async def test_execution_requires_a_different_authorized_executor(
    session: AsyncSession,
) -> None:
    tenant_id, candidate, review = await _seed_review(session)

    with pytest.raises(CandidateRetentionExecutionAccessDeniedError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(
                tenant_id,
                subject="retention-reviewer",
                roles=frozenset({Role.PEOPLE_OPERATIONS}),
            ),
            candidate_id=candidate.id,
            review_id=review.id,
        )

    with pytest.raises(CandidateRetentionExecutionAccessDeniedError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(
                tenant_id,
                subject="unauthorized-recruiter",
                roles=frozenset({Role.RECRUITER}),
            ),
            candidate_id=candidate.id,
            review_id=review.id,
        )


@pytest.mark.asyncio
async def test_execution_rejects_a_superseded_recommendation(
    session: AsyncSession,
) -> None:
    tenant_id, candidate, review = await _seed_review(session)
    policy = await session.scalar(
        select(CandidateRetentionPolicy).where(
            CandidateRetentionPolicy.tenant_id == tenant_id
        )
    )
    assert policy is not None
    await record_candidate_retention_review(
        session,
        context=_context(
            tenant_id,
            subject="second-reviewer",
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
        ),
        candidate_id=candidate.id,
        command=RecordCandidateRetentionReviewCommand(
            policy_id=policy.id,
            purpose=CandidateRetentionReviewPurpose.UNSUCCESSFUL_APPLICANT,
            disposition=CandidateRetentionReviewDisposition.RETAIN,
            reason_code=CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS,
            checklist=CandidateRetentionReviewChecklist(
                active_matters_reviewed=True,
                legal_holds_reviewed=True,
                other_lawful_basis_reviewed=True,
                employee_obligations_reviewed=True,
                external_processors_reviewed=True,
                backup_restore_safeguards_reviewed=True,
            ),
            next_review_at=datetime.now(UTC) + timedelta(days=30),
        ),
    )

    with pytest.raises(CandidateRetentionExecutionStateError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(tenant_id, subject="independent-executor"),
            candidate_id=candidate.id,
            review_id=review.id,
        )


@pytest.mark.asyncio
async def test_execution_rechecks_holds_and_active_workflows(session: AsyncSession) -> None:
    tenant_id, candidate, review = await _seed_review(session)
    await place_candidate_retention_hold(
        session,
        context=_context(tenant_id, subject="hold-admin"),
        candidate_id=candidate.id,
        reason=CandidateRetentionHoldReason.LEGAL_MATTER,
    )

    with pytest.raises(CandidateRetentionExecutionStateError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(tenant_id, subject="independent-executor"),
            candidate_id=candidate.id,
            review_id=review.id,
        )

    active_hold = await session.scalar(
        select(CandidateRetentionHold).where(
            CandidateRetentionHold.tenant_id == tenant_id,
            CandidateRetentionHold.candidate_id == candidate.id,
            CandidateRetentionHold.released_at.is_(None),
        )
    )
    assert active_hold is not None

    # Release the hold, then verify that a newly active application also blocks execution.
    from app.services.candidate_retention_holds import release_candidate_retention_hold

    await release_candidate_retention_hold(
        session,
        context=_context(tenant_id, subject="hold-admin"),
        hold_id=active_hold.id,
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Active retention-workflow test",
        headcount=1,
        status=RequisitionStatus.CLOSED,
        created_by_subject="retention-execution-test",
    )
    session.add(requisition)
    await session.flush()
    session.add(
        Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.APPLIED,
            created_by_subject="retention-execution-test",
        )
    )
    await session.flush()

    with pytest.raises(CandidateRetentionExecutionStateError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(tenant_id, subject="independent-executor"),
            candidate_id=candidate.id,
            review_id=review.id,
        )


@pytest.mark.asyncio
async def test_execution_hides_cross_tenant_candidate_and_review(
    session: AsyncSession,
) -> None:
    _, candidate, review = await _seed_review(session)

    with pytest.raises(CandidateRetentionExecutionNotFoundError):
        await execute_candidate_retention_recommendation(
            session,
            context=_context(uuid4(), subject="other-tenant-admin"),
            candidate_id=candidate.id,
            review_id=review.id,
        )


@pytest.mark.asyncio
async def test_execution_history_is_database_immutable(session: AsyncSession) -> None:
    tenant_id, candidate, review = await _seed_review(session)
    execution = await execute_candidate_retention_recommendation(
        session,
        context=_context(tenant_id, subject="independent-executor"),
        candidate_id=candidate.id,
        review_id=review.id,
    )
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION prevent_candidate_retention_execution_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'candidate retention execution evidence is immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER trg_candidate_retention_execution_immutable
            BEFORE UPDATE OR DELETE ON candidate_retention_executions
            FOR EACH ROW EXECUTE FUNCTION prevent_candidate_retention_execution_mutation()
            """
        )
    )

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "UPDATE candidate_retention_executions "
                    "SET review_number = review_number + 1 WHERE id = :id"
                ),
                {"id": execution.id},
            )
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text("DELETE FROM candidate_retention_executions WHERE id = :id"),
                {"id": execution.id},
            )


@pytest.mark.asyncio
async def test_concurrent_execution_creates_one_record_and_one_audit(
    session: AsyncSession,
) -> None:
    tenant_id, candidate, review = await _seed_review(session, add_document=True)
    await session.commit()
    session_factory = async_sessionmaker(bind=session.bind, expire_on_commit=False)

    async def execute(subject: str) -> UUID:
        async with session_factory() as concurrent_session:
            result = await execute_candidate_retention_recommendation(
                concurrent_session,
                context=_context(tenant_id, subject=subject),
                candidate_id=candidate.id,
                review_id=review.id,
            )
            return result.id

    first_id, second_id = await asyncio.gather(
        execute("retention-executor-one"),
        execute("retention-executor-two"),
    )
    assert first_id == second_id

    executions = list(
        await session.scalars(
            select(CandidateRetentionExecution).where(
                CandidateRetentionExecution.tenant_id == tenant_id,
                CandidateRetentionExecution.candidate_id == candidate.id,
            )
        )
    )
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.retention_erasure_executed",
                AuditEvent.entity_id == str(first_id),
            )
        )
    )
    outbox_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "candidate_document.privacy_delete_requested",
            )
        )
    )
    assert len(executions) == len(audits) == len(outbox_events) == 1
