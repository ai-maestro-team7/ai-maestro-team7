"""정책 지갑 (B-08). 판정은 규칙으로 하고, 서울과 부산을 같은 함수로 계산한다.

담당 워크트리: core-policy. 명세: 개발계획서2 §4.2 B-08. 테스트: T-06, T-07, T-12, T-13, T-14.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import (
    PolicyApplicationView,
    PolicyBrief,
    PolicyCard,
    PolicyDetailResponse,
    PolicyJudgement,
    PolicyTotals,
    PolicyWalletResponse,
    ProfileUsed,
    RegionalPolicyCount,
)
from ..models.enums import (
    EmploymentStatus,
    MoneyUnit,
    PeriodType,
    PolicyBucket,
    PolicyEligibilityStatus,
    PolicySource,
    PolicyStage,
    RegionScope,
    Selection,
)
from ..models.errors import policy_not_found
from ..models.policy import ALWAYS_APPLY_END, IncomeRule, Policy
from ..models.posting import PostingLatest
from ..models.profile import BasicProfile, OppPrefs
from . import clock, copy_rules, regions
from .context import load_context

Status = PolicyEligibilityStatus

# 판정 우선순위. 앞에 있을수록 강하다
_PRIORITY = (Status.NOT_ELIGIBLE, Status.AFTER_EMPLOYMENT, Status.CHECK_NEEDED, Status.ELIGIBLE)

_EMPLOYMENT_LABEL = {
    EmploymentStatus.UNEMPLOYED: "미취업",
    EmploymentStatus.EMPLOYED: "취업",
    EmploymentStatus.STUDENT: "학생",
}

# 구 이름. 사유 문구와 profileUsed에만 쓴다 (판정은 코드로 한다). 공용 regions.py로 옮길 후보다
_SIGUNGU_NAMES = {
    "26110": "중구", "26140": "서구", "26170": "동구", "26200": "영도구", "26230": "부산진구",
    "26260": "동래구", "26290": "남구", "26320": "북구", "26350": "해운대구", "26380": "사하구",
    "26410": "금정구", "26440": "강서구", "26470": "연제구", "26500": "수영구", "26530": "사상구",
    "26710": "기장군",
}


def _region_label(sido: str | None, sigungu: str | None = None) -> str | None:
    name = regions.sido_name(sido)
    if name is None:
        return None
    gu = _SIGUNGU_NAMES.get(sigungu or "")
    return f"{name} {gu}" if gu else name


def _target_label(targets: list[EmploymentStatus]) -> str:
    if targets == [EmploymentStatus.UNEMPLOYED]:
        return "취업 준비 청년 대상"
    if targets == [EmploymentStatus.EMPLOYED]:
        return "일하는 청년 대상"
    return "대상 " + "·".join(_EMPLOYMENT_LABEL[t] for t in targets)


# ---------------------------------------------------------------- 조건별 판정
def _judge_employment(policy: Policy, profile: BasicProfile) -> tuple[Status, str] | None:
    targets = policy.eligibility.employment
    if not targets:
        return None
    label = _target_label(targets)
    mine = profile.employment_status
    if mine is None:
        return Status.CHECK_NEEDED, f"{label}: 취업 상태 확인 필요"
    if mine in targets:
        return Status.ELIGIBLE, f"{label}: {_EMPLOYMENT_LABEL[mine]} 충족"
    if targets == [EmploymentStatus.EMPLOYED] and mine in (EmploymentStatus.UNEMPLOYED, EmploymentStatus.STUDENT):
        return Status.AFTER_EMPLOYMENT, f"{label}: 지금은 {_EMPLOYMENT_LABEL[mine]}"
    return Status.NOT_ELIGIBLE, f"{label}: 지금은 {_EMPLOYMENT_LABEL[mine]}"


def _judge_age(policy: Policy, profile: BasicProfile, as_of: datetime) -> tuple[Status, str] | None:
    low = policy.eligibility.age_min if policy.eligibility.age_min is not None else policy.age_min
    high = policy.eligibility.age_max if policy.eligibility.age_max is not None else policy.age_max
    if low is None and high is None:
        return None
    span = f"{low if low is not None else ''}~{high if high is not None else ''}세"
    if profile.birth_year is None:
        return Status.CHECK_NEEDED, f"나이 {span} 대상: 생년 확인 필요"

    def inside(age: int) -> bool:
        return (low is None or age >= low) and (high is None or age <= high)

    before, after = clock.age_range(profile.birth_year, as_of)
    hits = inside(before) + inside(after)
    if hits == 2:
        return Status.ELIGIBLE, f"나이 {span} 충족"
    if hits == 1:  # 생일 전후로 갈린다 (T-12)
        return Status.CHECK_NEEDED, f"나이 {span} 대상: 만 {before}~{after}세라 생일에 따라 달라 확인 필요"
    return Status.NOT_ELIGIBLE, f"나이 {span} 대상: 만 {before}~{after}세"


def _judge_residence(policy: Policy, profile: BasicProfile,
                     assumed_sido: str | None) -> tuple[Status, str]:
    areas = policy.regions
    if not areas or any(r.scope == RegionScope.NATIONAL for r in areas):
        return Status.ELIGIBLE, "전국 대상"
    sido = assumed_sido or profile.residence_sido
    if sido is None:
        return Status.CHECK_NEEDED, "거주지 미입력: 확인 필요"
    for r in areas:
        if r.scope == RegionScope.SIDO and r.sido == sido:
            return Status.ELIGIBLE, f"{_region_label(sido)} 거주 충족"
    for r in areas:
        if r.scope != RegionScope.SIGUNGU or r.sido != sido:
            continue
        label = _region_label(r.sido, r.sigungu)
        if assumed_sido is not None:  # 구까지는 가정하지 않는다
            return Status.CHECK_NEEDED, f"{label} 거주 대상: 구 확인 필요"
        if profile.residence_sigungu == r.sigungu:
            return Status.ELIGIBLE, f"{label} 거주 충족"
    names = ", ".join(_region_label(r.sido, r.sigungu) or "-" for r in areas)
    return Status.NOT_ELIGIBLE, f"{names} 거주 대상: 거주지가 달라요"


def _judge_income(policy: Policy, profile: BasicProfile) -> tuple[Status, str] | None:
    rule = policy.eligibility.income
    if rule is None and policy.income_rule:
        rule = IncomeRule(text=policy.income_rule)
    if rule is None:
        return None
    checks: list[bool] = []
    if rule.max_monthly_income is not None and profile.monthly_income is not None:
        checks.append(profile.monthly_income <= rule.max_monthly_income)
    if rule.max_household_level is not None and profile.household_income_level is not None:
        checks.append(profile.household_income_level <= rule.max_household_level)
    if not checks:  # 소득을 입력하지 않았거나 원문 기준이라 잴 수 없다 (T-13)
        return Status.CHECK_NEEDED, f"소득 조건({rule.text}): 확인 필요"
    if all(checks):
        return Status.ELIGIBLE, f"소득 조건({rule.text}) 충족"
    return Status.NOT_ELIGIBLE, f"소득 조건({rule.text}) 넘음"


def _judge_exclusive(policy: Policy, prefs: OppPrefs) -> tuple[Status, str] | None:
    receiving = {name.strip() for name in prefs.receiving_policies if name.strip()}
    clash = [name for name in policy.exclusive_with if name.strip() in receiving]
    if not clash:
        return None
    return Status.NOT_ELIGIBLE, f"중복 불가: {', '.join(clash)} 받는 중"


def judge_policy(policy: Policy, profile: BasicProfile, prefs: OppPrefs, *, as_of: datetime,
                 assumed_sido: str | None = None) -> PolicyJudgement:
    """정책 하나를 판정한다. assumed_sido를 주면 그 시·도에 산다고 가정한다 (비교 패널).

    나이가 범위 경계에 걸치면 CHECK_NEEDED (T-12), 소득 조건이 있는데 미입력이면 CHECK_NEEDED (T-13),
    받는 중인 정책과 중복 불가면 NOT_ELIGIBLE (T-14). 자유 서술 조건은 판정에 쓰지 않고 manualChecks로 돌려준다.
    """
    results = [
        _judge_employment(policy, profile),
        _judge_age(policy, profile, as_of),
        _judge_residence(policy, profile, assumed_sido),
        _judge_income(policy, profile),
        _judge_exclusive(policy, prefs),
    ]
    results = [r for r in results if r is not None]
    statuses = {status for status, _ in results}
    status = next((s for s in _PRIORITY if s in statuses), Status.ELIGIBLE)
    return PolicyJudgement(status=status, reasons=[reason for _, reason in results],
                           manual_checks=list(policy.eligibility.manual_checks))


# ---------------------------------------------------------------- 신청 시기와 칸
_OPEN, _UPCOMING, _NEXT, _ENDED = "OPEN", "UPCOMING", "NEXT", "ENDED"


def _timing(policy: Policy, as_of: datetime) -> str:
    """신청 시기. OPEN(지금), UPCOMING(아직 안 열림), NEXT(지났고 다음 일정 있음), ENDED(다음 일정 없음)."""
    period = policy.application.period_type
    if period in (PeriodType.ALWAYS, PeriodType.MONTHLY):
        return _OPEN
    today = clock.day(as_of)
    has_next = policy.last_cycle is not None or bool(policy.application.expected)
    if period == PeriodType.TBD:
        return _NEXT if has_next else _ENDED
    if policy.apply_start and today < policy.apply_start:
        return _UPCOMING
    if policy.apply_end == ALWAYS_APPLY_END or today <= policy.apply_end:
        return _OPEN
    return _NEXT if has_next else _ENDED


def _bucket(policy: Policy, judgement: PolicyJudgement, profile: BasicProfile, timing: str) -> PolicyBucket:
    """칸을 정하는 순서:
    1. 판정이 NOT_ELIGIBLE이면 CLOSED (접어 둠)
    2. 정착 단계(SETTLE)인데 아직 취업 전이면 SETTLEMENT
    3. 판정이 AFTER_EMPLOYMENT면 AFTER_EMPLOYMENT
    4. 지금 신청 기간이거나 상시·매월이면 OPEN_NOW
    5. 아직 안 열렸거나, 지났지만 작년 일정·다음 예정이 있으면 NEXT_CYCLE
    6. 그 밖(다음 일정 없는 마감)은 CLOSED
    """
    if judgement.status == Status.NOT_ELIGIBLE:
        return PolicyBucket.CLOSED
    if policy.stage == PolicyStage.SETTLE and profile.employment_status != EmploymentStatus.EMPLOYED:
        return PolicyBucket.SETTLEMENT
    if judgement.status == Status.AFTER_EMPLOYMENT:
        return PolicyBucket.AFTER_EMPLOYMENT
    if timing == _OPEN:
        return PolicyBucket.OPEN_NOW
    if timing in (_UPCOMING, _NEXT):
        return PolicyBucket.NEXT_CYCLE
    return PolicyBucket.CLOSED


def _public_amount(policy: Policy) -> int | None:
    """시 지원분만. 본인 저축분(selfShareMax)은 쓰지 않는다."""
    if policy.benefit is not None:
        if policy.benefit.unit != MoneyUnit.MANWON:
            return None
        if policy.benefit.public_share_max is not None:
            return policy.benefit.public_share_max
    return policy.amount_max


def _visible(deps: Deps, policy: Policy | None) -> bool:
    return policy is not None and (policy.verified or not deps.config.policies.hide_unverified)


def _card(deps: Deps, user_id: str, policy: Policy, profile: BasicProfile, prefs: OppPrefs, as_of: datetime, *,
          with_checklist: bool = False, subscribed: set[str] | None = None) -> PolicyCard:
    """subscribed: 이 사용자가 알림을 신청한 정책 ID. 목록에서는 한 번에 읽어 넘긴다 (정책마다 읽으면 수백 번 조회)."""
    judgement = judge_policy(policy, profile, prefs, as_of=as_of)
    timing = _timing(policy, as_of)
    bucket = _bucket(policy, judgement, profile, timing)
    show_dates = timing in (_OPEN, _UPCOMING)
    application = PolicyApplicationView(
        apply_start=policy.apply_start if show_dates else None,
        apply_end=policy.apply_end if show_dates and policy.apply_end != ALWAYS_APPLY_END else None,
        expected=policy.application.expected,
        selection=policy.application.selection,
        last_competition=policy.application.last_competition,
    )
    return PolicyCard(
        policy_id=policy.policy_id, title=policy.title, summary=policy.summary, category=policy.category,
        stage=policy.stage, bucket=bucket, eligibility=judgement, benefit=policy.benefit, application=application,
        exclusive_with=list(policy.exclusive_with),
        alert_available=judgement.status != Status.NOT_ELIGIBLE and timing in (_UPCOMING, _NEXT),
        alert_subscribed=(policy.policy_id in subscribed if subscribed is not None
                          else deps.users.get_alert(user_id, policy.policy_id) is not None),
        url=policy.url, source=str(policy.source), as_of=policy.as_of,
        checklist=list(policy.checklist) if with_checklist else None,
    )


def _profile_used(profile: BasicProfile, as_of: datetime) -> ProfileUsed:
    age = None
    if profile.birth_year is not None:
        before, after = clock.age_range(profile.birth_year, as_of)
        age = f"{before}~{after}"
    has_income = profile.monthly_income is not None or profile.household_income_level is not None
    return ProfileUsed(
        age_range=age,
        residence=_region_label(profile.residence_sido, profile.residence_sigungu),
        employment=str(profile.employment_status) if profile.employment_status else "UNKNOWN",
        income="ENTERED" if has_income else "UNKNOWN",
    )


def _user_policies(deps: Deps, profile: BasicProfile) -> list[Policy]:
    """사용자 시·도 정책과 전국 정책. 숨길 정책은 뺀다."""
    keys = [k for k in (profile.residence_sido, regions.NATIONAL) if k]
    seen: dict[str, Policy] = {}
    for key in dict.fromkeys(keys):
        for policy in deps.catalog.query_policies(key):
            if _visible(deps, policy) and policy.policy_id not in seen:
                seen[policy.policy_id] = policy
    return list(seen.values())


# ---------------------------------------------------------------- 공개 함수
def match_policies(deps: Deps, user_id: str, *, stage: PolicyStage | None = None,
                   as_of: str | date | datetime | None = None) -> PolicyWalletResponse:
    """정책 지갑. OPEN_NOW, NEXT_CYCLE, AFTER_EMPLOYMENT, SETTLEMENT, CLOSED로 나눈다.

    verified=false 정책은 내보내지 않는다 (T-07). 합계는 자격만 맞으면 받는 금액과 선정돼야 받는 최대 금액으로
    나누고 본인 저축분은 더하지 않는다.
    """
    ctx = load_context(deps, user_id, as_of)
    buckets: dict[PolicyBucket, list[PolicyCard]] = {b: [] for b in PolicyBucket}
    totals = PolicyTotals(note=copy_rules.POLICY_TOTAL_NOTE)
    subscribed = {alert.policy_id for alert in deps.users.list_alerts(user_id)}  # 알림 신청 여부는 한 번만 읽는다
    for policy in _user_policies(deps, ctx.profile):
        if stage is not None and policy.stage != stage:
            continue
        card = _card(deps, user_id, policy, ctx.profile, ctx.prefs, ctx.as_of, subscribed=subscribed)
        buckets[card.bucket].append(card)
        # 합계: 지금 자격이 맞고 신청할 길이 있는(접어 두지 않은) 정책만
        amount = _public_amount(policy)
        if card.eligibility.status != Status.ELIGIBLE or card.bucket == PolicyBucket.CLOSED or amount is None:
            continue
        if policy.application.selection == Selection.AUTOMATIC:
            totals.guaranteed_if_eligible += amount
        else:
            totals.selective_max += amount
    return PolicyWalletResponse(profile_used=_profile_used(ctx.profile, ctx.as_of), buckets=buckets,
                                totals=totals, data_as_of=deps.catalog.data_as_of())


def get_policy(deps: Deps, user_id: str, policy_id: str, *,
               as_of: str | date | datetime | None = None) -> PolicyDetailResponse:
    """정책 상세, 판정 이유, 체크리스트. 없거나 verified=false면 POLICY_NOT_FOUND."""
    policy = deps.catalog.get_policy(policy_id)
    if not _visible(deps, policy):
        raise policy_not_found(policy_id)
    ctx = load_context(deps, user_id, as_of)
    card = _card(deps, user_id, policy, ctx.profile, ctx.prefs, ctx.as_of, with_checklist=True)
    return PolicyDetailResponse(policy=card, data_as_of=deps.catalog.data_as_of())


def _youthcenter(deps: Deps, region_key: str) -> list[Policy]:
    return [p for p in deps.catalog.query_policies(region_key)
            if p.source == PolicySource.YOUTHCENTER and _visible(deps, p)]


def count_regional_policies(deps: Deps, profile: BasicProfile, prefs: OppPrefs, sido: str, *,
                            as_of: datetime) -> RegionalPolicyCount:
    """그 시·도에 산다고 가정했을 때 맞는 지역 정책 수와 금액. 온통청년 출처만 센다 (T-06).

    서울과 부산을 이 함수 하나로 계산한다. 직접 정리한 부산 시드는 세지 않는다.
    """
    result = RegionalPolicyCount(sido=sido, count=0)
    for policy in _youthcenter(deps, sido):
        if judge_policy(policy, profile, prefs, as_of=as_of, assumed_sido=sido).status != Status.ELIGIBLE:
            continue
        result.count += 1
        result.policy_ids.append(policy.policy_id)
        amount = _public_amount(policy)
        if amount is None:
            continue
        if policy.application.selection == Selection.AUTOMATIC:
            result.guaranteed_if_eligible += amount
        else:
            result.selective_max += amount
    result.national_common = sum(
        1 for policy in _youthcenter(deps, regions.NATIONAL)
        if judge_policy(policy, profile, prefs, as_of=as_of, assumed_sido=sido).status == Status.ELIGIBLE)
    return result


def related_policies(deps: Deps, profile: BasicProfile, prefs: OppPrefs, posting: PostingLatest, *,
                     as_of: datetime, limit: int = 3) -> list[PolicyBrief]:
    """이 공고에 취업하면 받을 수 있는 정책 (공고 근무지 기준). 부산 공고가 아니면 빈 목록."""
    if not regions.is_busan(deps.config, posting.work_region):
        return []
    sido = posting.work_region.sido
    hired = profile.model_copy(update={"employment_status": EmploymentStatus.EMPLOYED})
    briefs: list[PolicyBrief] = []
    for policy in deps.catalog.query_policies(sido):
        if len(briefs) >= limit:
            break
        if not _visible(deps, policy) or policy.stage not in (PolicyStage.EMPLOYED, PolicyStage.SETTLE):
            continue
        # 취업했다고 봐도 안 맞으면(나이·거주·중복) 뺀다
        if judge_policy(policy, hired, prefs, as_of=as_of, assumed_sido=sido).status == Status.NOT_ELIGIBLE:
            continue
        # 보여 줄 판정은 지금 상태 기준이다. 지금 안 맞는 것은 취업하면 맞는 것이다
        judgement = judge_policy(policy, profile, prefs, as_of=as_of, assumed_sido=sido)
        if judgement.status == Status.NOT_ELIGIBLE:
            judgement = judgement.model_copy(update={"status": Status.AFTER_EMPLOYMENT})
        bucket = _bucket(policy, judgement, profile, _timing(policy, as_of))
        briefs.append(PolicyBrief(policy_id=policy.policy_id, title=policy.title, bucket=bucket,
                                  status=judgement.status, summary=policy.summary))
    return briefs
