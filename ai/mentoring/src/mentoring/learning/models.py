"""학습 경로 요청·저장·모델 출력 (개발계획서1 F-05, §4.5 `LearningPathResult`, §6.5, db-schema §2.1 `PATH#`)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from mentoring.fit.records import AnalysisWarning
from mentoring.models import TaskStatus
from mentoring.models.base import MentoringModel, RequestModel

TargetKind = Literal["CONFIRMED_GAP", "ELIGIBILITY_GAP", "STRENGTHEN_EVIDENCE", "NCS_UNIT", "DEEPEN_STRENGTH"]


class LearningPathRequest(RequestModel):
    analysis_id: str
    weekly_study_hours: int = Field(ge=1, le=40)
    preferred_format: Literal["ONLINE", "OFFLINE", "HYBRID"] = "HYBRID"
    region_code: str | None = None
    target_date: str | None = None  # YYYY-MM-DD
    start_date: str | None = None
    ncs_code: str | None = None
    workspace_id: str | None = None


class LearningTarget(MentoringModel):
    """코드가 고른 학습 대상. 모델은 이 목록 밖의 능력단위·자격을 넣지 못한다 (Requirement 12 기준 5)."""
    target_id: str
    kind: TargetKind
    name: str
    category: str | None = None          # REQUIRED / PREFERRED (공고 요건일 때)
    requirement_id: str | None = None
    ncs_unit_code: str | None = None
    reference_training_hours: int | None = None  # NCS 훈련시간. 개인 학습 기간이 아니다 (F-05 "훈련시간 ≠ 실제 학습 기간")


class VerificationTask(MentoringModel):
    """학습 전에 먼저 확인할 것 (서류에 없어서 미확인인 요건)."""
    requirement_id: str
    name: str
    question: str


class Week(MentoringModel):
    week: int = Field(ge=1)
    start_date: str
    target_ids: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    deliverable: str | None = None
    estimated_hours: int = Field(ge=0)
    official_sources: list[dict] = Field(default_factory=list)


class ExamRound(MentoringModel):
    round: str | None = None
    dates: dict[str, str] = Field(default_factory=dict)  # writtenExamStart 등 → YYYY-MM-DD
    result_after_posting_deadline: bool | None = None


class CertificateCandidate(MentoringModel):
    qualification_code: str
    name: str
    exam_agency: str | None = None
    linked_unit_codes: list[str] = Field(default_factory=list)
    reason: str
    required_by_posting: bool = False
    schedule: list[ExamRound] | None = None
    verification_status: Literal["VERIFIED", "SCHEDULE_UNVERIFIED"]
    official_url: str
    checked_at: str


class LearningPathRecord(MentoringModel):
    schema_version: str = "1.0"
    learning_path_id: str
    owner_user_id: str
    status: TaskStatus
    task_id: str
    analysis_id: str
    workspace_id: str | None = None
    version: int = 1
    ncs_code: str | None = None
    ncs_name: str | None = None
    weekly_study_hours: int
    preferred_format: str
    region_code: str | None = None
    start_date: str
    target_date: str | None = None
    total_weeks: int | None = None
    total_hours: int | None = None
    estimated: bool = True  # 기간·시간은 추정이다
    targets: list[LearningTarget] = Field(default_factory=list)
    verification_tasks: list[VerificationTask] = Field(default_factory=list)
    weeks: list[Week] = Field(default_factory=list)
    certificates: list[CertificateCandidate] = Field(default_factory=list)
    courses: list[dict] = Field(default_factory=list)
    source_verification_status: dict[str, str] = Field(default_factory=dict)
    related_links: list[dict] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)
    review_reason: str | None = None
    error_code: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


# ---------------------------------------------------------------- 모델 출력 (고정 스키마)
class WeekOut(MentoringModel):
    week: int
    goals: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    deliverable: str | None = None


class PlanOutput(MentoringModel):
    weeks: list[WeekOut] = Field(default_factory=list)
