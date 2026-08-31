"""Audit event service for recording security-relevant application actions."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.audit import AuditEvent


def record_audit_event(
    session: AsyncSession,
    *,
    context: TenantContext,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Queue an audit event in the caller's transaction.

    The caller owns commit and rollback. This ensures future business
    mutations and their audit event succeed or fail together.
    """
    event = AuditEvent(
        tenant_id=context.tenant_id,
        actor_subject=context.subject,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=context.request_id,
        details=details,
    )
    session.add(event)
    return event
