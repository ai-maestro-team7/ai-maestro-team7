"""정책 지갑 규칙 (B-08). T-06, T-07, T-12, T-13, T-14와 칸 나누기, 합계."""

import pytest

from opportunity.core import clock, policies
from opportunity.core.copy_rules import find_forbidden
from opportunity.models import (
    EmploymentStatus,
    OppError,
    PeriodType,
    PolicyAlert,
    PolicyBucket,
    PolicyEligibilityStatus,
    PolicySource,
    PolicyStage,
)
from opportunity.models.policy import PolicyEligibility
from opportunity.seeds import demo_world as w

S = PolicyEligibilityStatus


def judge(deps, policy_id, user_id="demo1", *, profile=None, prefs=None, as_of=w.DEMO_AS_OF, **kwargs):
    policy = deps.catalog.get_policy(policy_id)
    profile = profile or deps.users.get_basic_profile(user_id)
    prefs = prefs or deps.users.get_prefs(user_id)
    return policies.judge_policy(policy, profile, prefs, as_of=clock.parse_as_of(as_of), **kwargs)


def all_cards(wallet):
    return [card for cards in wallet.buckets.values() for card in cards]


def bucket_of(wallet, policy_id):
    return next(card.bucket for card in all_cards(wallet) if card.policy_id == policy_id)


def put_policy(deps, policy_id, **update):
    deps.catalog.put_policy(deps.catalog.get_policy(policy_id).model_copy(update=update))


# ---------------------------------------------------------------- T-07
def test_t07_unverified_policy_not_in_wallet(deps, as_of):
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    ids = {card.policy_id for card in all_cards(wallet)}
    assert w.P_UNVERIFIED not in ids
    assert w.P_DIDIMDOL in ids
    assert wallet.totals.selective_max < 999  # 검수 전 정책 금액(999)이 합계에 없다


def test_t07_unverified_policy_detail_not_found(deps, as_of):
    with pytest.raises(OppError) as e:
        policies.get_policy(deps, "demo1", w.P_UNVERIFIED, as_of=as_of)
    assert e.value.code == "POLICY_NOT_FOUND"
    with pytest.raises(OppError) as e:
        policies.get_policy(deps, "demo1", "ythc-NOPE", as_of=as_of)
    assert e.value.code == "POLICY_NOT_FOUND"


def test_t07_unverified_not_counted_in_regional(deps, as_of):
    put_policy(deps, w.P_BUSAN_INTERVIEW, verified=False)
    count = policies.count_regional_policies(deps, deps.users.get_basic_profile("demo1"), deps.users.get_prefs("demo1"),
                                             "26", as_of=clock.parse_as_of(as_of))
    assert w.P_BUSAN_INTERVIEW not in count.policy_ids


# ---------------------------------------------------------------- T-12 나이
def test_t12_demo1_age_boundary_check_needed(deps, as_of):
    # demo1은 2003년생이라 2026년에 만 22~23세. 23~34세 정책은 생일에 따라 갈린다
    result = judge(deps, w.P_BUSAN_TRANSIT)
    assert result.status == S.CHECK_NEEDED
    assert any("나이" in r for r in result.reasons)
    detail = policies.get_policy(deps, "demo1", w.P_BUSAN_TRANSIT, as_of=as_of)
    assert detail.policy.eligibility.status == S.CHECK_NEEDED


def test_t12_age_both_inside_or_outside(deps):
    profile = deps.users.get_basic_profile("demo1")
    assert judge(deps, w.P_BUSAN_INTERVIEW).status == S.ELIGIBLE  # 19~34세
    old = profile.model_copy(update={"birth_year": 1980})
    result = judge(deps, w.P_BUSAN_INTERVIEW, profile=old)
    assert result.status == S.NOT_ELIGIBLE
    no_birth = profile.model_copy(update={"birth_year": None})
    assert judge(deps, w.P_BUSAN_INTERVIEW, profile=no_birth).status == S.CHECK_NEEDED


