"""페르소나 ①②③ 피드·대안·상세 기대 결과 (개발계획서2 §7.1)."""

import pytest
from rules.test_ncs_match import ALIO_IT, ALIO_OFFICE, add_posting

from opportunity.core import alternatives, facts, policies, posting_detail, ranking
from opportunity.models import BadgeType, RegionalTalentStatus
from opportunity.seeds import demo_world as w


@pytest.fixture(autouse=True)
def no_related_policies(monkeypatch):
    """`related_policies`는 core-policy 워크트리 몫이라 빈 목록으로 대신한다."""
    monkeypatch.setattr(policies, "related_policies", lambda *args, **kwargs: [])


def test_persona1_top10_has_busan_postings(deps, as_of):
    top = ranking.search_postings(deps, "demo1", as_of=as_of).items[:10]
    assert any(card.is_busan for card in top)
    assert top[0].is_busan  # 기본 정렬은 부산 우선


def test_persona1_seoul_data_has_two_busan_alternatives(deps, as_of):
    response = alternatives.find_busan_alternatives(deps, "demo1", w.SEOUL_DATA, as_of=as_of)
    assert len(response.alternatives) >= 2
    for alt in response.alternatives:
        assert deps.catalog.get_latest(alt.job_posting_id).is_busan
        assert alt.similarity >= deps.config.alternatives.min_similarity
    feed = {c.job_posting_id: c for c in ranking.search_postings(deps, "demo1", as_of=as_of).items}
    assert feed[w.SEOUL_DATA].busan_alternatives_count >= 2


def test_persona2_sees_cheonggeul_and_gangso_badges(deps, as_of):
    cards = ranking.search_postings(deps, "demo2", as_of=as_of).items
    types = {b.type for card in cards for b in card.badges}
    assert BadgeType.CHEONGKKEUL in types and BadgeType.GANGSO in types
    top = cards[:5]
    assert any(b.type in (BadgeType.CHEONGKKEUL, BadgeType.GANGSO) for card in top for b in card.badges)


def test_persona3_relocated_posting_is_regional_talent_likely(deps, as_of):
    response = posting_detail.get_posting(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, as_of=as_of)
    talent = response.regional_talent
    assert talent.status == RegionalTalentStatus.LIKELY
    assert "대상일 수 있어요" in talent.message and "공고문 확인" in talent.message
    assert "합격에 유리" not in talent.message
    feed = [c.job_posting_id for c in ranking.search_postings(deps, "demo3", as_of=as_of).items]
    assert w.BUSAN_FINANCE_PUBLIC in feed[:3]


# ---------------------------------------------------------------- 실제 잡알리오 공고 모양 (NCS 코드만 있음)
@pytest.mark.parametrize("user,job,description", [
    ("demo1", ALIO_IT, "데이터 분석과 통계로 정보시스템 데이터를 다룬다"),     # 20010105 ↔ R600020
    ("demo2", ALIO_OFFICE, "회계 전표 처리와 경영 지원 사무"),                 # 02030201 ↔ R600002
])
def test_persona_alio_posting_gets_ncs_job_match(deps, as_of, user, job, description):
    """고용24 직종 코드가 없는 공공기관 공고도 NCS 대분류로 직무 일치를 잰다. "같은 직종"이라고 하지 않는다."""
    add_posting(deps, "alio-T-PERSONA", region=w.NAMGU, job=job, description=description)
    card = next(c for c in ranking.search_postings(deps, user, as_of=as_of, limit=100).items
                if c.job_posting_id == "alio-T-PERSONA")
    assert facts.FACT_JOB_NCS_MAJOR in card.facts
    assert facts.FACT_JOB_EXACT not in card.facts and facts.FACT_JOB_MAJOR not in card.facts
    no_ncs = deps.catalog.get_latest("alio-T-PERSONA").model_copy(
        update={"job": job.model_copy(update={"ncs_codes": []})})
    profile = deps.users.get_basic_profile(user)
    breakdown = ranking.match_score(deps.config, profile, no_ncs)
    assert breakdown.job_match == 0  # NCS 경로가 없으면 이름만 비교해 0이다
    with_ncs = ranking.match_score(deps.config, profile, deps.catalog.get_latest("alio-T-PERSONA"))
    assert with_ncs.job_match == deps.config.match.job_match_levels.same_major_category_only


def test_persona3_without_ncs_code_is_unchanged(deps, as_of):
    """희망 직무에 NCS 코드가 없으면 NCS 경로는 끼지 않는다."""
    add_posting(deps, "alio-T-PERSONA3", region=w.NAMGU, job=ALIO_OFFICE)
    latest = deps.catalog.get_latest("alio-T-PERSONA3")
    breakdown = ranking.match_score(deps.config, deps.users.get_basic_profile("demo3"), latest)
    assert breakdown.job_basis != ranking.BASIS_NCS
