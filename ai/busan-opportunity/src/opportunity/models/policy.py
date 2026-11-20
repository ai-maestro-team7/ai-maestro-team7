"""청년정책 모델. `team07-catalog`의 POLICY#{policyId}/META와 같은 모양이다 (`docs/db-schema.md` §3)."""

from pydantic import Field

from .base import OppModel
from .enums import (
    EmploymentStatus,
    MoneyUnit,
    PeriodType,
    PolicyKind,
    PolicySource,
    PolicyStage,
    RegionScope,
    Selection,
)

ALWAYS_APPLY_END = "9999-12-31"  # 상시 정책


class PolicyRegion(OppModel):
    scope: RegionScope
    sido: str | None = None
    sigungu: str | None = None


class IncomeRule(OppModel):
    """소득 조건. 조건이 있는데 사용자가 소득을 입력하지 않았으면 CHECK_NEEDED (T-13)."""

    text: str
    max_monthly_income: int | None = None  # 만 원
    max_household_level: int | None = None  # 중위소득 %


class PolicyEligibility(OppModel):
    age_min: int | None = None
    age_max: int | None = None
    employment: list[EmploymentStatus] | None = None  # None이면 제한 없음
    income: IncomeRule | None = None
    student: bool | None = None
    residence_min_months: int | None = None
    manual_checks: list[str] = Field(default_factory=list)  # 자유 서술 조건. 판정에 쓰지 않고 그대로 보여 준다


class PolicyBenefit(OppModel):
    """본인 저축이 섞인 정책은 시 지원분(publicShareMax)과 본인분(selfShareMax)을 따로 둔다."""

    text: str
    public_share_max: int | None = None
    self_share_max: int | None = None
    unit: MoneyUnit = MoneyUnit.MANWON
    period: str | None = None


class PolicyApplication(OppModel):
    period_type: PeriodType = PeriodType.FIXED
    selection: Selection = Selection.REVIEW
    last_competition: str | None = None
    expected: str | None = None  # 다음 모집 예정 문구 (작년 일정 기준)


class PolicyCycle(OppModel):
    start: str
    end: str


class Policy(OppModel):
    policy_id: str
    kind: PolicyKind = PolicyKind.POLICY
    title: str
    summary: str | None = None
    amount_max: int | None = None  # 시 지원분 최대 (만 원). 본인 저축은 넣지 않는다
    age_min: int | None = None
    age_max: int | None = None
    residence_rule: str | None = None
    income_rule: str | None = None
    apply_start: str | None = None
    apply_end: str = ALWAYS_APPLY_END
    url: str | None = None
    source: PolicySource
    as_of: str | None = None
    regions: list[PolicyRegion] = Field(default_factory=list)
    category: str | None = None  # JOB, HOUSING, ASSET, EDUCATION, WELFARE …
    stage: PolicyStage = PolicyStage.PREPARE
    eligibility: PolicyEligibility = Field(default_factory=PolicyEligibility)
    benefit: PolicyBenefit | None = None
    application: PolicyApplication = Field(default_factory=PolicyApplication)
    last_cycle: PolicyCycle | None = None
    exclusive_with: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    verified: bool = False  # false면 화면에 내보내지 않는다 (T-07)
    verified_by: str | None = None
    verified_at: str | None = None
    youthcenter_id: str | None = None

    def region_key(self) -> str:
        """GSI1PK에 쓰는 시·도 키. 전국은 00, 구 단위 정책도 시·도 키에 둔다."""
        for region in self.regions:
            if region.scope != RegionScope.NATIONAL and region.sido:
                return region.sido
        return "00"