def test_profile_used_age_is_range(deps, as_of):
    used = policies.match_policies(deps, "demo1", as_of=as_of).profile_used
    assert used.age_range == "22~23"
    assert used.residence == "부산 남구"
    assert used.employment == "UNEMPLOYED"
    assert used.income == "UNKNOWN"


# ---------------------------------------------------------------- T-13 소득
def test_t13_income_rule_without_income_check_needed(deps):
    result = judge(deps, w.P_BUSAN_RENT)
    assert result.status == S.CHECK_NEEDED
    assert any("소득" in r for r in result.reasons)


def test_t13_income_entered_is_judged(deps):
    profile = deps.users.get_basic_profile("demo1")
    assert judge(deps, w.P_BUSAN_RENT, profile=profile.model_copy(update={"household_income_level": 50})).status \
        == S.ELIGIBLE
    assert judge(deps, w.P_BUSAN_RENT, profile=profile.model_copy(update={"household_income_level": 80})).status \
        == S.NOT_ELIGIBLE
    # 원문으로만 적힌 소득 기준은 입력이 있어도 잴 수 없다
    assert judge(deps, w.P_STAY_LOAN, profile=profile.model_copy(update={"monthly_income": 100})).status \
        == S.CHECK_NEEDED


# ---------------------------------------------------------------- T-14 중복 불가
def test_t14_exclusive_with_receiving_policy_by_name(deps):
    prefs = deps.users.get_prefs("demo1").model_copy(update={"receiving_policies": ["청년내일저축계좌"]})
    result = judge(deps, w.P_JOY_DOUBLE, prefs=prefs)
    assert result.status == S.NOT_ELIGIBLE  # AFTER_EMPLOYMENT보다 강하다
    assert any("중복 불가" in r and "청년내일저축계좌" in r for r in result.reasons)


def test_t14_exclusive_with_receiving_policy_by_id(deps, as_of):
    put_policy(deps, w.P_BUSAN_INTERVIEW, exclusive_with=[w.P_NATIONAL_JOB])
    deps.users.put_prefs("demo1", deps.users.get_prefs("demo1").model_copy(
        update={"receiving_policies": [w.P_NATIONAL_JOB]}))
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    card = next(c for c in all_cards(wallet) if c.policy_id == w.P_BUSAN_INTERVIEW)
    assert card.eligibility.status == S.NOT_ELIGIBLE
    assert card.bucket == PolicyBucket.CLOSED
    assert card.exclusive_with == [w.P_NATIONAL_JOB]


# ---------------------------------------------------------------- 거주
def test_sigungu_policy_not_for_other_gu(deps):
    # 남구 정책: 남구에 사는 demo1은 충족, 사하구에 사는 demo2는 안 맞는다
    assert judge(deps, w.P_BUSAN_NAMGU, "demo1").status == S.ELIGIBLE
    other = judge(deps, w.P_BUSAN_NAMGU, "demo2")
    assert other.status == S.NOT_ELIGIBLE
    assert any("거주" in r for r in other.reasons)


def test_assumed_sido_makes_gu_policy_check_needed(deps):
    assert judge(deps, w.P_BUSAN_NAMGU, "demo2", assumed_sido="26").status == S.CHECK_NEEDED
    assert judge(deps, w.P_SEOUL_ALLOWANCE, "demo1", assumed_sido="11").status == S.ELIGIBLE
    assert judge(deps, w.P_SEOUL_ALLOWANCE, "demo1").status == S.NOT_ELIGIBLE
    result = judge(deps, w.P_BUSAN_INTERVIEW, "demo1")
    assert "부산 거주 충족" in result.reasons
    assert "전국 대상" in judge(deps, w.P_NATIONAL_JOB).reasons


