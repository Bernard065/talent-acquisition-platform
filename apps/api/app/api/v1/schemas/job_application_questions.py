"""Contracts for job-specific public application questions and answers."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ApplicationQuestionType = Literal[
    "short_text",
    "long_text",
    "yes_no",
    "single_choice",
]


class ApplicationQuestionDefinition(BaseModel):
    """One candidate-facing question configured on a job posting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    prompt: str = Field(min_length=1, max_length=300)
    question_type: ApplicationQuestionType
    is_required: bool = False
    options: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        """Keep answer choices limited to single-choice questions."""
        self.options = [option.strip() for option in self.options]
        if self.question_type == "single_choice":
            if len(self.options) < 2 or any(not option for option in self.options):
                raise ValueError("Single-choice questions need at least two options.")
            if len({option.casefold() for option in self.options}) != len(self.options):
                raise ValueError("Question options must be unique.")
        elif self.options:
            raise ValueError("Options are only supported for single-choice questions.")
        return self


class ReplaceApplicationQuestionsRequest(BaseModel):
    """Replace a posting's question set with optimistic concurrency."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    questions: list[ApplicationQuestionDefinition] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_question_ids(self) -> Self:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique.")
        return self


class JobApplicationQuestionsResponse(BaseModel):
    """Private question configuration returned to workspace members."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationQuestionDefinition]
    version: int = Field(ge=1)


class ApplicationAnswerInput(BaseModel):
    """One answer submitted with a public job application."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: UUID
    answer: str = Field(min_length=1, max_length=5000)


class ApplicationAnswerResponse(BaseModel):
    """An immutable question and answer snapshot shown to recruiters."""

    model_config = ConfigDict(extra="forbid")

    question_id: UUID
    prompt: str
    question_type: ApplicationQuestionType
    answer: str


class ApplicationAnswersResponse(BaseModel):
    """The answers submitted for one application."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationAnswerResponse]

