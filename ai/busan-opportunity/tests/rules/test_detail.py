"""공고 상세 (B-04)와 지역인재. T-08, T-21."""

from pathlib import Path

import pytest

from opportunity.core import copy_rules, policies, posting_detail
from opportunity.ingest.local_data import load_local_life, parse_festivals
from opportunity.models import EligibilityStatus, OppError, PolicyBrief, RegionalTalentStatus
from opportunity.seeds import demo_world as w


@pytest.fixture(autouse=True)
def related_calls(monkeypatch):
    """`related_policies`는 core-policy 워크트리 몫이라 여기서는 대신한다."""
    calls = []

    def fake(deps, profile, prefs, posting, *, as_of, limit=3):
        calls.append(posting.job_posting_id)
        if not posting.is_busan:
            return []
        return [PolicyBrief(policy_id=w.P_JOY_DOUBLE, title="부산청년 기쁨두배통장", bucket="AFTER_EMPLOYMENT",
                            status="AFTER_EMPLOYMENT")]

    monkeypatch.setattr(policies, "related_policies", fake)
    return calls


def detail(deps, as_of, pid, user="demo1"):
    return posting_detail.get_posting(deps, user, pid, as_of=as_of)


def test_t08_detail_drops_badge_without_source(deps, as_of):
    response = detail(deps, as_of, w.BUSAN_BADGE_NO_SOURCE, "demo2")
    assert response.badges == [] and response.posting.badges == []
    kept = detail(deps, as_of, w.BUSAN_DATA)
    assert [b.label for b in kept.badges] == ["청끌기업 · 급여"]
    assert all(b.source and b.as_of for b in kept.posting.badges)


def test_t21_closed_posting_is_not_an_error(deps, as_of):
    for pid in (w.BUSAN_DATA_EXPIRED, w.BUSAN_DATA_JUST_CLOSED):
        response = detail(deps, as_of, pid)
        assert response.closed is True and "마감" in response.facts
    assert detail(deps, as_of, w.BUSAN_DATA).closed is False


def test_t21_preview_drops_closed_and_caps_at_mini_card(deps, as_of):
    response = detail(deps, as_of, w.SEOUL_DATA)
    preview = response.alternatives_preview
    assert response.is_capital_area and not response.is_busan
    assert 0 < len(preview) <= deps.config.alternatives.mini_card_max
    got = {a.job_posting_id for a in preview}
    assert w.BUSAN_DATA_JUST_CLOSED not in got and w.BUSAN_DATA_EXPIRED not in got
    assert all(deps.catalog.get_latest(pid).is_busan for pid in got)
    assert detail(deps, as_of, w.BUSAN_DATA).alternatives_preview == []


def test_ineligible_posting_is_shown_with_reasons(deps, as_of):
    response = detail(deps, as_of, w.BUSAN_DATA, "demo2")  # 전문대 졸업, 공고는 학사 이상
    assert response.eligibility.status == EligibilityStatus.INELIGIBLE
    assert any(c.result == "NOT_MET" and c.reason for c in response.eligibility.conditions)
    assert response.posting.job_posting_id == w.BUSAN_DATA


def test_detail_fields(deps, as_of, related_calls):
    response = detail(deps, as_of, w.BUSAN_DATA)
    assert response.posting.requirements and response.is_busan and not response.is_capital_area
    assert response.match_level is not None and response.is_sample
    assert response.facts == ["희망 직무와 같은 직종", "필수 조건 2개 중 2개 충족", "마감 D-14"]
    assert [p.policy_id for p in response.related_policies] == [w.P_JOY_DOUBLE]
    assert related_calls == [w.BUSAN_DATA]
    assert response.data_as_of == w.DATA_AS_OF
    assert response.regional_talent is None  # 민간 공고


def test_not_found(deps, as_of):
    with pytest.raises(OppError) as e:
        detail(deps, as_of, "wk24-NOPE")
    assert e.value.code == "POSTING_NOT_FOUND" and e.value.status == 404
    with pytest.raises(OppError):
        posting_detail.get_regional_talent(deps, "demo3", "wk24-NOPE", as_of=as_of)


def test_unknown_region_detail_is_not_busan(deps, as_of):
    response = detail(deps, as_of, w.DATA_UNKNOWN_REGION)
    assert not response.is_busan and not response.is_capital_area and response.alternatives_preview == []


