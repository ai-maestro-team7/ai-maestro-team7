"""Story Bank business rules. HTTP and task handlers call these synchronous functions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mentoring.deps import Deps
from mentoring.errors import ai_output_invalid, invalid_input, not_found, precondition_not_met
from mentoring.ports import VersionConflict

from .models import (
    AnswerStoryRequest,
    CreateStoryRequest,
    StoryAnswer,
    StoryExtraction,
    StoryLatest,
    StoryVersion,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .repo import StoryRepo

_FIELDS = ("situation", "task", "actions", "result", "learning")
_EDITABLE = set(_FIELDS) | {"title", "target_role"}


class _StoryConfig(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: value.split("_")[0] + "".join(
        part.capitalize() for part in value.split("_")[1:]
    ), populate_by_name=True)

    config_version: str
    prompt_version: str
    raw_experience_min_chars: int = Field(ge=1)
    raw_experience_max_chars: int = Field(ge=1)
    max_questions: int = Field(ge=1, le=3)
    max_llm_tokens: int = Field(ge=1)


def _load_config() -> _StoryConfig:
    path = Path(__file__).with_name("story_config.json")
    config = _StoryConfig.model_validate_json(path.read_text(encoding="utf-8"))
    if config.raw_experience_min_chars > config.raw_experience_max_chars:
        raise ValueError("rawExperienceMinChars must not exceed rawExperienceMaxChars")
    return config


def _current(stories: StoryRepo, user_id: str, story_id: str) -> tuple[StoryLatest, StoryVersion]:
    latest = stories.get_latest(user_id, story_id)
    if latest is None:
        raise not_found()
    story = stories.get_version(user_id, story_id, latest.latest_version)
    if story is None:
        raise not_found()
    return latest, story


def create_story_draft(
    deps: Deps,
    stories: StoryRepo,
    user_id: str,
    request: CreateStoryRequest,
) -> StoryVersion:
    config = _load_config()
    raw = request.raw_experience.strip()
    if not config.raw_experience_min_chars <= len(raw) <= config.raw_experience_max_chars:
        raise invalid_input(
            "경험 내용 길이를 확인해 주세요.",
            minChars=config.raw_experience_min_chars,
            maxChars=config.raw_experience_max_chars,
        )
    now = deps.now_iso()
    story = StoryVersion(
        story_id=deps.new_id("story"),
        version=1,
        owner_user_id=user_id,
        status="DRAFT",
        title=request.title,
        raw_experience=raw,
        target_role=request.target_role,
        source_document_id=request.source_document_id,
        created_at=now,
        updated_at=now,
    )
    stories.create_story(StoryLatest.of(story), story)
    return story


def _parse_model(deps: Deps, user_prompt: str, max_tokens: int) -> StoryExtraction:
    for _ in range(2):
        raw = deps.llm.invoke(SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens)
        try:
            return StoryExtraction.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError):
            continue
    raise ai_output_invalid()


def _grounded(deps: Deps, source: str, value: str | None) -> str | None:
    if not value or deps.text.find_unsupported_facts(source, value):
        return None
    check = deps.text.check_evidence(source, value, None, None)
    return value if check.status != "NOT_FOUND" else None


def generate_story_questions(
    deps: Deps,
    stories: StoryRepo,
    user_id: str,
    story_id: str,
) -> StoryVersion:
    latest, current = _current(stories, user_id, story_id)
    config = _load_config()
    combined = "\n".join([current.raw_experience, *(answer.answer for answer in current.answers)])
    masked_experience = deps.text.mask_pii(current.raw_experience).masked_text
    masked_answers = [
        {
            "question": deps.text.mask_pii(answer.question).masked_text,
            "answer": deps.text.mask_pii(answer.answer).masked_text,
        }
        for answer in current.answers
    ]
    output = _parse_model(
        deps,
        build_user_prompt(masked_experience, masked_answers),
        config.max_llm_tokens,
    )

    values: dict[str, Any] = {
        "situation": _grounded(deps, combined, output.situation),
        "task": _grounded(deps, combined, output.task),
        "actions": [
            grounded
            for action in output.actions
            if (grounded := _grounded(deps, combined, action)) is not None
        ],
        "result": _grounded(deps, combined, output.result),
        "learning": _grounded(deps, combined, output.learning),
    }
    candidates = []
    for candidate in output.competency_candidates:
        check = deps.text.check_evidence(combined, candidate.evidence_action, None, None)
        if check.status != "NOT_FOUND":
            candidates.append(candidate)

    statuses = dict(current.field_status)
    for field in _FIELDS:
        value = values[field]
        if value:
            statuses[field] = "VERIFIED" if field in current.confirmed_fields else "NEEDS_CONFIRMATION"
        else:
            statuses[field] = "NEEDS_CONFIRMATION"

    story = current.model_copy(
        update={
            "version": current.version + 1,
            "status": "QUESTIONS_READY",
            "title": output.title or current.title,
            **values,
            "field_status": statuses,
            "questions": output.questions[: config.max_questions],
            "competency_candidates": candidates,
            "model_id": getattr(deps.llm, "model_id", None),
            "prompt_version": config.prompt_version,
            "updated_at": deps.now_iso(),
        },
        deep=True,
    )
    try:
        stories.put_story_version(StoryLatest.of(story), story, expected_version=latest.latest_version)
    except VersionConflict as error:
        raise precondition_not_met("경험 블록이 이미 변경됐어요. 최신 버전을 다시 확인해 주세요.") from error
    return story


def answer_story(
    deps: Deps,
    stories: StoryRepo,
    user_id: str,
    story_id: str,
    request: AnswerStoryRequest,
) -> StoryVersion:
    latest, current = _current(stories, user_id, story_id)
    if request.base_version != latest.latest_version:
        raise precondition_not_met("경험 블록이 이미 변경됐어요. 최신 버전을 다시 확인해 주세요.")

    unknown_edits = set(request.edits) - _EDITABLE
    unknown_confirms = set(request.confirm_fields) - set(_FIELDS)
    if unknown_edits or unknown_confirms:
        raise invalid_input("수정하거나 확인할 수 없는 필드가 있어요.")

    updates: dict[str, Any] = {}
    statuses = dict(current.field_status)
    for field, value in request.edits.items():
        if field == "actions":
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise invalid_input("actions는 비어 있지 않은 문자열 목록이어야 해요.")
            updates[field] = [item.strip() for item in value]
        else:
            if not isinstance(value, str) or not value.strip():
                raise invalid_input(f"{field} 값은 비어 있을 수 없어요.")
            updates[field] = value.strip()
        if field in _FIELDS:
            statuses[field] = "VERIFIED"

    confirmed = list(current.confirmed_fields)
    for field in request.confirm_fields:
        value = updates.get(field, getattr(current, field))
        if not value:
            raise invalid_input("값이 없는 필드는 확인할 수 없어요.", field=field)
        statuses[field] = "VERIFIED"
        if field not in confirmed:
            confirmed.append(field)

    answers = [*current.answers, *(StoryAnswer(question=item.question, answer=item.answer) for item in request.answers)]
    complete = all(
        (updates.get(field, getattr(current, field))) and statuses.get(field) == "VERIFIED"
        for field in _FIELDS
    )
    story = current.model_copy(
        update={
            **updates,
            "version": current.version + 1,
            "status": "CONFIRMED" if complete else "QUESTIONS_READY",
            "field_status": statuses,
            "confirmed_fields": confirmed,
            "answers": answers,
            "updated_at": deps.now_iso(),
        },
        deep=True,
    )
    try:
        stories.put_story_version(StoryLatest.of(story), story, expected_version=request.base_version)
    except VersionConflict as error:
        raise precondition_not_met("경험 블록이 이미 변경됐어요. 최신 버전을 다시 확인해 주세요.") from error
    return story


def list_stories(deps: Deps, stories: StoryRepo, user_id: str) -> list[StoryLatest]:
    del deps
    return stories.list_latest(user_id)


def get_story(
    deps: Deps,
    stories: StoryRepo,
    user_id: str,
    story_id: str,
) -> StoryVersion:
    del deps
    return _current(stories, user_id, story_id)[1]


def story_for_review(
    deps: Deps,
    stories: StoryRepo,
    user_id: str,
    story_id: str,
) -> dict:
    story = get_story(deps, stories, user_id, story_id)
    result: dict[str, Any] = {
        "storyId": story.story_id,
        "version": story.version,
        "confirmedFields": list(story.confirmed_fields),
    }
    for field in story.confirmed_fields:
        if field in _FIELDS:
            result[field] = getattr(story, field)
    return result
