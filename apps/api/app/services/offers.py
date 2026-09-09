"""Transactional, tenant-safe offer and offer-approval workflow."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.approval import ApprovalPolicy, ApprovalPolicyStep
from app.db.models.identity import User
from app.db.models.offer import Offer, OfferLifecycleHistory
from app.db.models.offer_approval import OfferApproval, OfferApprovalDecision
from app.db.transactions import transactional
from app.domains.applications.transitions import validate_application_transition
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.candidates.enums import ApplicationStatus
from app.domains.offers.enums import (
    OfferLifecycleEventType,
    OfferPayPeriod,
    OfferStatus,
)
from app.domains.offers.transitions import validate_offer_transition
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.offer_errors import (
    OfferAccessDeniedError,
    OfferAlreadyExistsError,
    OfferApplicationNotEligibleError,
    OfferApprovalAlreadyCompleteError,
    OfferApprovalForbiddenError,
    OfferApprovalNotFoundError,
    OfferNotFoundError,
    OfferSelfApprovalError,
    OfferValidationError,
    OfferVersionConflictError,
)

_OFFER_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_MAX_EQUITY_SUMMARY_LENGTH = 5_000
_MAX_APPROVAL_COMMENT_LENGTH = 5_000


@dataclass(frozen=True, slots=True)
class CreateOfferCommand:
    """Validated compensation and expiry data for a draft offer."""

    currency: str
    base_salary: Decimal
    pay_period: OfferPayPeriod
    proposed_start_date: date
    expires_at: datetime
    bonus_amount: Decimal | None = None
    equity_summary: str | None = None

    def __post_init__(self) -> None:
        normalized_currency = self.currency.strip().upper()

        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise OfferValidationError(
                "Currency must be a three-letter ISO 4217-style code."
            )

        if self.base_salary <= 0:
            raise OfferValidationError("Base salary must be greater than zero.")

        if self.bonus_amount is not None and self.bonus_amount < 0:
            raise OfferValidationError("Bonus amount cannot be negative.")

        if self.expires_at.tzinfo is None:
            raise OfferValidationError("Offer expiry must include a UTC offset.")

        if self.expires_at <= datetime.now(UTC):
            raise OfferValidationError("Offer expiry must be in the future.")

        normalized_equity = (
            self.equity_summary.strip() if self.equity_summary is not None else None
        )
        if normalized_equity == "":
            normalized_equity = None

        if (
            normalized_equity is not None
            and len(normalized_equity) > _MAX_EQUITY_SUMMARY_LENGTH
        ):
            raise OfferValidationError(
                "Equity summary must not exceed 5000 characters."
            )

        object.__setattr__(self, "currency", normalized_currency)
        object.__setattr__(self, "equity_summary", normalized_equity)


def _require_offer_write_access(context: TenantContext) -> None:
    """Restrict operational offer actions to recruiting operations roles."""
    if context.roles.isdisjoint(_OFFER_WRITE_ROLES):
        raise OfferAccessDeniedError(
            "Caller is not permitted to perform this offer operation."
        )


def _validate_expected_version(offer: Offer, expected_version: int) -> None:
    """Reject stale writes before changing the locked offer."""
    if expected_version < 1:
        raise OfferValidationError("Expected offer version must be at least 1.")

    if offer.version != expected_version:
        raise OfferVersionConflictError(
            "Offer has changed since the supplied version."
        )


def _append_lifecycle_history(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer: Offer,
    event_type: OfferLifecycleEventType,
    from_status: OfferStatus | None,
    to_status: OfferStatus,
) -> None:
    """Append a lifecycle row; the database migration makes it immutable."""
    session.add(
        OfferLifecycleHistory(
            tenant_id=context.tenant_id,
            offer_id=offer.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            occurred_by_subject=context.subject,
        )
    )


async def _load_offer_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
) -> Offer:
    """Load and lock one tenant-owned offer."""
    offer = await session.scalar(
        select(Offer)
        .where(
            Offer.id == offer_id,
            Offer.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if offer is None:
        raise OfferNotFoundError("Offer was not found.")

    return offer


async def create_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: CreateOfferCommand,
) -> Offer:
    """Create one draft offer for an application already in the offer stage."""
    _require_offer_write_access(context)

    async with transactional(session):
        application = await session.scalar(
            select(Application)
            .where(
                Application.id == application_id,
                Application.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if application is None:
            raise ApplicationNotFoundError("Application was not found.")

        if application.status is not ApplicationStatus.OFFER:
            raise OfferApplicationNotEligibleError(
                "Only applications in the offer stage can receive an offer."
            )

        active_offer = await session.scalar(
            select(Offer.id).where(
                Offer.tenant_id == context.tenant_id,
                Offer.application_id == application.id,
                Offer.status.in_(
                    (
                        OfferStatus.DRAFT,
                        OfferStatus.PENDING_APPROVAL,
                        OfferStatus.APPROVED,
                        OfferStatus.SENT,
                    )
                ),
            )
        )
        if active_offer is not None:
            raise OfferAlreadyExistsError(
                "This application already has an active offer."
            )

        offer = Offer(
            tenant_id=context.tenant_id,
            application_id=application.id,
            status=OfferStatus.DRAFT,
            currency=command.currency,
            base_salary=command.base_salary,
            pay_period=command.pay_period,
            bonus_amount=command.bonus_amount,
            equity_summary=command.equity_summary,
            proposed_start_date=command.proposed_start_date,
            expires_at=command.expires_at,
            created_by_subject=context.subject,
        )
        session.add(offer)
        await session.flush()

        _append_lifecycle_history(
            session,
            context=context,
            offer=offer,
            event_type=OfferLifecycleEventType.CREATED,
            from_status=None,
            to_status=OfferStatus.DRAFT,
        )
        record_audit_event(
            session,
            context=context,
            action="offer.created",
            entity_type="offer",
            entity_id=str(offer.id),
            details={
                "application_id": str(application.id),
                "offer_version": offer.version,
            },
        )

        await session.flush()
        await session.refresh(offer)

    return offer


async def submit_offer_for_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> OfferApproval:
    """Snapshot the active default policy and submit a draft offer."""
    _require_offer_write_access(context)

    async with transactional(session):
        offer = await _load_offer_for_update(
            session,
            context=context,
            offer_id=offer_id,
        )
        _validate_expected_version(offer, expected_offer_version)

        if offer.status is not OfferStatus.DRAFT:
            raise OfferValidationError(
                "Only draft offers can be submitted for approval."
            )

        policy = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.tenant_id == context.tenant_id,
                ApprovalPolicy.is_default.is_(True),
                ApprovalPolicy.is_active.is_(True),
            )
            .with_for_update()
        )
        if policy is None:
            raise OfferValidationError(
                "No active default approval policy is configured."
            )

        steps = list(
            await session.scalars(
                select(ApprovalPolicyStep)
                .where(ApprovalPolicyStep.approval_policy_id == policy.id)
                .order_by(ApprovalPolicyStep.position)
            )
        )
        if not steps:
            raise OfferValidationError(
                "The active default approval policy has no approvers."
            )

        approver_ids = tuple(step.approver_user_id for step in steps)
        approvers = list(
            await session.scalars(
                select(User).where(
                    User.tenant_id == context.tenant_id,
                    User.id.in_(approver_ids),
                )
            )
        )
        approvers_by_id = {approver.id: approver for approver in approvers}

        if len(approvers_by_id) != len(approver_ids):
            raise OfferValidationError(
                "Every configured offer approver must belong to the tenant."
            )

        if any(
            approver.external_subject == context.subject
            for approver in approvers_by_id.values()
        ):
            raise OfferSelfApprovalError(
                "An offer submitter cannot approve their own offer."
            )

        previous_attempt = await session.scalar(
            select(func.coalesce(func.max(OfferApproval.attempt), 0)).where(
                OfferApproval.offer_id == offer.id
            )
        )
        attempt = (previous_attempt or 0) + 1

        policy_snapshot = {
            "policy_id": str(policy.id),
            "policy_name": policy.name,
            "policy_version": policy.version,
            "steps": [
                {
                    "position": step.position,
                    "approver_user_id": str(step.approver_user_id),
                    "approver_subject": approvers_by_id[
                        step.approver_user_id
                    ].external_subject,
                }
                for step in steps
            ],
        }

        approval = OfferApproval(
            tenant_id=context.tenant_id,
            offer_id=offer.id,
            approval_policy_id=policy.id,
            policy_snapshot=policy_snapshot,
            attempt=attempt,
            status=ApprovalStatus.PENDING,
            current_step=steps[0].position,
            submitted_by_subject=context.subject,
        )
        session.add(approval)

        previous_status = offer.status
        validate_offer_transition(previous_status, OfferStatus.PENDING_APPROVAL)
        offer.status = OfferStatus.PENDING_APPROVAL
        offer.approval_requested_at = datetime.now(UTC)

        await session.flush()

        session.add_all(
            [
                OfferApprovalDecision(
                    offer_approval_id=approval.id,
                    step_position=step.position,
                    approver_user_id=step.approver_user_id,
                    status=ApprovalDecisionStatus.PENDING,
                )
                for step in steps
            ]
        )

        _append_lifecycle_history(
            session,
            context=context,
            offer=offer,
            event_type=OfferLifecycleEventType.SUBMITTED_FOR_APPROVAL,
            from_status=previous_status,
            to_status=offer.status,
        )
        record_audit_event(
            session,
            context=context,
            action="offer.submitted_for_approval",
            entity_type="offer",
            entity_id=str(offer.id),
            details={
                "approval_id": str(approval.id),
                "attempt": approval.attempt,
                "policy_id": str(policy.id),
                "policy_version": policy.version,
            },
        )

        await session.flush()
        await session.refresh(approval)

    return approval


async def decide_offer_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    approval_id: UUID,
    expected_offer_version: int,
    decision: ApprovalDecisionStatus,
    comment: str | None = None,
) -> OfferApproval:
    """Record one ordered approval decision and update the offer when final."""
    normalized_comment = comment.strip() if comment is not None else None
    if normalized_comment == "":
        normalized_comment = None

    if (
        normalized_comment is not None
        and len(normalized_comment) > _MAX_APPROVAL_COMMENT_LENGTH
    ):
        raise OfferValidationError(
            "Approval comment must not exceed 5000 characters."
        )

    if decision is ApprovalDecisionStatus.PENDING:
        raise OfferValidationError("An approval decision must be approved or rejected.")

    async with transactional(session):
        approval = await session.scalar(
            select(OfferApproval)
            .where(
                OfferApproval.id == approval_id,
                OfferApproval.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if approval is None:
            raise OfferApprovalNotFoundError("Offer approval was not found.")

        if approval.status is not ApprovalStatus.PENDING:
            raise OfferApprovalAlreadyCompleteError("Offer approval is complete.")

        offer = await _load_offer_for_update(
            session,
            context=context,
            offer_id=approval.offer_id,
        )
        _validate_expected_version(offer, expected_offer_version)

        actor = await session.scalar(
            select(User).where(
                User.tenant_id == context.tenant_id,
                User.external_subject == context.subject,
            )
        )
        if actor is None:
            raise OfferApprovalForbiddenError(
                "Caller is not an assigned offer approver."
            )

        current_decision = await session.scalar(
            select(OfferApprovalDecision)
            .where(
                OfferApprovalDecision.offer_approval_id == approval.id,
                OfferApprovalDecision.step_position == approval.current_step,
            )
            .with_for_update()
        )
        if current_decision is None:
            raise OfferValidationError("Offer approval has no current decision step.")

        if current_decision.approver_user_id != actor.id:
            raise OfferApprovalForbiddenError(
                "Caller is not assigned to the current approval step."
            )

        current_decision.status = decision
        current_decision.comment = normalized_comment
        current_decision.decided_at = datetime.now(UTC)

        if decision is ApprovalDecisionStatus.REJECTED:
            approval.status = ApprovalStatus.REJECTED
            approval.completed_at = datetime.now(UTC)

            previous_status = offer.status
            validate_offer_transition(previous_status, OfferStatus.DRAFT)
            offer.status = OfferStatus.DRAFT

            _append_lifecycle_history(
                session,
                context=context,
                offer=offer,
                event_type=OfferLifecycleEventType.APPROVAL_REJECTED,
                from_status=previous_status,
                to_status=offer.status,
            )
            action = "offer_approval.rejected"
        else:
            next_decision = await session.scalar(
                select(OfferApprovalDecision)
                .where(
                    OfferApprovalDecision.offer_approval_id == approval.id,
                    OfferApprovalDecision.step_position > approval.current_step,
                )
                .order_by(OfferApprovalDecision.step_position)
                .limit(1)
            )

            if next_decision is None:
                approval.status = ApprovalStatus.APPROVED
                approval.completed_at = datetime.now(UTC)

                previous_status = offer.status
                validate_offer_transition(previous_status, OfferStatus.APPROVED)
                offer.status = OfferStatus.APPROVED
                offer.approved_at = datetime.now(UTC)

                _append_lifecycle_history(
                    session,
                    context=context,
                    offer=offer,
                    event_type=OfferLifecycleEventType.APPROVED,
                    from_status=previous_status,
                    to_status=offer.status,
                )
            else:
                approval.current_step = next_decision.step_position

            action = "offer_approval.approved"

        record_audit_event(
            session,
            context=context,
            action=action,
            entity_type="offer_approval",
            entity_id=str(approval.id),
            details={
                "offer_id": str(offer.id),
                "approver_user_id": str(actor.id),
                "step_position": current_decision.step_position,
                "decision": decision.value,
                "offer_version": offer.version,
            },
        )

        await session.flush()
        await session.refresh(approval)

    return approval


async def _transition_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
    target_status: OfferStatus,
    event_type: OfferLifecycleEventType,
) -> Offer:
    """Lock, transition, append history, and audit one offer lifecycle action."""
    _require_offer_write_access(context)

    async with transactional(session):
        offer = await _load_offer_for_update(
            session,
            context=context,
            offer_id=offer_id,
        )
        _validate_expected_version(offer, expected_offer_version)

        previous_status = offer.status
        validate_offer_transition(previous_status, target_status)
        offer.status = target_status

        now = datetime.now(UTC)
        if target_status is OfferStatus.SENT:
            if offer.expires_at <= now:
                raise OfferValidationError("An expired offer cannot be sent.")
            offer.sent_at = now
        elif target_status is OfferStatus.DECLINED:
            offer.declined_at = now
        elif target_status is OfferStatus.CANCELLED:
            offer.cancelled_at = now

        _append_lifecycle_history(
            session,
            context=context,
            offer=offer,
            event_type=event_type,
            from_status=previous_status,
            to_status=target_status,
        )
        record_audit_event(
            session,
            context=context,
            action=f"offer.{event_type.value}",
            entity_type="offer",
            entity_id=str(offer.id),
            details={
                "from_status": previous_status.value,
                "to_status": target_status.value,
                "offer_version": offer.version,
            },
        )

        await session.flush()
        await session.refresh(offer)

    return offer


async def send_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> Offer:
    """Mark an approved offer as sent by an authorized operator."""
    return await _transition_offer(
        session,
        context=context,
        offer_id=offer_id,
        expected_offer_version=expected_offer_version,
        target_status=OfferStatus.SENT,
        event_type=OfferLifecycleEventType.SENT,
    )


async def decline_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> Offer:
    """Record that a sent offer was declined."""
    return await _transition_offer(
        session,
        context=context,
        offer_id=offer_id,
        expected_offer_version=expected_offer_version,
        target_status=OfferStatus.DECLINED,
        event_type=OfferLifecycleEventType.DECLINED,
    )


async def expire_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> Offer:
    """Expire a sent offer only after its configured expiry instant."""
    _require_offer_write_access(context)

    async with transactional(session):
        offer = await _load_offer_for_update(
            session,
            context=context,
            offer_id=offer_id,
        )
        _validate_expected_version(offer, expected_offer_version)

        if offer.status is not OfferStatus.SENT:
            raise OfferValidationError("Only sent offers can expire.")

        if offer.expires_at > datetime.now(UTC):
            raise OfferValidationError("Offer expiry has not been reached.")

        previous_status = offer.status
        validate_offer_transition(previous_status, OfferStatus.EXPIRED)
        offer.status = OfferStatus.EXPIRED

        _append_lifecycle_history(
            session,
            context=context,
            offer=offer,
            event_type=OfferLifecycleEventType.EXPIRED,
            from_status=previous_status,
            to_status=offer.status,
        )
        record_audit_event(
            session,
            context=context,
            action="offer.expired",
            entity_type="offer",
            entity_id=str(offer.id),
            details={"offer_version": offer.version},
        )

        await session.flush()
        await session.refresh(offer)

    return offer


async def cancel_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> Offer:
    """Cancel a non-terminal offer."""
    return await _transition_offer(
        session,
        context=context,
        offer_id=offer_id,
        expected_offer_version=expected_offer_version,
        target_status=OfferStatus.CANCELLED,
        event_type=OfferLifecycleEventType.CANCELLED,
    )


async def accept_offer(
    session: AsyncSession,
    *,
    context: TenantContext,
    offer_id: UUID,
    expected_offer_version: int,
) -> Offer:
    """Accept a sent offer and atomically hire its application."""
    _require_offer_write_access(context)

    async with transactional(session):
        offer = await _load_offer_for_update(
            session,
            context=context,
            offer_id=offer_id,
        )
        _validate_expected_version(offer, expected_offer_version)

        previous_status = offer.status
        validate_offer_transition(previous_status, OfferStatus.ACCEPTED)

        application = await session.scalar(
            select(Application)
            .where(
                Application.id == offer.application_id,
                Application.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if application is None:
            raise ApplicationNotFoundError("Application was not found.")

        if application.status is not ApplicationStatus.OFFER:
            raise OfferApplicationNotEligibleError(
                "Only applications in the offer stage can be hired."
            )

        validate_application_transition(
            application.status,
            ApplicationStatus.HIRED,
        )

        now = datetime.now(UTC)
        offer.status = OfferStatus.ACCEPTED
        offer.accepted_at = now

        previous_application_status = application.status
        application.status = ApplicationStatus.HIRED

        _append_lifecycle_history(
            session,
            context=context,
            offer=offer,
            event_type=OfferLifecycleEventType.ACCEPTED,
            from_status=previous_status,
            to_status=offer.status,
        )
        session.add(
            ApplicationStageHistory(
                tenant_id=context.tenant_id,
                application_id=application.id,
                from_status=previous_application_status,
                to_status=ApplicationStatus.HIRED,
                transitioned_by_subject=context.subject,
            )
        )
        record_audit_event(
            session,
            context=context,
            action="offer.accepted",
            entity_type="offer",
            entity_id=str(offer.id),
            details={
                "application_id": str(application.id),
                "application_version": application.version,
                "offer_version": offer.version,
            },
        )

        await session.flush()
        await session.refresh(offer)

    return offer
