"""나란히 비교 규칙 (B-06). T-05, T-06, T-22와 주거비·통근·인증 행."""

import pytest

from opportunity.core import compare, policies
from opportunity.core.copy_rules import NOT_IN_POSTING, find_forbidden
from opportunity.models import CompareKey, LeaveReason, OppError
from opportunity.models.region import CommuteStat
from opportunity.seeds import demo_world as w


def rows(result):
    return {row.key: row for row in result.rows}


def with_rent_rate(deps, rate=0.05):
    cfg = deps.config
    deps.config = cfg.model_copy(update={"compare": cfg.compare.model_copy(update={"rent_conversion_rate": rate})})
    return deps


# ---------------------------------------------------------------- T-05 급여
def test_t05_salary_only_one_side_not_compared(deps, as_of):
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA_PUBLIC, as_of=as_of)
    salary = rows(result)[CompareKey.SALARY]
    assert salary.comparable is False
    assert salary.base == "연 4,000~4,400만 원"
    assert salary.alt == NOT_IN_POSTING
    assert result.cost_adjusted.available is False
    assert result.cost_adjusted.reason == "SALARY_NOT_COMPARABLE"


def test_salary_both_sides_shown_as_is(deps, as_of):
    # 서울이 높은 칸도 그대로 보이고 승패 표시가 없다
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    salary = rows(result)[CompareKey.SALARY]
    assert salary.comparable is True
    assert (salary.base, salary.alt) == ("연 4,000~4,400만 원", "연 3,400~3,800만 원")
    for row in result.rows:
        dumped = row.to_api()
        assert not {"winner", "better", "highlight"} & set(dumped)


def test_row_order_and_labels(deps, as_of):
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    assert [r.key for r in result.rows] == [CompareKey.SALARY, CompareKey.COMMUTE, CompareKey.REGIONAL_POLICY,
                                            CompareKey.REGIONAL_TALENT, CompareKey.VERIFIED]
    assert result.base.label == "서울 강남구 · (주)가상테크"
    assert result.alt.job_posting_id == w.BUSAN_DATA
    assert result.data_as_of == w.DATA_AS_OF


# ---------------------------------------------------------------- 주거비
def test_housing_hidden_when_rent_conversion_rate_null(deps, as_of):
    assert deps.config.compare.rent_conversion_rate is None
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    assert CompareKey.HOUSING not in rows(result)
    assert result.cost_adjusted.available is False
    assert result.cost_adjusted.reason == "HOUSING_UNAVAILABLE"


def test_housing_row_with_rate_and_small_sample_fallback(deps, as_of):
    with_rent_rate(deps)
    # 남구 표본(12)이 minSample(30)보다 적어 부산 전체 값으로 바뀐다
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA_PUBLIC, as_of=as_of)
    housing = rows(result)[CompareKey.HOUSING]
    assert housing.base == "약 95만 원 (서울 강남구)"
    assert housing.alt == "약 44만 원 (부산)"
    assert "부산 남구" in housing.note and "부산" in housing.note
    assert housing.source and housing.as_of and housing.assumption
    assert "33㎡" in housing.assumption


def test_cost_adjusted_and_family_housing(deps, as_of):
    with_rent_rate(deps)
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    cost = result.cost_adjusted
    # 세전 월 급여 = 하한 ÷ 12 (반올림): 4000/12 → 333, 3400/12 → 283. 해운대구 표본은 충분하다
    assert cost.available and (cost.base, cost.alt) == (333 - 95, 283 - 52)
    assert cost.unit == "MANWON_MONTH"
    assert result.family_housing_applied is False

    family = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, family_housing=True, as_of=as_of)
    housing = rows(family)[CompareKey.HOUSING]
    assert housing.alt.startswith("0만 원") and housing.base == "약 95만 원 (서울 강남구)"
    assert family.family_housing_applied is True
    assert (family.cost_adjusted.base, family.cost_adjusted.alt) == (333 - 95, 283)
    assert "demo1" not in deps.users.prefs  # 토글은 저장하지 않는다


def test_housing_hidden_when_stats_missing(deps, as_of):
    with_rent_rate(deps)
    deps.region_stats = deps.region_stats.model_copy(update={"rent": {
        k: v for k, v in deps.region_stats.rent.items() if not k.startswith("26")}})
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    assert CompareKey.HOUSING not in rows(result)


