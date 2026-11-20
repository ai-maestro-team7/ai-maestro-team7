"""API 요청·응답 모델. REST와 Action Group이 같은 모델을 쓴다.

필드 이름은 팀 스키마에 맞췄다 (jobPostingId, closesAt, organization).
화면에는 matchScore 숫자 대신 matchLevel 3단계만 보여 준다 (개발계획서2 §4.4).
"""

from typing import Any

from pydantic import Field

from .base import OppModel
from .enums import (
    CareerType,
    CompareKey,
    ConditionResult,
    EligibilityStatus,
    LeaveReason,
    MatchLevel,
    NotificationType,
    OrgType,
    PolicyBucket,
    PolicyEligibilityStatus,
    PolicyStage,
    RegionalTalentStatus,
    SavedKind,
    Selection,
    Sort,
    TrackEvent,
    WorkspaceStatus,
)
from .policy import PolicyBenefit
from .posting import Badge, Job, PostingSnapshot, Salary, WorkRegion
from .profile import NotificationPrefs
from .region import LocalLifeView
from .user_state import Notification


# ---------------------------------------------------------------- 지원 자격
class EligibilityCondition(OppModel):
    rule_id: str | None = None
    type: str | None = None
    result: ConditionResult
    reason: str | None = None
    source_quote: str | None = None


class EligibilityResult(OppModel):
    """`backend/eligibility.py`의 `evaluate_eligibility` 결과와 같은 모양이다."""

    status: EligibilityStatus
    conditions: list[EligibilityCondition] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    rule_version: str | None = None


# ---------------------------------------------------------------- 피드 (B-03)
class PostingCard(OppModel):
    job_posting_id: str
    title: str
    organization: str
    org_type: OrgType = OrgType.PRIVATE
    work_region: WorkRegion
    is_busan: bool = False
    is_capital_area: bool = False
    job: Job
    closes_at: str
    rolling: bool = False
    salary: Salary
    career_type: CareerType = CareerType.UNKNOWN  # 신입/경력 (개발계획서4 §9)
    match_score: float
    match_level: MatchLevel
    rank_score: float | None = None
    eligibility: EligibilityResult | None = None
    badges: list[Badge] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)  # 근거 사실. 문장이 아니라 사실 목록
    busan_alternatives_count: int | None = None     # 수도권 공고에만
    commute_minutes: int | None = None              # 거주 구 → 근무 구 대중교통 분. 값이 있을 때만
    distance_km: float | None = None                # 구청 사이 직선거리 (km)
    is_sample: bool = False


class Ranking(OppModel):
    sort: Sort
    basis: str  # 정렬 기준 문구. 화면에 칩으로 보여 준다
    busan_boost: float | None = None


class FeedResponse(OppModel):
    items: list[PostingCard] = Field(default_factory=list)
    ranking: Ranking
    data_as_of: str | None = None
    stale: bool = False
    next_cursor: str | None = None
    ask_leave_reason: bool = False  # 지역 필터를 수도권으로 처음 바꿨을 때 한 번
    empty_message: str | None = None


# ---------------------------------------------------------------- 대안 (B-05)
class AlternativeItem(OppModel):
    job_posting_id: str
    title: str
    organization: str
    work_region: WorkRegion
    closes_at: str
    similarity: float
    match_score: float
    match_level: MatchLevel
    alt_score: float | None = None
    badges: list[Badge] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    why_shown: str
    is_sample: bool = False


class AlternativesResponse(OppModel):
    base_job_posting_id: str
    alternatives: list[AlternativeItem] = Field(default_factory=list)  # 최대 3개
    expanded: bool = False        # 직종 상위 분류로 넓혀 찾았는지
    no_alternative: bool = False  # 넓혀도 없음. 화면은 새 공고 알림을 제안한다
    reason: str | None = None     # ALREADY_BUSAN
    leave_reason_applied: LeaveReason | None = None
    suggest_compare: bool = True  # WANT_SEOUL_LIFE면 false (T-22)
    data_as_of: str | None = None


# ---------------------------------------------------------------- 정책 (B-08)
class PolicyJudgement(OppModel):
    status: PolicyEligibilityStatus
    reasons: list[str] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)  # 직접 확인할 조건


