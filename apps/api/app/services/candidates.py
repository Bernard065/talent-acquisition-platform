"""Tenant-scoped services for candidate profiles and job applications."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.candidate import Candidate
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.audit import record_audit_event
from app.services.candidate_errors import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    CandidateAccessDeniedError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
    RequisitionNotAcceptingApplicationsError,
)
from app.services.requisition_errors import RequisitionNotFoundError

_CANDIDATE_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_CANDIDATE_WRITE_ROLES = _CANDIDATE_READ_ROLES


@dataclass(frozen=True, slots=True)
class CreateCandidateCommand:
    """Validated business input for creating a candidate profile."""

    full_name: str
    email: str
    source: str
    phone: str | None = None
    location: str | None = None
    source_metadata: Mapping[str, Any] = field(default_factory=dict)
    consent_status: CandidateConsentStatus = CandidateConsentStatus.UNKNOWN

    def __post_init__(self) -> None:
        if not self.full_name.strip():
            raise ValueError("Candidate full name is required.")

        if len(self.full_name.strip()) > 200:
            raise ValueError("Candidate full name must not exceed 200 characters.")

        if not self.email.strip():
            raise ValueError("Candidate email is required.")

        if not self.source.strip():
            raise ValueError("Candidate source is required.")

        if len(self.source.strip()) > 100:
            raise ValueError("Candidate source must not exceed 100 characters.")

        try:
            json.dumps(dict(self.source_metadata))
        except (TypeError, ValueError) as error:
            raise ValueError("Candidate source metadata must be JSON serializable.") from error


@dataclass(frozen=True, slots=True)
class CreateApplicationCommand:
    """Input for creating a candidate application to an open requisition."""

    candidate_id: UUID
    requisition_id: UUID


def _require_any_role(
    context: TenantContext,
    allowed_roles: frozenset[Role],
) -> None:
    """Enforce candidate-data authorization at the service boundary."""
    if context.roles.isdisjoint(allowed_roles):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to access candidate data."
        )


def _canonicalize_email(email: str) -> tuple[str, str]:
    """Validate and derive display and tenant-local identity email values."""
    try:
        validated_email = validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized
    except EmailNotValidError as error:
        raise ValueError("Candidate email is invalid.") from error

    return validated_email, validated_email.casefold()


async def create_candidate(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateCandidateCommand,
) -> Candidate:
    """Create a candidate once per normalized email within a tenant."""
    _require_any_role(context, _CANDIDATE_WRITE_ROLES)
    email, normalized_email = _canonicalize_email(command.email)

    async with transactional(session):
        candidate = Candidate(
            tenant_id=context.tenant_id,
            full_name=command.full_name.strip(),
            email=email,
            normalized_email=normalized_email,
            phone=command.phone,
            location=command.location,
            source=command.source.strip(),
            source_metadata=dict(command.source_metadata),
            consent_status=command.consent_status,
            created_by_subject=context.subject,
        )

        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as error:
            raise CandidateAlreadyExistsError(
                "A candidate with this email already exists."
            ) from error

        record_audit_event(
            session,
            context=context,
            action="candidate.created",
            entity_type="candidate",
            entity_id=str(candidate.id),
            details={
                "source": candidate.source,
                "consent_status": candidate.consent_status.value,
            },
        )

    return candidate


async def get_candidate(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> Candidate:
    """Return one candidate visible only to the verified caller's tenant."""
    _require_any_role(context, _CANDIDATE_READ_ROLES)

    candidate = await session.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.tenant_id == context.tenant_id,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
        )
    )
    if candidate is None:
        raise CandidateNotFoundError("Candidate was not found.")

    return candidate


async def create_application(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateApplicationCommand,
) -> Application:
    """Create one application for a candidate and an open tenant requisition."""
    _require_any_role(context, _CANDIDATE_WRITE_ROLES)

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == command.candidate_id,
                Candidate.tenant_id == context.tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
            .with_for_update()
        )
        if candidate is None:
            raise CandidateNotFoundError("Candidate was not found.")

        requisition = await session.scalar(
            select(Requisition)
            .where(
                Requisition.id == command.requisition_id,
                Requisition.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if requisition is None:
            raise RequisitionNotFoundError("Requisition was not found.")

        if requisition.status is not RequisitionStatus.OPEN:
            raise RequisitionNotAcceptingApplicationsError(
                "Requisition is not accepting applications."
            )

        application = Application(
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.APPLIED,
            created_by_subject=context.subject,
        )

        try:
            async with session.begin_nested():
                session.add(application)
                await session.flush()
        except IntegrityError as error:
            raise ApplicationAlreadyExistsError(
                "Candidate already has an application for this requisition."
            ) from error

        session.add(
            ApplicationStageHistory(
                tenant_id=context.tenant_id,
                application_id=application.id,
                from_status=None,
                to_status=ApplicationStatus.APPLIED,
                transitioned_by_subject=context.subject,
            )
        )
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="application.created",
            entity_type="application",
            entity_id=str(application.id),
            details={
                "candidate_id": str(candidate.id),
                "requisition_id": str(requisition.id),
                "status": application.status.value,
            },
        )

    return application


async def get_application(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> Application:
    """Return one application visible only to the verified caller's tenant."""
    _require_any_role(context, _CANDIDATE_READ_ROLES)

    application = await session.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.tenant_id == context.tenant_id,
        )
    )
    if application is None:
        raise ApplicationNotFoundError("Application was not found.")

    return application
