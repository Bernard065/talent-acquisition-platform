"""Schemas for workspace teammate discovery."""

from uuid import UUID

from pydantic import BaseModel


class TeamMemberResponse(BaseModel):
    """Workspace member eligible for recruiting application assignment."""

    id: UUID
    display_name: str
    email: str


class TeamMemberListResponse(BaseModel):
    """Recruiting members visible to the authenticated workspace user."""

    items: list[TeamMemberResponse]