# ---------------------------------------------------------------- 취업 상태
def test_employment_after_employment_and_not_eligible(deps):
    profile = deps.users.get_basic_profile("demo1")
    assert judge(deps, w.P_JOY_DOUBLE).status == S.AFTER_EMPLOYMENT
    student = profile.model_copy(update={"employment_status": EmploymentStatus.STUDENT})
    assert judge(deps, w.P_JOY_DOUBLE, profile=student).status == S.AFTER_EMPLOYMENT
    employed = profile.model_copy(update={"employment_status": EmploymentStatus.EMPLOYED})
    assert judge(deps, w.P_JOY_DOUBLE, profile=employed).status == S.ELIGIBLE
    result = judge(deps, w.P_DIDIMDOL, profile=employed)  # 미취업 대상 정책
    assert result.status == S.NOT_ELIGIBLE
    assert "취업 준비 청년 대상: 미취업 충족" in judge(deps, w.P_DIDIMDOL).reasons


def test_manual_checks_passed_through(deps):
    policy = deps.catalog.get_policy(w.P_BUSAN_INTERVIEW)
    put_policy(deps, w.P_BUSAN_INTERVIEW, eligibility=policy.eligibility.model_copy(
        update={"manual_checks": ["부산 소재 기업 면접 확인서"]}))
    result = judge(deps, w.P_BUSAN_INTERVIEW)
    assert result.manual_checks == ["부산 소재 기업 면접 확인서"]
    assert result.status == S.ELIGIBLE  # 자유 서술 조건은 판정에 쓰지 않는다


# ---------------------------------------------------------------- 칸 나누기
def test_buckets(deps, as_of):
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    assert set(wallet.buckets) == set(PolicyBucket)
    assert bucket_of(wallet, w.P_BUSAN_INTERVIEW) == PolicyBucket.OPEN_NOW     # 상시
    assert bucket_of(wallet, w.P_DIDIMDOL) == PolicyBucket.NEXT_CYCLE          # 지났고 작년 일정 있음
    assert bucket_of(wallet, w.P_JOY_DOUBLE) == PolicyBucket.AFTER_EMPLOYMENT
    assert bucket_of(wallet, w.P_MOVING) == PolicyBucket.SETTLEMENT            # 정착 단계, 취업 전
    assert bucket_of(wallet, w.P_STAY_LOAN) == PolicyBucket.SETTLEMENT
    didimdol = next(c for c in all_cards(wallet) if c.policy_id == w.P_DIDIMDOL)
    assert didimdol.alert_available
    assert didimdol.application.expected
    assert didimdol.application.apply_start is None  # 지난 일정은 신청 기간으로 보이지 않는다
    interview = next(c for c in all_cards(wallet) if c.policy_id == w.P_BUSAN_INTERVIEW)
    assert not interview.alert_available


def test_buckets_by_period(deps, as_of):
    # 아직 안 열린 정책은 NEXT_CYCLE + 알림 가능, 다음 일정 없이 지난 정책은 CLOSED, 기간 안이면 OPEN_NOW
    put_policy(deps, w.P_BUSAN_INTERVIEW, apply_start="2026-12-01", apply_end="2026-12-20",
               application=deps.catalog.get_policy(w.P_BUSAN_INTERVIEW).application.model_copy(
                   update={"period_type": PeriodType.FIXED}))
    put_policy(deps, w.P_BUSAN_TRANSIT, apply_start="2026-10-01", apply_end="2026-10-31",
               application=deps.catalog.get_policy(w.P_BUSAN_TRANSIT).application.model_copy(
                   update={"period_type": PeriodType.FIXED}))
    deps.users.profiles["demo1"] = deps.users.get_basic_profile("demo1").model_copy(update={"birth_year": 2001})
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    upcoming = next(c for c in all_cards(wallet) if c.policy_id == w.P_BUSAN_INTERVIEW)
    assert upcoming.bucket == PolicyBucket.NEXT_CYCLE and upcoming.alert_available
    assert upcoming.application.apply_start == "2026-12-01"
    assert bucket_of(wallet, w.P_BUSAN_TRANSIT) == PolicyBucket.CLOSED
    # 서울에 사는 사용자에게 서울 청년 수당(11.02~11.27)은 지금 신청 가능
    deps.users.profiles["demo1"] = deps.users.get_basic_profile("demo1").model_copy(
        update={"residence_sido": "11", "residence_sigungu": "11680"})
    seoul = policies.match_policies(deps, "demo1", as_of=as_of)
    assert bucket_of(seoul, w.P_SEOUL_ALLOWANCE) == PolicyBucket.OPEN_NOW
    assert w.P_DIDIMDOL not in {c.policy_id for c in all_cards(seoul)}  # 부산 정책은 읽지 않는다


