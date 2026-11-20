"""나란히 비교 (B-06). 값만 나란히 두고 승패는 표시하지 않는다. 서울이 높은 칸도 그대로 보여 준다.

담당 워크트리: core-policy. 명세: 개발계획서2 §4.2 B-06, §5.5. 테스트: T-05, T-06, T-22.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import CompareResponse, CompareRow, CompareSide, CostAdjusted
from ..models.enums import BadgeType, CompareKey, LeaveReason, MoneyUnit, RegionalTalentStatus
from ..models.errors import posting_not_found
from ..models.posting import PostingLatest
from ..models.profile import BasicProfile
from ..models.region import CommuteStat, RentStat
from . import clock, copy_rules, facts, policies, regions
from .context import load_context

MONTHS_PER_YEAR = 12

# 행 이름과 값 문구. copy_rules에 없는 것만 여기 둔다 (공용 파일로 옮길 후보)
LABEL = {
    CompareKey.SALARY: "급여 (공고 기재)",
    CompareKey.HOUSING: "원룸 월 주거비 (환산 중앙값)",
    CompareKey.COMMUTE: "통근 30분 미만 비율 (지역 평균)",
    CompareKey.REGIONAL_POLICY: "나에게 맞는 지역 정책 (온통청년 기준)",
    CompareKey.REGIONAL_TALENT: "지역인재 전형",
    CompareKey.VERIFIED: "시·정부 인증",
}
SALARY_SOURCE = "각 공고"
POLICY_SOURCE = "온통청년"
TALENT_MAYBE = "대상일 수 있음"
TALENT_CHECK = "학교 소재지 확인 필요"
TALENT_NONE = "해당 없음"
TALENT_NOTICE = "공고문 확인 필요"
NO_BADGE = "-"
FAMILY_HOUSING = "가족과 거주"
SAMPLE_FALLBACK_NOTE = "{gu} 표본이 적어 {sido} 전체 값으로 보여드려요"
RENT_ASSUMPTION = "전용 {area}㎡ 이하, 최근 {months}개월, 환산 월세 = 월세 + 보증금 × 전환율({rate}) ÷ 12"


def _half_up(value: float) -> int:
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def _known_sido(posting: PostingLatest) -> str | None:
    return None if posting.work_region.unknown else posting.work_region.sido


def _side(posting: PostingLatest) -> CompareSide:
    return CompareSide(job_posting_id=posting.job_posting_id,
                       label=f"{posting.work_region.label} · {posting.organization}")


def _has_source(stat: RentStat | CommuteStat | None) -> bool:
    return stat is not None and bool(stat.source) and bool(stat.as_of)


def _joined(*values: str) -> str:
    return " / ".join(dict.fromkeys(values))


# ---------------------------------------------------------------- 급여
def _salary_comparable(posting: PostingLatest) -> bool:
    s = posting.salary
    return s.disclosed and (s.min is not None or s.max is not None) and s.unit == MoneyUnit.MANWON_YEAR


def _salary_row(base: PostingLatest, alt: PostingLatest) -> CompareRow:
    def label(p: PostingLatest) -> str:
        return copy_rules.salary_label(p.salary.disclosed, p.salary.min, p.salary.max)

    return CompareRow(key=CompareKey.SALARY, label=LABEL[CompareKey.SALARY], base=label(base), alt=label(alt),
                      comparable=_salary_comparable(base) and _salary_comparable(alt), source=SALARY_SOURCE)


def _monthly_pay(posting: PostingLatest) -> int:
    """세전 월 급여 = 공고 하한 ÷ 12 (만 원, 반올림). 하한이 없으면 적힌 값 하나를 쓴다."""
    low = posting.salary.min if posting.salary.min is not None else posting.salary.max
    return _half_up(low / MONTHS_PER_YEAR)


# ---------------------------------------------------------------- 주거비
def _rent(deps: Deps, posting: PostingLatest) -> tuple[RentStat | None, str | None]:
    """근무지 구 값. 구 표본이 minSample보다 적거나 없으면 시·도 값으로 바꾸고 note를 돌려준다."""
    rent = deps.region_stats.rent
    sido, sigungu = posting.work_region.sido, posting.work_region.sigungu
    gu = rent.get(sigungu) if sigungu else None
    if _has_source(gu) and gu.sample_size >= deps.config.compare.min_sample:
        return gu, None
    city = rent.get(sido)
    if not _has_source(city):
        return None, None
    note = None
    if gu is not None:
        note = SAMPLE_FALLBACK_NOTE.format(gu=gu.label, sido=city.label)
    return city, note


def _housing(deps: Deps, base: PostingLatest, alt: PostingLatest,
             family_housing: bool) -> tuple[CompareRow | None, tuple[int, int] | None, bool]:
    """(행, (base 월세, alt 월세), 가족과 거주를 적용했는지). 값이 없으면 행을 뺀다."""
    rate = deps.config.compare.rent_conversion_rate
    if rate is None:
        return None, None, False
    base_stat, base_note = _rent(deps, base)
    alt_stat, alt_note = _rent(deps, alt)
    if base_stat is None or alt_stat is None:
        return None, None, False
    values, texts, applied = [], [], False
    for posting, stat in ((base, base_stat), (alt, alt_stat)):
        if family_housing and posting.is_busan:  # 가족과 살면 부산 쪽 주거비 0. 저장하지 않는다
            values.append(0)
            texts.append(f"0만 원 ({FAMILY_HOUSING})")
            applied = True
        else:
            values.append(stat.value)
            texts.append(f"약 {stat.value:,}만 원 ({stat.label})")
    notes = [n for n in (base_note, alt_note) if n]
    cfg = deps.config.compare
    row = CompareRow(
        key=CompareKey.HOUSING, label=LABEL[CompareKey.HOUSING], base=texts[0], alt=texts[1], comparable=True,
        source=_joined(base_stat.source, alt_stat.source), as_of=_joined(base_stat.as_of, alt_stat.as_of),
        assumption=RENT_ASSUMPTION.format(area=cfg.rent_max_area_m2, months=cfg.rent_months, rate=rate),
        note=" · ".join(notes) or None,
    )
    return row, (values[0], values[1]), applied


# ---------------------------------------------------------------- 통근
def _commute_stat(deps: Deps, posting: PostingLatest) -> CommuteStat | None:
    commute = deps.region_stats.commute
    for code in (posting.work_region.sigungu, posting.work_region.sido):
        stat = commute.get(code) if code else None
        if _has_source(stat):
            return stat
    return None


def _percent(value: float) -> str:
    return f"{value:.0f}%" if value == int(value) else f"{value:.1f}%"


def _commute_row(deps: Deps, base: PostingLatest, alt: PostingLatest) -> CompareRow | None:
    b, a = _commute_stat(deps, base), _commute_stat(deps, alt)
    if b is None or a is None:
        return None
    return CompareRow(key=CompareKey.COMMUTE, label=LABEL[CompareKey.COMMUTE],
                      base=f"{_percent(b.value)} ({b.label})", alt=f"{_percent(a.value)} ({a.label})",
                      is_regional_average=True, source=_joined(b.source, a.source), as_of=_joined(b.as_of, a.as_of))


# ---------------------------------------------------------------- 지역 정책
def _policy_row(deps: Deps, ctx, base_sido: str, alt_sido: str) -> CompareRow | None:
    data_as_of = deps.catalog.data_as_of()
    if data_as_of is None:  # 기준일이 없으면 뺀다
        return None
    # 서울·부산을 같은 함수로 계산한다 (T-06)
    counts = [policies.count_regional_policies(deps, ctx.profile, ctx.prefs, sido, as_of=ctx.as_of)
              for sido in (base_sido, alt_sido)]
    values = [c.to_api() for c in counts]
    for value in values:
        value.pop("nationalCommon", None)
        value["unit"] = str(MoneyUnit.MANWON)
    common = counts[0].national_common
    return CompareRow(key=CompareKey.REGIONAL_POLICY, label=LABEL[CompareKey.REGIONAL_POLICY], base=values[0],
                      alt=values[1], source=POLICY_SOURCE, as_of=clock.day(data_as_of), national_common=common,
                      note=copy_rules.NATIONAL_COMMON_NOTE.format(count=common))


# ---------------------------------------------------------------- 지역인재·인증
def _talent(config, posting: PostingLatest, profile: BasicProfile) -> str:
    """공고문의 지역 조건을 학교 소재지·거주지로 본 결과. 상세 화면과 같은 규칙(`facts.regional_talent_view`)이다.
    확정하지 않고 '대상일 수 있음'까지만 쓴다."""
    status = facts.regional_talent_view(config, profile, posting).status
    if status == RegionalTalentStatus.LIKELY:
        return TALENT_MAYBE
    if status == RegionalTalentStatus.CHECK_NEEDED:
        return TALENT_CHECK if profile.university_region is None else TALENT_NOTICE
    return TALENT_NONE


def _verified(posting: PostingLatest) -> str:
    labels = [b.label for b in posting.badges
              if b.type in (BadgeType.CHEONGKKEUL, BadgeType.GANGSO) and b.source and b.as_of]
    return ", ".join(labels) or NO_BADGE


# ---------------------------------------------------------------- 공개 함수
def compare_postings(deps: Deps, user_id: str, base_job_posting_id: str, alt_job_posting_id: str, *,
                     family_housing: bool = False,
                     as_of: str | date | datetime | None = None) -> CompareResponse:
    """급여, 주거비, 통근, 지역 정책, 지역인재, 인증을 나란히 둔다.

    급여는 두 공고 모두 적혀 있을 때만 비교한다 (T-05). 출처·기준일이 없는 행은 뺀다.
    rentConversionRate가 null이면 주거비 행을 숨긴다. 지역 정책은 `count_regional_policies`로 양쪽을 계산한다.
    """
    base = deps.catalog.get_latest(base_job_posting_id)
    if base is None:
        raise posting_not_found(base_job_posting_id)
    alt = deps.catalog.get_latest(alt_job_posting_id)
    if alt is None:
        raise posting_not_found(alt_job_posting_id)
    ctx = load_context(deps, user_id, as_of)

    salary = _salary_row(base, alt)
    rows: list[CompareRow] = [salary]
    rents, family_applied = None, False
    base_sido, alt_sido = _known_sido(base), _known_sido(alt)
    if base_sido and alt_sido:  # 근무지를 모르면 지역 행(주거비·통근·지역 정책)을 뺀다
        housing, rents, family_applied = _housing(deps, base, alt, family_housing)
        rows += [r for r in (housing, _commute_row(deps, base, alt),
                             _policy_row(deps, ctx, base_sido, alt_sido)) if r is not None]
    rows.append(CompareRow(key=CompareKey.REGIONAL_TALENT, label=LABEL[CompareKey.REGIONAL_TALENT],
                           base=_talent(deps.config, base, ctx.profile), alt=_talent(deps.config, alt, ctx.profile)))
    rows.append(CompareRow(key=CompareKey.VERIFIED, label=LABEL[CompareKey.VERIFIED],
                           base=_verified(base), alt=_verified(alt)))

    if not salary.comparable:
        cost = CostAdjusted(available=False, reason="SALARY_NOT_COMPARABLE")
    elif rents is None:
        cost = CostAdjusted(available=False, reason="HOUSING_UNAVAILABLE")
    else:
        cost = CostAdjusted(available=True, base=_monthly_pay(base) - rents[0], alt=_monthly_pay(alt) - rents[1],
                            unit=str(MoneyUnit.MANWON_MONTH))

    return CompareResponse(
        base=_side(base), alt=_side(alt), rows=rows, cost_adjusted=cost,
        family_housing_applied=family_applied,
        suggest_more=ctx.prefs.leave_reason != LeaveReason.WANT_SEOUL_LIFE,  # T-22
        data_as_of=deps.catalog.data_as_of(),
    )
