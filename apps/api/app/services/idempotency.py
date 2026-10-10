"""Durable execution and replay of idempotent write operations."""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.idempotency import IdempotencyRecord
from app.db.transactions import transactional

DEFAULT_IDEMPOTENCY_TTL = timedelta(hours=24)

type IdempotentOperation = Callable[[], Awaitable[tuple[int, dict[str, Any]]]]


class InvalidIdempotencyKeyError(ValueError):
    """Raised when an idempotency key is blank or exceeds the allowed length."""


class IdempotencyKeyReuseError(ValueError):
    """Raised when a key is reused for a different request."""


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """The stored or newly-created HTTP response for an idempotent operation."""

    status_code: int
    body: dict[str, Any]
    replayed: bool


def hash_idempotency_key(key: str) -> str:
    """Create the canonical non-reversible digest of a caller-supplied key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _fingerprint_request(
    operation: str,
    payload: Mapping[str, Any],
) -> str:
    """Hash a canonical operation and JSON-compatible request payload."""
    serialized = json.dumps(
        {
            "operation": operation,
            "payload": payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_key(key: str) -> str:
    """Validate a header value before it reaches persistence."""
    normalized_key = key.strip()

    if not normalized_key:
        raise InvalidIdempotencyKeyError("Idempotency-Key must not be blank.")

    if len(normalized_key) > 255:
        raise InvalidIdempotencyKeyError(
            "Idempotency-Key must not exceed 255 characters."
        )

    return normalized_key


async def _execute_and_store(
    record: IdempotencyRecord,
    operation: IdempotentOperation,
) -> IdempotencyResult:
    """Execute the winning operation and attach its response to the record."""
    status_code, body = await operation()

    if not 100 <= status_code <= 599:
        raise ValueError("Idempotent operation returned an invalid HTTP status.")

    record.response_status = status_code
    record.response_body = body

    return IdempotencyResult(
        status_code=status_code,
        body=body,
        replayed=False,
    )


async def execute_idempotently(
    session: AsyncSession,
    *,
    context: TenantContext,
    key: str,
    operation_name: str,
    payload: Mapping[str, Any],
    operation: IdempotentOperation,
    ttl: timedelta = DEFAULT_IDEMPOTENCY_TTL,
) -> IdempotencyResult:
    """Execute a write once per tenant/key and replay its persisted response.

    The idempotency record, domain mutation, audit event, and serialized HTTP
    response commit together. Failed operations roll back entirely, allowing a
    client to retry safely with the same key.
    """
    normalized_key = _normalize_key(key)
    key_hash = hash_idempotency_key(normalized_key)
    request_fingerprint = _fingerprint_request(operation_name, payload)
    now = datetime.now(UTC)
    expires_at = now + ttl

    async with transactional(session):
        created_record_id = await session.scalar(
            insert(IdempotencyRecord)
            .values(
                tenant_id=context.tenant_id,
                key_hash=key_hash,
                operation=operation_name,
                request_fingerprint=request_fingerprint,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    IdempotencyRecord.tenant_id,
                    IdempotencyRecord.key_hash,
                ]
            )
            .returning(IdempotencyRecord.id)
        )

        if created_record_id is not None:
            record = await session.get(IdempotencyRecord, created_record_id)
            if record is None:
                raise RuntimeError("Created idempotency record could not be loaded.")

            return await _execute_and_store(record, operation)

        record = await session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.tenant_id == context.tenant_id,
                IdempotencyRecord.key_hash == key_hash,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("Idempotency record could not be loaded.")

        if (
            record.operation != operation_name
            or record.request_fingerprint != request_fingerprint
        ):
            raise IdempotencyKeyReuseError(
                "Idempotency-Key was already used for a different request."
            )

        if record.expires_at <= now:
            await session.delete(record)
            await session.flush()

            replacement = IdempotencyRecord(
                tenant_id=context.tenant_id,
                key_hash=key_hash,
                operation=operation_name,
                request_fingerprint=request_fingerprint,
                expires_at=expires_at,
            )
            session.add(replacement)
            await session.flush()

            return await _execute_and_store(replacement, operation)

        return IdempotencyResult(
            status_code=record.response_status,
            body=record.response_body,
            replayed=True,
        )


async def get_idempotent_replay(
    session: AsyncSession,
    *,
    context: TenantContext,
    key: str,
    operation_name: str,
    payload: Mapping[str, Any],
) -> IdempotencyResult | None:
    """Return an existing committed response without opening a write workflow.

    This lets endpoints perform expensive external preflight work only for new
    requests. The final write must still use ``execute_idempotently`` to handle
    concurrent requests safely.
    """
    normalized_key = _normalize_key(key)
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == context.tenant_id,
            IdempotencyRecord.key_hash == hash_idempotency_key(normalized_key),
        )
    )
    if record is None or record.expires_at <= datetime.now(UTC):
        return None

    request_fingerprint = _fingerprint_request(operation_name, payload)
    if (
        record.operation != operation_name
        or record.request_fingerprint != request_fingerprint
    ):
        raise IdempotencyKeyReuseError(
            "Idempotency-Key was already used for a different request."
        )

    return IdempotencyResult(
        status_code=record.response_status,
        body=record.response_body,
        replayed=True,
    )
