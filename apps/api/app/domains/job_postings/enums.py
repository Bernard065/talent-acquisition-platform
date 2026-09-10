"""Job posting lifecycle and employment-type enumerations."""

from enum import StrEnum


class JobPostingStatus(StrEnum):
    """Controlled visibility lifecycle for a public job posting."""

    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    EXPIRED = "expired"


class EmploymentType(StrEnum):
    """Supported employment arrangements exposed to candidates."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
