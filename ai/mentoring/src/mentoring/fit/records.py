"""직무 적합도 분석의 요청·저장·공고 읽기 모델 (mentoring-fit-review-learning Requirement 2~8, 개발계획서1 §4.5·§6.3).

저장 키는 `team07-career-mentor`의 `ANALYSIS#{analysisId}`다 (db-schema §2.1). 결과는 고치지 않고, 상태만
작업(`TASK#`) 진행에 맞춰 바꾼다.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from mentoring.models import EvidenceLevel, TaskStatus
from mentoring.models.base import MentoringModel, RequestModel

from .models import CategoryBreakdown, GapResult, RequirementCategory

AssessmentMode = Literal["POSTING", "NCS_GENERAL"]
EligibilityStatus = Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_VERIFICATION"]

# 분석 상태 사유 (Requirement 2 기준 3, Requirement 8 기준 4)
POSTING_NOT_READY = "POSTING_NOT_READY"
# 경고 코드 (화면은 message를 보여 준다)
W_NOTICE = "NOT_PROBABILITY"
W_EXPIRED = "POSTING_EXPIRED"
W_NCS_AMBIGUOUS = "NCS_AMBIGUOUS"
W_NO_EVIDENCE = "NO_EVIDENCE"
W_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
W_ELIGIBILITY_UNAVAILABLE = "ELIGIBILITY_UNAVAILABLE"
W_BASIC_PROFILE_MISSING = "BASIC_PROFILE_MISSING"
W_NOT_POSTING = "NOT_POSTING_SPECIFIC"
W_SUMMARY_UNAVAILABLE = "SUMMARY_UNAVAILABLE"


class AnalysisRequest(RequestModel):
    """`POST /analyses` 본문 (개발계획서1 §6.3)."""
    profile_id: str
    profile_version: int | None = Field(default=None, ge=1)
    job_posting_id: str | None = None
    target_ncs_code: str | None = None
    workspace_id: str | None = None


# ---------------------------------------------------------------- 공고 (B 소유 catalog, 읽기만)
class PostingRequirement(MentoringModel):
    requirement_id: str
    name: str
    kind: str  # REQUIRED_SKILL / PREFERRED_SKILL (D-10)
    weight: float = 1.0
    source_quote: str | None = None


class PostingJob(MentoringModel):
    name: str | None = None
    ncs_codes: list[str] = Field(default_factory=list)


class PostingLatestView(MentoringModel):
    """`POSTING#{id}` / `LATEST`에서 A가 쓰는 칸만."""
    job_posting_id: str
    snapshot_id: str
    is_expired: bool = False


class PostingSnapshotView(MentoringModel):
    """`POSTING#{id}` / `SNAP#{snapshotId}`에서 A가 쓰는 칸만 (db-schema §3, contracts `PostingForAnalysis`).
    요건과 자격 조건은 B가 원문 인용과 함께 저장한 값을 그대로 쓰고 LLM으로 바꾸지 않는다."""
    job_posting_id: str
    snapshot_id: str
    title: str
    organization: str
    job: PostingJob = Field(default_factory=PostingJob)
    requirements: list[PostingRequirement] = Field(default_factory=list)
    eligibility_rules: list[dict[str, Any]] = Field(default_factory=list)
    closes_at: str | None = None
    official_url: str | None = None
    checked_at: str | None = None
    source_type: str | None = None
    extract_status: str | None = None  # B: PENDING / DONE / FAILED


# ---------------------------------------------------------------- 분석 결과
class EvidenceQuote(MentoringModel):
    evidence_id: str
    quoted_text: str


class RequirementLink(MentoringModel):
    """요건 하나와 프로필 근거의 연결. 근거 단계는 코드가 정한다 (Requirement 4 기준 4)."""
    requirement_id: str
    name: str
    category: RequirementCategory
    weight: float = Field(gt=0)
    source_quote: str | None = None
    ncs_unit_code: str | None = None
    evidence_level: EvidenceLevel
    skill_ids: list[str] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    question: str | None = None  # 미확인 요건에 묻는 확인 질문 (Requirement 4 기준 5)


class EligibilityCondition(MentoringModel):
    rule_id: str | None = None
    type: str | None = None
    result: str  # MET / NOT_MET / UNKNOWN (backend/eligibility.py)
    reason: str | None = None
    source_quote: str | None = None


class Citation(MentoringModel):
    """KB 검색 근거 (개발계획서1 §8.2 KnowledgeCitation). retrievalScore는 신뢰도가 아니라서 저장하지 않는다."""
    document_id: str
    document_type: str | None = None
    role: Literal["NCS_JOB_PROFILE", "GUIDANCE"]  # 방법론 문서는 NCS 필수 능력의 출처가 아니다 (Requirement 7 기준 5)
    source_url: str
    checked_at: str
    excerpt: str | None = None
    retrieved_at: str


class AnalysisWarning(MentoringModel):
    code: str
    message: str


class JobFitAnalysis(MentoringModel):
    schema_version: str = "1.0"
    analysis_id: str
    owner_user_id: str
    status: TaskStatus
    task_id: str
    assessment_mode: AssessmentMode
    profile_id: str
    profile_version: int = Field(ge=1)
    workspace_id: str | None = None
    # 공고 (POSTING 모드). 분석 시점의 스냅샷을 고정한다 (UT-19)
    job_posting_id: str | None = None
    snapshot_id: str | None = None
    posting_title: str | None = None
    organization: str | None = None
    official_url: str | None = None
    closes_at: str | None = None
    is_expired: bool | None = None
    source_checked_at: str | None = None
    # NCS
    ncs_code: str | None = None
    ncs_name: str | None = None
    ncs_candidates: list[str] = Field(default_factory=list)
    requested_ncs_code: str | None = None
    # 결과
    requirements: list[RequirementLink] = Field(default_factory=list)
    score_type: str = "DOCUMENT_BASED_MATCH"
    score_status: Literal["SCORED", "INSUFFICIENT_REQUIREMENTS"] | None = None
    fit_score: int | None = Field(default=None, ge=0, le=100)
    potential_upper_bound: int | None = Field(default=None, ge=0, le=100)
    score_policy_version: str | None = None
    category_breakdown: dict[str, CategoryBreakdown] = Field(default_factory=dict)
    eligibility_status: EligibilityStatus | None = None
    eligibility_conditions: list[EligibilityCondition] = Field(default_factory=list)
    rule_version: str | None = None
    gaps: GapResult | None = None
    summary: str | None = None
    sources: list[Citation] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)
    review_reason: str | None = None
    error_code: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


# ---------------------------------------------------------------- 모델 출력 (고정 스키마)
class LinkOut(MentoringModel):
    requirement_id: str
    skill_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    question: str | None = None


class LinkOutput(MentoringModel):
    """요건–근거 연결 응답. 근거 단계·점수 같은 판단 칸은 받지 않는다 (받아도 무시)."""
    links: list[LinkOut] = Field(default_factory=list)


class SummaryOutput(MentoringModel):
    summary: str