def test_stage_filter(deps, as_of):
    wallet = policies.match_policies(deps, "demo1", stage=PolicyStage.SETTLE, as_of=as_of)
    cards = all_cards(wallet)
    assert cards and all(c.stage == PolicyStage.SETTLE for c in cards)


def test_alert_subscribed(deps, as_of):
    deps.users.put_alert("demo1", PolicyAlert(policy_id=w.P_DIDIMDOL, scheduled_at=as_of, schedule_name="n"))
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    assert next(c for c in all_cards(wallet) if c.policy_id == w.P_DIDIMDOL).alert_subscribed
    assert not next(c for c in all_cards(wallet) if c.policy_id == w.P_INTERN).alert_subscribed


def test_detail_has_checklist(deps, as_of):
    detail = policies.get_policy(deps, "demo1", w.P_JOY_DOUBLE, as_of=as_of)
    assert detail.policy.checklist == ["주민등록초본", "신청서"]
    assert detail.policy.benefit.self_share_max == 360
    assert detail.data_as_of == w.DATA_AS_OF
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    assert all(c.checklist is None for c in all_cards(wallet))


# ---------------------------------------------------------------- 합계
def test_totals_split_and_only_eligible(deps, as_of):
    totals = policies.match_policies(deps, "demo1", as_of=as_of).totals
    # 자격만 맞으면: 면접 지원 10 + 남구 응시료 10 (AUTOMATIC)
    assert totals.guaranteed_if_eligible == 20
    # 선정되면 최대: 디딤돌카드+ 180 + 전국 구직활동 300. 교통비(나이 경계)·기쁨두배(취업 후)는 빠진다
    assert totals.selective_max == 480
    assert totals.unit == "MANWON" and totals.note


def test_self_savings_not_in_totals(deps, as_of):
    deps.users.profiles["demo1"] = deps.users.get_basic_profile("demo1").model_copy(
        update={"employment_status": EmploymentStatus.EMPLOYED})
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    joy = next(c for c in all_cards(wallet) if c.policy_id == w.P_JOY_DOUBLE)
    assert joy.eligibility.status == S.ELIGIBLE
    before = wallet.totals.selective_max
    # 본인 저축분을 바꿔도 합계는 그대로다
    policy = deps.catalog.get_policy(w.P_JOY_DOUBLE)
    put_policy(deps, w.P_JOY_DOUBLE, benefit=policy.benefit.model_copy(update={"self_share_max": 9999}))
    assert policies.match_policies(deps, "demo1", as_of=as_of).totals.selective_max == before
    # 시 지원분 360만 들어간다 (본인분 포함 720이 아니다)
    put_policy(deps, w.P_JOY_DOUBLE, benefit=policy.benefit.model_copy(update={"public_share_max": 0}))
    assert policies.match_policies(deps, "demo1", as_of=as_of).totals.selective_max == before - 360


# ---------------------------------------------------------------- T-06 지역 정책 수
def test_t06_regional_count_only_youthcenter(deps, as_of):
    profile, prefs = deps.users.get_basic_profile("demo1"), deps.users.get_prefs("demo1")
    at = clock.parse_as_of(as_of)
    busan = policies.count_regional_policies(deps, profile, prefs, "26", as_of=at)
    seoul = policies.count_regional_policies(deps, profile, prefs, "11", as_of=at)
    assert busan.sido == "26" and seoul.sido == "11"
    # 디딤돌카드+는 demo1에게 맞지만 직접 정리한 시드라 세지 않는다
    assert judge(deps, w.P_DIDIMDOL).status == S.ELIGIBLE
    assert all(deps.catalog.get_policy(pid).source == PolicySource.YOUTHCENTER for pid in busan.policy_ids)
    assert busan.policy_ids == [w.P_BUSAN_INTERVIEW]  # 월세(소득)·교통비(나이)·남구(구 가정)는 확인 필요라 빠진다
    assert seoul.policy_ids == [w.P_SEOUL_ALLOWANCE]
    assert busan.count == 1 and seoul.count == 1
    assert busan.national_common == seoul.national_common == 1  # 전국 구직활동 지원


