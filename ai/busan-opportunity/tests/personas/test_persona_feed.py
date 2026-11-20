"""페르소나 ①②③ 피드·대안·상세 기대 결과 (개발계획서2 §7.1)."""

import pytest

from opportunity.core import alternatives, policies, posting_detail, ranking
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