class PolicyApplicationView(OppModel):
    apply_start: str | None = None
    apply_end: str | None = None
    expected: str | None = None
    selection: Selection | None = None
    last_competition: str | None = None


class PolicyCard(OppModel):
    policy_id: str
    title: str
    summary: str | None = None
    category: str | None = None
    stage: PolicyStage
    bucket: PolicyBucket
    eligibility: PolicyJudgement
    benefit: PolicyBenefit | None = None
    application: PolicyApplicationView
    exclusive_with: list[str] = Field(default_factory=list)
    alert_available: bool = False
    alert_subscribed: bool = False
    url: str | None = None
    source: str
    as_of: str | None = None
    checklist: list[str] | None = None  # 상세에서만


class ProfileUsed(OppModel):
    age_range: str | None = None
    residence: str | None = None
    employment: str | None = None
    income: str | None = None


class PolicyTotals(OppModel):
    """본인 저축분은 더하지 않는다."""

    guaranteed_if_eligible: int = 0  # 자격만 맞으면 받는 지원
    selective_max: int = 0           # 선정되면 최대
    unit: str = "MANWON"
    note: str | None = None


class PolicyWalletResponse(OppModel):
    profile_used: ProfileUsed
    buckets: dict[PolicyBucket, list[PolicyCard]]
    totals: PolicyTotals
    data_as_of: str | None = None


class PolicyDetailResponse(OppModel):
    policy: PolicyCard
    data_as_of: str | None = None


class RegionalPolicyCount(OppModel):
    """한 지역에 산다고 가정했을 때 맞는 지역 정책. 온통청년 출처만 센다 (T-06)."""

    sido: str
    count: int
    selective_max: int = 0
    guaranteed_if_eligible: int = 0
    national_common: int = 0  # 전국 공통 정책 수 (어디서든 같음)
    policy_ids: list[str] = Field(default_factory=list)


class PolicyBrief(OppModel):
    policy_id: str
    title: str
    bucket: PolicyBucket
    status: PolicyEligibilityStatus
    summary: str | None = None


# ---------------------------------------------------------------- 상세 (B-04)
class RegionalTalentView(OppModel):
    status: RegionalTalentStatus
    basis: str | None = None
    message: str | None = None  # "…대상일 수 있어요 · 공고문 확인"


class PostingDetailResponse(OppModel):
    posting: PostingSnapshot
    is_busan: bool
    is_capital_area: bool
    closed: bool = False  # 마감된 공고는 오류가 아니라 closed=true
    is_sample: bool = False
    match_level: MatchLevel | None = None
    eligibility: EligibilityResult
    badges: list[Badge] = Field(default_factory=list)
    regional_talent: RegionalTalentView | None = None
    related_policies: list[PolicyBrief] = Field(default_factory=list)
    alternatives_preview: list[AlternativeItem] = Field(default_factory=list)  # 수도권 공고면 최대 2개
    local_life: LocalLifeView | None = None  # 부산 공고에만
    facts: list[str] = Field(default_factory=list)
    data_as_of: str | None = None


class ExplanationResponse(OppModel):
    job_posting_id: str
    sentences: list[str]
    facts: list[str]
    cached: bool = False


# ---------------------------------------------------------------- 비교 (B-06)
class CompareSide(OppModel):
    job_posting_id: str
    label: str


class CompareRow(OppModel):
    """값만 나란히 둔다. 승패 표시는 하지 않는다."""

    key: CompareKey
    label: str
    base: Any = None
    alt: Any = None
    comparable: bool | None = None
    source: str | None = None
    as_of: str | None = None
    assumption: str | None = None
    note: str | None = None
    is_regional_average: bool | None = None
    national_common: int | None = None


class CostAdjusted(OppModel):
    available: bool
    reason: str | None = None  # SALARY_NOT_COMPARABLE, HOUSING_UNAVAILABLE
    base: int | None = None    # 세전 월 급여(공고 하한) − 월 주거비
    alt: int | None = None
    unit: str | None = None


class CompareResponse(OppModel):
    base: CompareSide
    alt: CompareSide
    rows: list[CompareRow]
    cost_adjusted: CostAdjusted
    family_housing_option: bool = True
    family_housing_applied: bool = False
    suggest_more: bool = True  # WANT_SEOUL_LIFE면 추가 안내를 하지 않는다
    data_as_of: str | None = None


