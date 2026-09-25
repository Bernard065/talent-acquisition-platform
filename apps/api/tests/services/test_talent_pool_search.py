"""PostgreSQL tests for consent-filtered talent-pool search."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_talent_pool_consent import (
    CandidateTalentPoolConsentEvent,
)
from app.db.models.identity import Tenant
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)
from app.services.talent_pool_search import (
    TalentPoolSearchFilters,
    search_consented_talent_pool,
)
from app.services.talent_pool_search_errors import (
    InvalidTalentPoolSearchCursorError,
    TalentPoolSearchAccessDeniedError,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Create a test identity with an explicit tenant and role set."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="talent-pool-search-test",
        roles=roles,
        request_id="talent-pool-search-test-request",
    )


def _candidate(
    *,
    tenant_id: UUID,
    name: str,
    email: str,
    created_at: datetime,
    source: str = "referral",
    location: str = "Nairobi",
    privacy_status: CandidatePrivacyStatus = CandidatePrivacyStatus.ACTIVE,
) -> Candidate:
    """Build candidate test data without using a public API or real PII."""
    erased_at = created_at if privacy_status is CandidatePrivacyStatus.ERASED else None
    erasure_requested_at = (
        created_at
        if privacy_status
        in {
            CandidatePrivacyStatus.ERASURE_PENDING,
            CandidatePrivacyStatus.ERASED,
        }
        else None
    )
    return Candidate(
        tenant_id=tenant_id,
        full_name=name,
        email=email,
        normalized_email=email.lower(),
        location=location,
        source=source,
        source_metadata={},
        created_by_subject="test-seed",
        privacy_status=privacy_status,
        erasure_requested_at=erasure_requested_at,
        erased_at=erased_at,
        created_at=created_at,
    )


def _consent_event(
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    event_version: int,
    event_type: CandidateTalentPoolConsentEventType,
    recorded_at: datetime,
) -> CandidateTalentPoolConsentEvent:
    """Build minimal immutable consent evidence for a candidate."""
    return CandidateTalentPoolConsentEvent(
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        event_version=event_version,
        event_type=event_type,
        capture_method=CandidateTalentPoolCaptureMethod.SIGNED_FORM,
        notice_version=(
            None
            if event_type is CandidateTalentPoolConsentEventType.WITHDRAWN
            else f"notice-v{event_version}"
        ),
        recorded_by_subject="consent-test-seed",
        recorded_at=recorded_at,
    )


@pytest.mark.asyncio
async def test_search_includes_only_currently_consented_active_candidates(
    session: AsyncSession,
) -> None:
    """Renewals qualify, while absent consent, withdrawal, and erasure do not."""
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    now = datetime.now(UTC)
    session.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Talent Pool Search Tenant",
                slug=f"talent-pool-{tenant_id.hex[:12]}",
            ),
            Tenant(
                id=other_tenant_id,
                name="Other Talent Pool Tenant",
                slug=f"other-talent-pool-{other_tenant_id.hex[:12]}",
            ),
        ]
    )
    await session.flush()

    granted = _candidate(
        tenant_id=tenant_id,
        name="Ada Grant",
        email=f"ada-{tenant_id.hex[:8]}@example.test",
        created_at=now,
    )
    renewed = _candidate(
        tenant_id=tenant_id,
        name="Grace Renewal",
        email=f"grace-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=1),
    )
    withdrawn = _candidate(
        tenant_id=tenant_id,
        name="Linus Withdrawn",
        email=f"linus-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=2),
    )
    unknown = _candidate(
        tenant_id=tenant_id,
        name="No Consent",
        email=f"unknown-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=3),
    )
    erased = _candidate(
        tenant_id=tenant_id,
        name="Erased Candidate",
        email=f"erased-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=4),
        privacy_status=CandidatePrivacyStatus.ERASED,
    )
    erasure_pending = _candidate(
        tenant_id=tenant_id,
        name="Erasure Pending Candidate",
        email=f"pending-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=5),
        privacy_status=CandidatePrivacyStatus.ERASURE_PENDING,
    )
    foreign = _candidate(
        tenant_id=other_tenant_id,
        name="Foreign Candidate",
        email=f"foreign-{other_tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=5),
    )
    session.add_all(
        [granted, renewed, withdrawn, unknown, erased, erasure_pending, foreign]
    )
    await session.flush()

    session.add_all(
        [
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=granted.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now,
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=renewed.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now - timedelta(days=1),
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=renewed.id,
                event_version=2,
                event_type=CandidateTalentPoolConsentEventType.RENEWED,
                recorded_at=now,
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=withdrawn.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now - timedelta(days=1),
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=withdrawn.id,
                event_version=2,
                event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
                recorded_at=now,
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=erased.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now,
            ),
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=erasure_pending.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now,
            ),
            _consent_event(
                tenant_id=other_tenant_id,
                candidate_id=foreign.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now,
            ),
        ]
    )
    await session.flush()

    result = await search_consented_talent_pool(
        session,
        context=_context(tenant_id),
    )

    assert [item.candidate.id for item in result.items] == [
        granted.id,
        renewed.id,
    ]
    assert [item.consent_event.event_type for item in result.items] == [
        CandidateTalentPoolConsentEventType.GRANTED,
        CandidateTalentPoolConsentEventType.RENEWED,
    ]
    assert [item.consent_event.event_version for item in result.items] == [1, 2]
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_search_filters_and_paginates_with_stable_candidate_cursor(
    session: AsyncSession,
) -> None:
    """Apply literal filters and return stable non-overlapping cursor pages."""
    tenant_id = uuid4()
    now = datetime.now(UTC)
    tenant = Tenant(
        id=tenant_id,
        name="Talent Pool Cursor Tenant",
        slug=f"talent-pool-cursor-{tenant_id.hex[:12]}",
    )
    session.add(tenant)
    await session.flush()

    candidates = [
        _candidate(
            tenant_id=tenant_id,
            name=f"Candidate {index}",
            email=f"candidate-{index}-{tenant_id.hex[:8]}@example.test",
            created_at=now,
            location="Nairobi, Kenya",
        )
        for index in range(3)
    ]
    excluded = _candidate(
        tenant_id=tenant_id,
        name="C_Developer% Specialist",
        email=f"escaped-{tenant_id.hex[:8]}@example.test",
        created_at=now - timedelta(minutes=4),
        source="agency",
    )
    session.add_all([*candidates, excluded])
    await session.flush()
    session.add_all(
        [
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=candidate.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now - timedelta(minutes=index),
            )
            for index, candidate in enumerate(candidates)
        ]
        + [
            _consent_event(
                tenant_id=tenant_id,
                candidate_id=excluded.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                recorded_at=now,
            )
        ]
    )
    await session.flush()

    first_page = await search_consented_talent_pool(
        session,
        context=_context(tenant_id),
        filters=TalentPoolSearchFilters(source="referral", location="nairobi"),
        limit=2,
    )
    second_page = await search_consented_talent_pool(
        session,
        context=_context(tenant_id),
        filters=TalentPoolSearchFilters(source="referral", location="nairobi"),
        limit=2,
        cursor=first_page.next_cursor,
    )
    literal_wildcard = await search_consented_talent_pool(
        session,
        context=_context(tenant_id),
        filters=TalentPoolSearchFilters(query="C_Developer%"),
    )
    expected_ids = [
        candidate.id
        for candidate in sorted(candidates, key=lambda value: value.id, reverse=True)
    ]

    assert [item.candidate.id for item in first_page.items] == [
        candidate_id for candidate_id in expected_ids[:2]
    ]
    assert [item.candidate.id for item in second_page.items] == [expected_ids[2]]
    assert first_page.next_cursor is not None
    assert second_page.next_cursor is None
    assert [item.candidate.id for item in literal_wildcard.items] == [excluded.id]


@pytest.mark.asyncio
async def test_search_rejects_unauthorized_roles_and_malformed_cursor(
    session: AsyncSession,
) -> None:
    """Protect the search role boundary and reject malformed cursor state."""
    tenant_id = uuid4()
    session.add(
        Tenant(
            id=tenant_id,
            name="Talent Pool Security Tenant",
            slug=f"talent-pool-security-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    with pytest.raises(TalentPoolSearchAccessDeniedError):
        await search_consented_talent_pool(
            session,
            context=_context(tenant_id, roles=frozenset({Role.INTERVIEWER})),
        )

    with pytest.raises(InvalidTalentPoolSearchCursorError):
        await search_consented_talent_pool(
            session,
            context=_context(tenant_id),
            cursor="not-a-valid-cursor",
        )
