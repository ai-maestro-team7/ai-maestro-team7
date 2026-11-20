"""첨삭 요청·저장·모델 출력 (개발계획서1 F-03 "수정 결과 단위", §4.5 `ReviewResult`, §6.4).
저장은 둘로 나눈다: DynamoDB `REVIEW#{reviewId}`에는 메타만, 첨삭 본문은 S3 `resultKey` (db-schema §2.1, §0 원칙 7)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from mentoring.fit.records import AnalysisWarning
from mentoring.models import DocumentType, TaskStatus
from mentoring.models.base import MentoringModel, RequestModel

FactCheckStatus = Literal["PASSED", "NEEDS_CONFIRMATION"]


class ReviewRequest(RequestModel):
    document_id: str | None = None
    input_text: str | None = None
    document_type: DocumentType = DocumentType.COVER_LETTER
    analysis_id: str | None = None
    job_posting_id: str | None = None
    workspace_id: str | None = None
    profile_id: str | None = None
    question_text: str | None = None
    max_characters: int | None = Field(default=None, ge=1)
    story_ids: list[str] = Field(default_factory=list)


class SourceSpan(MentoringModel):
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)


class ReviewIssue(MentoringModel):
    issue_id: str
    source_span: SourceSpan
    original_text: str  # 개인정보를 가린 원문 구간
    issue_type: str
    reason: str
    improvement_action: str
    revised_example: str | None = None
    needs_user_confirmation: bool = False
    questions: list[str] = Field(default_factory=list)
    used_story_ids: list[str] = Field(default_factory=list)
    fact_check: Literal["PASSED", "REJECTED", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    detected_by: Literal["MODEL", "RULE"] = "MODEL"


class CharCount(MentoringModel):
    """글자 수는 코드가 센다. 모델에게 세게 하지 않는다 (F-03 처리 9단계)."""
    with_spaces: int
    without_spaces: int
    utf8_bytes: int
    max_characters: int | None = None
    over_limit: bool = False


class PostingBasis(MentoringModel):
    mode: Literal["POSTING", "GENERAL"]
    job_posting_id: str | None = None
    snapshot_id: str | None = None
    analysis_id: str | None = None
    requirement_names: list[str] = Field(default_factory=list)


class ReviewBody(MentoringModel):
    """S3에 저장하는 첨삭 본문. 수정 문서가 아니라 제안이다 (F-03 처리 10단계)."""
    review_id: str
    question_intent: str
    overall_feedback: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    missing_questions: list[str] = Field(default_factory=list)
    char_count: CharCount
    posting_basis: PostingBasis
    used_story_ids: list[str] = Field(default_factory=list)
    fact_check_status: FactCheckStatus
    warnings: list[AnalysisWarning] = Field(default_factory=list)
    model_id: str | None = None
    prompt_version: str | None = None


class ReviewRecord(MentoringModel):
    """`REVIEW#{reviewId}` 메타. 원문과 첨삭 본문은 넣지 않는다."""
    schema_version: str = "1.0"
    review_id: str
    owner_user_id: str
    status: TaskStatus
    task_id: str
    document_type: DocumentType
    document_id: str | None = None
    document_version: int | None = None
    input_key: str | None = None
    analysis_id: str | None = None
    job_posting_id: str | None = None
    source_job_snapshot_id: str | None = None
    workspace_id: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    question_text: str | None = None
    max_characters: int | None = None
    story_ids: list[str] = Field(default_factory=list)
    result_key: str | None = None
    issue_count: int | None = None
    fact_check_status: FactCheckStatus | None = None
    used_story_ids: list[str] = Field(default_factory=list)
    review_reason: str | None = None
    error_code: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


# ---------------------------------------------------------------- 모델 출력 (고정 스키마)
class IssueOut(MentoringModel):
    original_text: str = Field(min_length=1)
    start_char: int | None = None
    end_char: int | None = None
    issue_type: str
    reason: str
    improvement_action: str
    revised_example: str | None = None
    questions: list[str] = Field(default_factory=list)
    used_story_ids: list[str] = Field(default_factory=list)


class ReviewOutput(MentoringModel):
    question_intent: str
    overall_feedback: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[IssueOut] = Field(default_factory=list)
    missing_questions: list[str] = Field(default_factory=list)
