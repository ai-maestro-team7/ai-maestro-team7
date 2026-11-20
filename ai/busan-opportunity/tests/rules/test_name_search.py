"""검색어·회사 이름 검색 (B-D08).

벡터 후보는 프로필과 비슷한 공고만 모은다. 그래서 프로필과 먼 회사의 공고는 거르기 전에 이미 빠져 있었다
(데이터 분석 희망자가 "삼성"을 찾으면 0건). 검색어나 회사 조건이 있으면 이름 색인에서 찾은 공고를 후보에 더한다.
"""

import pytest
from rules.test_ncs_match import add_posting
from rules.test_ranking import feed, ids

from opportunity.seeds import demo_world as w

PID = "wk24-NAME0001"
ORG = "(주)가상전자"


class HideFromVectors:
    """벡터 질의 결과에서 몇몇 공고를 뺀다. 그 공고가 프로필 후보 상위에 들지 못한 상황이다.
    similarities 호출은 기록하고 그대로 넘긴다."""

    def __init__(self, inner, hidden=()):
        self.inner, self.hidden, self.asked = inner, set(hidden), []

    def query(self, vector, *, top_k, filter=None):
        return [h for h in self.inner.query(vector, top_k=top_k, filter=filter) if h.key not in self.hidden]

    def similarities(self, vector, keys):
        self.asked += list(keys)
        return self.inner.similarities(vector, keys)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def add_company_posting(deps, *, closes="2026-12-06"):
    """회사 이름이 정해진 서울 공고 한 건. 내용은 demo1(데이터 분석)과 비슷하다."""
    latest = add_posting(deps, PID, region=w.GANGNAM, closes=closes)
    deps.catalog.put_latest(latest.model_copy(update={"organization": ORG}))


def test_keyword_finds_company_outside_vector_candidates(deps, as_of):
    add_company_posting(deps)
    deps.vectors = HideFromVectors(deps.vectors, {PID})
    assert PID not in ids(feed(deps, as_of))  # 검색어가 없으면 벡터 후보만 본다
    assert PID in ids(feed(deps, as_of, keyword="가상전자"))
    assert PID in deps.vectors.asked


def test_organization_condition_finds_company_outside_vector_candidates(deps, as_of):
    add_company_posting(deps)
    deps.vectors = HideFromVectors(deps.vectors, {PID})
    assert PID in ids(feed(deps, as_of, organization="가상 전자"))  # 공백은 무시한다
    assert PID not in ids(feed(deps, as_of, organization="없는회사"))


def test_name_candidate_scores_like_vector_candidate(deps, as_of):
    """이름으로 들어온 공고도 벡터로 들어왔을 때와 적합도가 같다 (유사도를 같은 식으로 계산한다)."""
    add_company_posting(deps)
    spy = HideFromVectors(deps.vectors)
    deps.vectors = spy
    by_vector = {c.job_posting_id: c for c in feed(deps, as_of, keyword="가상전자").items}
    assert PID in by_vector and PID not in spy.asked  # 벡터 후보에 이미 있으면 다시 계산하지 않는다
    deps.vectors = HideFromVectors(spy.inner, {PID})
    by_name = {c.job_posting_id: c for c in feed(deps, as_of, keyword="가상전자").items}
    assert by_name[PID].match_score == pytest.approx(by_vector[PID].match_score)


def test_closed_posting_is_not_found_by_name(deps, as_of):
    add_company_posting(deps, closes="2026-11-01")
    deps.vectors = HideFromVectors(deps.vectors, {PID})
    assert PID not in ids(feed(deps, as_of, keyword="가상전자"))


def test_posting_without_vector_is_still_found(deps, as_of):
    """보강 전이라 벡터가 없는 공고도 이름으로 찾는다. 내용 유사도만 빼고 계산한다."""
    add_company_posting(deps)
    deps.vectors.delete(PID)
    card = next(c for c in feed(deps, as_of, keyword="가상전자").items if c.job_posting_id == PID)
    assert card.match_score > 0


def test_feed_without_search_terms_does_not_read_names(deps, as_of, monkeypatch):
    def fail():
        raise AssertionError("검색어나 회사 조건이 없으면 이름 색인을 읽지 않는다")

    monkeypatch.setattr(deps.catalog, "posting_names", fail)
    assert feed(deps, as_of).items
