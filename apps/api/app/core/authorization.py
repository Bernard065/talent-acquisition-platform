"""Core authorization primitives for tenant and role-based access control."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    """Roles that can be assigned to users within a tenant."""

    TENANT_ADMIN = "tenant_admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    INTERVIEWER = "interviewer"
    PEOPLE_OPERATIONS = "people_operations"
    ANALYST = "analyst"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Verified caller identity derived only from a verified JWT."""

    tenant_id: UUID
    subject: str
    roles: frozenset[Role]
    request_id: str
