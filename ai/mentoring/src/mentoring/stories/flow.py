"""REST 입구가 부르는 경험 블록 흐름. 규칙은 `service.py`에 있고 여기서는 순서와 재시도만 정한다.

질문 생성은 동기로 한다 (첫 스펙 미결정 M-7, 2026-11-20). 작업 종류(`TASK#.taskType`)를 늘리지 않고(BE-7 불필요)
Haiku 한 번(실패 시 재시도 1회) 호출이라 API Gateway 30초 안에 끝난다.
- POST: 초안 저장만 멱등으로 처리하고, 질문 생성은 그 뒤에 한다. 모델 호출이 실패해도 초안은 남고,
  같은 `Idempotency-Key`로 다시 보내면 같은 경험 블록에서 질문 생성만 다시 한다.
- PATCH: 답변·확인·수정을 먼저 저장한다. 답변이 있으면 질문을 다시 만들고, 이때 모델이 실패하면 저장한 결과에
  `QUESTIONS_NOT_REFRESHED` 경고를 붙여 돌려준다 (저장한 답변을 잃지 않게).
"""
from __future__ import annotations

from mentoring.core.idempotency import run_idempotent
from mentoring.core.logs import log_event, user_hash
from mentoring.deps import Deps
from mentoring.errors import MentoringError, aws_service_error, not_implemented

from .models import AnswerStoryRequest, CreateStoryRequest, StoryVersion
from .repo import StoryRepo
from .service import answer_story, create_story_draft, generate_story_questions, get_story

QUESTIONS_NOT_REFRESHED = "QUESTIONS_NOT_REFRESHED"


def _repo(deps: Deps) -> StoryRepo:
    if deps.stories is None:
        raise not_implemented()
    return deps.stories


def _generate(deps: Deps, repo: StoryRepo, user_id: str, story_id: str) -> StoryVersion:
    try:
        return generate_story_questions(deps, repo, user_id, story_id)
    except MentoringError:
        raise
    except Exception as error:  # noqa: BLE001 - 모델 호출(Bedrock) 오류는 재시도 가능한 AWS 오류로 바꾼다
        log_event("story.llm_error", userHash=user_hash(deps, user_id), errorCode=type(error).__name__)
        raise aws_service_error("bedrock") from error


def start_story(deps: Deps, user_id: str, request: CreateStoryRequest, idempotency_key: str | None) -> StoryVersion:
    repo = _repo(deps)
    payload = request.model_dump(by_alias=True, mode="json")
    created = run_idempotent(
        deps, user_id, idempotency_key, payload,
        lambda: {"storyId": create_story_draft(deps, repo, user_id, request).story_id},
    )
    story = get_story(deps, repo, user_id, created["storyId"])
    if story.status != "DRAFT":  # 같은 키로 다시 왔고 질문 생성이 이미 끝났다
        return story
    return _generate(deps, repo, user_id, story.story_id)


def update_story(
    deps: Deps, user_id: str, story_id: str, request: AnswerStoryRequest,
) -> tuple[StoryVersion, list[str]]:
    repo = _repo(deps)
    story = answer_story(deps, repo, user_id, story_id, request)
    if not request.answers or story.status == "CONFIRMED":
        return story, []
    try:
        return _generate(deps, repo, user_id, story_id), []
    except MentoringError as error:
        if not error.retryable:
            raise
        return story, [QUESTIONS_NOT_REFRESHED]


def story_view(story: StoryVersion, warnings: list[str] | None = None) -> dict:
    """API 응답. 소유자 ID는 넣지 않는다."""
    data = story.to_api()
    data.pop("ownerUserId", None)
    if warnings:
        data["warnings"] = warnings
    return data