# ---------------------------------------------------------------- 저장 (B-09)
class SaveRequest(OppModel):
    job_posting_id: str
    kind: SavedKind = SavedKind.INTEREST
    from_alternative_of: str | None = None


class SavedView(OppModel):
    job_posting_id: str
    kind: SavedKind
    status: WorkspaceStatus
    is_busan: bool
    saved_at: str
    workspace_id: str | None = None
    title: str | None = None
    organization: str | None = None
    closes_at: str | None = None


class ScheduleView(OppModel):
    type: NotificationType
    at: str
    label: str


class SaveResponse(OppModel):
    saved: SavedView
    schedules: list[ScheduleView] = Field(default_factory=list)
    ask_leave_reason: bool = False
    created: bool = True  # 이미 저장돼 있었으면 false


class SavedListResponse(OppModel):
    items: list[SavedView] = Field(default_factory=list)


# ---------------------------------------------------------------- 설정 (B-07)
class PreferencesView(OppModel):
    sort: Sort
    leave_reason: LeaveReason | None = None
    notifications: NotificationPrefs
    receiving_policies: list[str] = Field(default_factory=list)


class PreferencesUpdate(OppModel):
    """보낸 필드만 바꾼다."""

    sort: Sort | None = None
    leave_reason: LeaveReason | None = None
    notifications: NotificationPrefs | None = None
    receiving_policies: list[str] | None = None


# ---------------------------------------------------------------- 알림 (B-10)
class PolicyAlertView(OppModel):
    policy_id: str
    scheduled_at: str


class PolicyAlertResponse(OppModel):
    alert: PolicyAlertView
    created: bool = True


class NotificationsResponse(OppModel):
    items: list[Notification] = Field(default_factory=list)
    next_cursor: str | None = None


class DemoClockRequest(OppModel):
    as_of: str


class DemoClockResponse(OppModel):
    as_of: str
    fired: int
    simulated: bool = True


class TrackRequest(OppModel):
    event: TrackEvent
    job_posting_id: str | None = None
    policy_id: str | None = None


class RegionalTalentResponse(OppModel):
    """Action Group `/agent/postings/{id}/regional-talent`."""

    job_posting_id: str
    organization: str
    regional_talent: RegionalTalentView


# ---------------------------------------------------------------- 질문하기 (RAG)
class AskRequest(OppModel):
    question: str


class AskSource(OppModel):
    """답의 근거. quote는 원문에 실제로 있는 문장이어야 한다."""

    kind: str  # POLICY, POSTING
    id: str
    title: str
    quote: str | None = None
    url: str | None = None
    as_of: str | None = None


class AskResponse(OppModel):
    """정책·공고 원문을 근거로 한 답. 근거를 못 찾았거나 검증에 실패하면 answered=false이고 answer는 없다."""

    question: str
    answered: bool
    answer: str | None = None
    sources: list[AskSource] = Field(default_factory=list)
    related_policies: list[PolicyBrief] = Field(default_factory=list)  # 검색된 정책과 규칙 판정 결과
    manual_checks: list[str] = Field(default_factory=list)             # 직접 확인할 조건
    notice: str | None = None
    data_as_of: str | None = None


# ---------------------------------------------------------------- 부산 기업 둘러보기 (B-D01)
class CompanyCard(OppModel):
    """회사 정보만 보여 준다. 채용 여부·직무·급여를 지어내지 않는다 (DECISIONS.md B-D01)."""

    company_id: str
    name: str
    industry: str | None = None
    size: str | None = None
    district: str | None = None        # 소재 구·군 (원문)
    main_product: str | None = None
    badges: list[Badge] = Field(default_factory=list)  # 출처·기준일이 있는 것만
    open_postings: int = 0             # 지금 우리 데이터에 있는 이 회사의 진행 중 공고 수
    facts: list[str] = Field(default_factory=list)
    source: str
    as_of: str


class CompaniesResponse(OppModel):
    items: list[CompanyCard] = Field(default_factory=list)
    basis: str          # 어떤 기준으로 골랐는지 (화면에 보여 준다)
    notice: str | None = None  # "채용 여부는 회사 채용 페이지에서 확인하세요"
    data_as_of: str | None = None
