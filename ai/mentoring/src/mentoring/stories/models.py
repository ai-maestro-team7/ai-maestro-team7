"""Pydantic contracts for versioned experience stories."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from mentoring.models.base import MentoringModel, RequestModel

StoryStatus = Literal["DRAFT", "QUESTIONS_READY", "CONFIRMED"]
FieldStatus = Literal["VERIFIED", "NEEDS_CONFIRMATION"]
Strength = Literal["EVIDENCED", "PARTIAL"]


class CompetencyCandidate(MentoringModel):
    name: str
    evidence_action: str
    strength: Strength


class StoryAnswer(MentoringModel):
    question: str
    answer: str


class StoryVersion(MentoringModel):
    story_id: str
    version: int = Field(ge=1)
    owner_user_id: str
    status: StoryStatus
    title: str | None = None
    raw_experience: str
    target_role: str | None = None
    source_document_id: str | None = None
    situation: str | None = None
    task: str | None = None
    actions: list[str] = Field(default_factory=list)
    result: str | None = None
    learning: str | None = None
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)
    confirmed_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, max_length=3)
    answers: list[StoryAnswer] = Field(default_factory=list)
    competency_candidates: list[CompetencyCandidate] = Field(default_factory=list)
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str
    updated_at: str


class StoryLatest(MentoringModel):
    story_id: str
    owner_user_id: str
    title: str | None = None
    status: StoryStatus
    latest_version: int = Field(ge=1)
    updated_at: str

    @classmethod
    def of(cls, story: StoryVersion) -> "StoryLatest":
        return cls(
            story_id=story.story_id,
            owner_user_id=story.owner_user_id,
            title=story.title,
            status=story.status,
            latest_version=story.version,
            updated_at=story.updated_at,
        )


class CreateStoryRequest(RequestModel):
    raw_experience: str
    target_role: str | None = None
    source_document_id: str | None = None
    title: str | None = None


class StoryAnswerRequest(RequestModel):
    question: str
    answer: str


class AnswerStoryRequest(RequestModel):
    base_version: int = Field(ge=1)
    answers: list[StoryAnswerRequest] = Field(default_factory=list)
    confirm_fields: list[str] = Field(default_factory=list)
    edits: dict[str, Any] = Field(default_factory=dict)


class StoryExtraction(MentoringModel):
    """Fixed schema accepted from the model. Its status claims are not trusted."""

    title: str | None = None
    situation: str | None = None
    task: str | None = None
    actions: list[str] = Field(default_factory=list)
    result: str | None = None
    learning: str | None = None
    questions: list[str] = Field(default_factory=list)
    competency_candidates: list[CompetencyCandidate] = Field(default_factory=list)
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)

    @field_validator("questions")
    @classmethod
    def _nonempty_questions(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]
