"""페르소나 정책 지갑·비교 기대 결과 (개발계획서2 §7.1)."""

from opportunity.core import compare, policies
from opportunity.models import CompareKey, PolicyBucket, PolicyEligibilityStatus, PolicyStage
from opportunity.seeds import demo_world as w


def cards(wallet):
    return {card.policy_id: card for items in wallet.buckets.values() for card in items}


def test_persona1_joy_double_after_employment(deps, as_of):
    wallet = policies.match_policies(deps, "demo1", as_of=as_of)
    joy = cards(wallet)[w.P_JOY_DOUBLE]
    assert joy.bucket == PolicyBucket.AFTER_EMPLOYMENT
    assert joy.eligibility.status == PolicyEligibilityStatus.AFTER_EMPLOYMENT
    assert "부산 거주 충족" in joy.eligibility.reasons
    assert joy.alert_available  # 다음 모집(작년 8월 기준) 알림
    assert (joy.benefit.public_share_max, joy.benefit.self_share_max) == (360, 360)
    assert joy.application.last_competition == "13:1 (2025)"
    assert joy.exclusive_with == ["청년내일저축계좌"]
    assert wallet.profile_used.age_range == "22~23"


def test_persona1_compare_salary_as_posted(deps, as_of):
    salary = {r.key: r for r in compare.compare_postings(deps, "demo1", w.SEOUL_DATA, w.BUSAN_DATA,
                                                         as_of=as_of).rows}[CompareKey.SALARY]
    assert (salary.base, salary.alt) == ("연 4,000~4,400만 원", "연 3,400~3,800만 원")


def test_persona2_prepare_policies_visible(deps, as_of):
    wallet = policies.match_policies(deps, "demo2", as_of=as_of)
    prepare = [c for c in cards(wallet).values() if c.stage == PolicyStage.PREPARE
               and c.bucket in (PolicyBucket.OPEN_NOW, PolicyBucket.NEXT_CYCLE)]
    ids = {c.policy_id for c in prepare}
    assert {w.P_DIDIMDOL, w.P_INTERN} <= ids
    assert all(c.eligibility.status != PolicyEligibilityStatus.NOT_ELIGIBLE for c in prepare)
    assert w.P_UNVERIFIED not in cards(wallet)
    # 사하구에 살아 남구 정책은 접어 둔다
    assert cards(wallet)[w.P_BUSAN_NAMGU].bucket == PolicyBucket.CLOSED


def test_persona3_wallet_and_regional_talent(deps, as_of):
    wallet = policies.match_policies(deps, "demo3", as_of=as_of)
    assert wallet.profile_used.residence == "부산 금정구"
    assert cards(wallet)[w.P_BUSAN_TRANSIT].eligibility.status == PolicyEligibilityStatus.ELIGIBLE  # 만 24~25세
    talent = {r.key: r for r in compare.compare_postings(deps, "demo3", w.SEOUL_FINANCE_PUBLIC,
                                                         w.BUSAN_FINANCE_PUBLIC, as_of=as_of).rows}
    assert talent[CompareKey.REGIONAL_TALENT].alt == "대상일 수 있음"
    assert talent[CompareKey.REGIONAL_TALENT].base == "해당 없음"
