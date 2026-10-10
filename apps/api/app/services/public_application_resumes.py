"""Short-lived proof records for résumés scanned before application submission."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.idempotency import IdempotencyRecord
from app.services.idempotency import hash_idempotency_key
from app.services.object_storage import public_application_resume_scan_object_key
from app.services.public_application_errors import PublicApplicationResumeScanProofError

_RESUME_SCAN_OPERATION = "public_application.resume_scan"


@dataclass(frozen=True, slots=True)
class ClaimedResumeScan:
    """Verified scan evidence consumed by one final application request."""

    scan_id: UUID
    object_key: str
    scanner_name: str
    content_sha256: str
    content_type: str
    byte_size: int


async def claim_public_application_resume_scan(
    session: AsyncSession,
    *,
    context: TenantContext,
    public_job_id: UUID,
    scan_token: str,
    content: bytes,
    content_type: str,
) -> ClaimedResumeScan:
    """Validate and consume a clean, job-bound scan proof in the caller's transaction."""
    if not scan_token or len(scan_token) > 255:
        raise PublicApplicationResumeScanProofError(
            "Scan the résumé again before submitting your application."
        )

    record = await session.scalar(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.tenant_id == context.tenant_id,
            IdempotencyRecord.key_hash == hash_idempotency_key(scan_token.strip()),
        )
        .with_for_update()
    )
    if (
        record is None
        or record.operation != _RESUME_SCAN_OPERATION
        or record.expires_at <= datetime.now(UTC)
    ):
        raise PublicApplicationResumeScanProofError(
            "The résumé scan expired or is no longer valid. Scan it again."
        )

    body = record.response_body
    digest = hashlib.sha256(content).hexdigest()
    scan_id: UUID | None = None
    expected_key: str | None = None
    scanner_name = ""
    try:
        scan_id = UUID(str(body["resume_scan_id"]))
        expiry = datetime.fromisoformat(str(body["scan_expires_at"]))
        expected_size = int(body["byte_size"])
        expected_key = public_application_resume_scan_object_key(
            tenant_id=context.tenant_id,
            scan_id=scan_id,
        )
        scanner_name = str(body["scanner_name"])
        proof_is_valid = (
            body["public_job_id"] == str(public_job_id)
            and body["content_sha256"] == digest
            and body["content_type"] == content_type
            and expected_size == len(content)
            and body["object_key"] == expected_key
            and bool(scanner_name.strip())
            and expiry.tzinfo is not None
            and expiry > datetime.now(UTC)
        )
    except (KeyError, TypeError, ValueError):
        proof_is_valid = False

    if not proof_is_valid or scan_id is None or expected_key is None:
        raise PublicApplicationResumeScanProofError(
            "The résumé changed after scanning or its scan expired. Scan it again."
        )

    await session.delete(record)
    return ClaimedResumeScan(
        scan_id=scan_id,
        object_key=expected_key,
        scanner_name=scanner_name,
        content_sha256=digest,
        content_type=content_type,
        byte_size=len(content),
    )