def test_t06_busan_seed_never_counted(deps, as_of):
    # 부산 시드를 아무리 늘려도 지역 정책 수는 그대로다
    at = clock.parse_as_of(as_of)
    profile, prefs = deps.users.get_basic_profile("demo1"), deps.users.get_prefs("demo1")
    before = policies.count_regional_policies(deps, profile, prefs, "26", as_of=at).count
    base = deps.catalog.get_policy(w.P_BUSAN_INTERVIEW)
    deps.catalog.put_policy(base.model_copy(update={"policy_id": "seed-busan-extra", "source": PolicySource.BUSAN_SEED}))
    deps.catalog.put_policy(base.model_copy(update={"policy_id": "busan-city-extra",
                                                    "source": PolicySource.BUSAN_CITY}))
    assert policies.count_regional_policies(deps, profile, prefs, "26", as_of=at).count == before


# ---------------------------------------------------------------- 관련 정책 (상세 화면)
def test_related_policies_only_for_busan_posting(deps, as_of):
    profile, prefs = deps.users.get_basic_profile("demo1"), deps.users.get_prefs("demo1")
    at = clock.parse_as_of(as_of)
    busan = policies.related_policies(deps, profile, prefs, deps.catalog.get_latest(w.BUSAN_DATA), as_of=at, limit=5)
    ids = [b.policy_id for b in busan]
    assert w.P_JOY_DOUBLE in ids and w.P_MOVING in ids
    assert w.P_DIDIMDOL not in ids  # 취업 준비 단계 정책은 아니다
    assert w.P_UNVERIFIED not in ids
    joy = next(b for b in busan if b.policy_id == w.P_JOY_DOUBLE)
    assert joy.status == S.AFTER_EMPLOYMENT and joy.bucket == PolicyBucket.AFTER_EMPLOYMENT
    assert len(policies.related_policies(deps, profile, prefs, deps.catalog.get_latest(w.BUSAN_DATA),
                                         as_of=at, limit=2)) == 2
    for pid in (w.SEOUL_DATA, w.DATA_UNKNOWN_REGION):
        assert policies.related_policies(deps, profile, prefs, deps.catalog.get_latest(pid), as_of=at) == []


def test_related_policies_skip_age_mismatch(deps, as_of):
    old = deps.users.get_basic_profile("demo1").model_copy(update={"birth_year": 1980})
    briefs = policies.related_policies(deps, old, deps.users.get_prefs("demo1"),
                                       deps.catalog.get_latest(w.BUSAN_DATA), as_of=clock.parse_as_of(as_of), limit=10)
    assert briefs == []


# ---------------------------------------------------------------- 문구
def test_reasons_have_no_forbidden_copy(deps, as_of):
    for user in ("demo1", "demo2", "demo3"):
        for card in all_cards(policies.match_policies(deps, user, as_of=as_of)):
            for text in card.eligibility.reasons:
                assert not find_forbidden(text), text


def test_policy_eligibility_defaults_unrestricted(deps):
    # 조건이 하나도 없는 정책은 거주(전국)만 보고 충족
    policy = deps.catalog.get_policy(w.P_NATIONAL_JOB).model_copy(
        update={"eligibility": PolicyEligibility(), "age_min": None, "age_max": None})
    result = policies.judge_policy(policy, deps.users.get_basic_profile("demo1"), deps.users.get_prefs("demo1"),
                                   as_of=clock.parse_as_of(w.DEMO_AS_OF))
    assert result.status == S.ELIGIBLE and result.reasons == ["전국 대상"]
