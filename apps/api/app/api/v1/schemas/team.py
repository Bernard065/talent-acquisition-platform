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


class InterviewerResponse(BaseModel):
    """Workspace member who can be assigned to an interview session."""

    id: UUID
    display_name: str
    email: str


class InterviewerListResponse(BaseModel):
    """Interviewers visible to an authorized workspace user."""

    items: list[InterviewerResponse]