# ---------------------------------------------------------------- 지역인재
def test_regional_talent_likely_only_for_busan_school(deps, as_of):
    likely = posting_detail.get_regional_talent(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, as_of=as_of)
    assert likely.regional_talent.status == RegionalTalentStatus.LIKELY
    assert likely.regional_talent.message == "부산 소재 학교 졸업 예정이라 지역인재 전형 대상일 수 있어요 · 공고문 확인"
    # 학교가 부산이 아니면 맞지 않는다(화면에 띄우지 않음). 학교 지역을 모르면 확인 필요로 둔다
    for school, status in (("11", RegionalTalentStatus.NOT_APPLICABLE), (None, RegionalTalentStatus.CHECK_NEEDED)):
        profile = deps.users.get_basic_profile("demo3").model_copy(update={"university_region": school})
        deps.users.profiles["demo3"] = profile
        view = posting_detail.get_regional_talent(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, as_of=as_of).regional_talent
        assert view.status == status
        assert "대상일 수 있어요" not in (view.message or "")


def test_regional_talent_check_needed_and_not_applicable(deps, as_of):
    check = posting_detail.get_regional_talent(deps, "demo3", w.BUSAN_ADMIN_PUBLIC, as_of=as_of).regional_talent
    assert check.status == RegionalTalentStatus.CHECK_NEEDED and check.message == copy_rules.REGIONAL_TALENT_CHECK
    private = posting_detail.get_regional_talent(deps, "demo3", w.BUSAN_DATA, as_of=as_of)
    assert private.regional_talent.status == RegionalTalentStatus.NOT_APPLICABLE
    assert private.organization == "(주)가상데이터"


def test_regional_talent_message_has_no_forbidden_copy(deps, as_of):
    for pid in (w.BUSAN_DATA_PUBLIC, w.BUSAN_FINANCE_PUBLIC, w.BUSAN_ADMIN_PUBLIC):
        view = detail(deps, as_of, pid, "demo3").regional_talent
        assert view is not None and not copy_rules.find_forbidden(view.message or "")


# ---------------------------------------------------------------- 이 동네에서 일하면
LOCAL_FIXTURES = Path(__file__).parents[1] / "unit" / "ingest" / "fixtures"


def _with_local_life(deps):
    deps.local_life = load_local_life({
        "festivals": [f.to_api() for f in parse_festivals((LOCAL_FIXTURES / "local_festival_p01.json").read_bytes(),
                                                          as_of="2026-11-20")],
        "transit": [{"label": "부산 도시철도", "value": "4개 노선", "source": "부산교통공사 도시철도노선정보",
                     "asOf": "2021-04-14"}],
    })
    return deps


def test_local_life_only_on_busan_detail(deps, as_of):
    _with_local_life(deps)
    busan = detail(deps, as_of, w.BUSAN_DATA)  # 해운대구
    assert busan.local_life is not None
    assert len(busan.local_life.festivals) <= deps.config.local_life.festival_max
    assert busan.local_life.festivals[0].gugun == "해운대구"
    assert busan.local_life.transit[0].label == "부산 도시철도"
    assert "localLife" in busan.to_api()
    for pid in (w.SEOUL_DATA, w.DATA_UNKNOWN_REGION):
        other = detail(deps, as_of, pid)
        assert other.local_life is None and "localLife" not in other.to_api()


def test_local_life_does_not_change_other_detail_fields(deps, as_of):
    before = detail(deps, as_of, w.SEOUL_DATA).to_api()
    after = detail(_with_local_life(deps), as_of, w.SEOUL_DATA).to_api()
    assert before == after


def test_regional_talent_message_uses_school_name(deps, as_of):
    profile = deps.users.get_basic_profile("demo3").model_copy(update={"school_name": "가상대학교"})
    deps.users.profiles["demo3"] = profile
    view = posting_detail.get_regional_talent(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, as_of=as_of).regional_talent
    assert view.status == RegionalTalentStatus.LIKELY
    assert view.message == "가상대학교(부산) 졸업 예정이라 지역인재 전형 대상일 수 있어요 · 공고문 확인"
    assert not copy_rules.find_forbidden(view.message)