# ---------------------------------------------------------------- 통근
def test_commute_regional_average(deps, as_of):
    commute = rows(compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of))[CompareKey.COMMUTE]
    assert commute.is_regional_average is True
    assert commute.base == "32% (서울)" and commute.alt == "48% (부산)"
    assert commute.source and commute.as_of


def test_stat_without_source_dropped(deps, as_of):
    commute = dict(deps.region_stats.commute)
    commute["26"] = CommuteStat(region_code="26", label="부산", value=48.0, source="", as_of="2025")
    deps.region_stats = deps.region_stats.model_copy(update={"commute": commute})
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    assert CompareKey.COMMUTE not in rows(result)


# ---------------------------------------------------------------- T-06 지역 정책
def test_t06_regional_policy_same_function_both_sides(deps, as_of, monkeypatch):
    calls = []
    original = policies.count_regional_policies

    def spy(deps_, profile, prefs, sido, *, as_of):
        calls.append(sido)
        return original(deps_, profile, prefs, sido, as_of=as_of)

    monkeypatch.setattr(policies, "count_regional_policies", spy)
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA_PUBLIC, as_of=as_of)
    assert calls == ["11", "26"]
    row = rows(result)[CompareKey.REGIONAL_POLICY]
    assert row.base["policyIds"] == [w.P_SEOUL_ALLOWANCE]
    assert row.alt["policyIds"] == [w.P_BUSAN_INTERVIEW]
    assert not any(pid.startswith("seed-") for pid in row.base["policyIds"] + row.alt["policyIds"])
    assert row.base["count"] == 1 and row.alt["count"] == 1
    assert row.national_common == 1
    assert row.note == "전국 공통 정책 1개는 어디서든 같아요"
    assert row.source == "온통청년" and row.as_of == "2026-11-21"


# ---------------------------------------------------------------- 근무지 미상
def test_unknown_region_drops_regional_rows(deps, as_of):
    with_rent_rate(deps)
    result = compare.compare_postings(deps, "demo1", w.DATA_UNKNOWN_REGION, w.BUSAN_DATA, as_of=as_of)
    keys = set(rows(result))
    assert not keys & {CompareKey.HOUSING, CompareKey.COMMUTE, CompareKey.REGIONAL_POLICY}
    assert {CompareKey.SALARY, CompareKey.REGIONAL_TALENT, CompareKey.VERIFIED} <= keys
    assert result.base.label.startswith("근무지 확인 필요")


# ---------------------------------------------------------------- 지역인재·인증
def test_regional_talent_and_verified(deps, as_of):
    result = rows(compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA_PUBLIC, as_of=as_of))
    assert (result[CompareKey.REGIONAL_TALENT].base, result[CompareKey.REGIONAL_TALENT].alt) == ("해당 없음",
                                                                                                 "대상일 수 있음")
    assert (result[CompareKey.VERIFIED].base, result[CompareKey.VERIFIED].alt) == ("-", "-")
    other = rows(compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_ACCOUNT_GANGSO, as_of=as_of))
    assert other[CompareKey.VERIFIED].alt == "청년일자리강소기업"
    assert other[CompareKey.REGIONAL_TALENT].alt == "해당 없음"


def test_verified_skips_badge_without_source(deps, as_of):
    result = rows(compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_BADGE_NO_SOURCE, as_of=as_of))
    assert result[CompareKey.VERIFIED].alt == "-"


# ---------------------------------------------------------------- T-22, 오류, 문구
def test_t22_want_seoul_life_no_suggest_more(deps, as_of):
    assert compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of).suggest_more is True
    deps.users.put_prefs("demo1", deps.users.get_prefs("demo1").model_copy(
        update={"leave_reason": LeaveReason.WANT_SEOUL_LIFE}))
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA, as_of=as_of)
    assert result.suggest_more is False
    assert rows(result)[CompareKey.SALARY].base == "연 4,000~4,400만 원"  # 값은 그대로 보여 준다


def test_missing_posting_not_found(deps, as_of):
    for base, alt in (("wk24-NOPE", w.BUSAN_DATA), (w.SEOUL_DATA, "alio-NOPE")):
        with pytest.raises(OppError) as e:
            compare.compare_postings(deps, "demo1", base, alt, as_of=as_of)
        assert e.value.code == "POSTING_NOT_FOUND"


def test_no_forbidden_copy(deps, as_of):
    with_rent_rate(deps)
    result = compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA_PUBLIC, family_housing=True,
                                      as_of=as_of)
    text = str(result.to_api())
    assert not find_forbidden(text)
