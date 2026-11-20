"""같은 일, 부산에서 (B-05, §4.5 altScore, §4.6). T-15, T-21, T-22."""

import pytest
from rules.test_ncs_match import OVERSEAS_VN, add_posting

from opportunity.core import alternatives, copy_rules
from opportunity.models import LeaveReason, OppError, TrackEvent
from opportunity.models.posting import AltCandidate, AltCandidates, Job
from opportunity.models.region import LocalLifeData
from opportunity.ports import VectorHit
from opportunity.seeds import demo_world as w


def find(deps, as_of, base, user="demo1", **kwargs):
    return alternatives.find_busan_alternatives(deps, user, base, as_of=as_of, **kwargs)


def alt_ids(response):
    return [a.job_posting_id for a in response.alternatives]


def set_alts(deps, base, pairs):
    deps.catalog.put_alts(AltCandidates(job_posting_id=base, computed_at=w.DATA_AS_OF, candidates=[
        AltCandidate(job_posting_id=pid, similarity=sim) for pid, sim in pairs]))


def set_reason(deps, user, reason):
    deps.users.put_prefs(user, deps.users.get_prefs(user).model_copy(update={"leave_reason": reason}))


def test_alternatives_are_busan_and_similar(deps, as_of):
    response = find(deps, as_of, w.SEOUL_DATA)
    cfg = deps.config.alternatives
    assert response.alternatives and not response.expanded and not response.no_alternative
    assert len(response.alternatives) <= cfg.view_max
    for alt in response.alternatives:
        latest = deps.catalog.get_latest(alt.job_posting_id)
        assert latest.is_busan and alt.similarity >= cfg.min_similarity
        assert alt.facts[0].startswith("하는 일이 비슷함 (유사도 ")
        assert all(b.source and b.as_of for b in alt.badges)
        assert not any(copy_rules.find_forbidden(text) for text in [*alt.facts, alt.why_shown])
    scores = [a.alt_score for a in response.alternatives]
    assert scores == sorted(scores, reverse=True)
    assert response.data_as_of == w.DATA_AS_OF
    assert TrackEvent.ALT_SHOWN in deps.events.names()


def test_alt_score_formula(deps, as_of):
    weights = deps.config.alternatives.weights
    for alt in find(deps, as_of, w.SEOUL_DATA, leave_reason=LeaveReason.SKIP).alternatives:
        expected = weights.similarity * alt.similarity + weights.match * alt.match_score  # SKIP이면 r=0
        assert alt.alt_score == pytest.approx(expected, abs=1e-3)


def test_t21_alternatives_drop_closed_postings(deps, as_of):
    got = alt_ids(find(deps, as_of, w.SEOUL_DATA))
    # ALTS에 유사도 0.9로 들어 있어도 마감 공고는 빠진다. 9번은 isExpired가 아직 false다
    assert w.BUSAN_DATA_JUST_CLOSED not in got and w.BUSAN_DATA_EXPIRED not in got
    assert w.BUSAN_BACKEND not in got  # 유사도 0.52


def test_t15_no_alternative_after_expansion(deps, as_of):
    response = find(deps, as_of, w.SEOUL_GAME)
    assert response.alternatives == [] and response.expanded and response.no_alternative
    assert TrackEvent.NO_ALTERNATIVE in deps.events.names()
    assert TrackEvent.ALT_SHOWN not in deps.events.names()


def test_t15_expansion_uses_lower_threshold(deps, as_of, monkeypatch):
    cfg = deps.config.alternatives
    low = (cfg.expanded_min_similarity + cfg.min_similarity) / 2
    set_alts(deps, w.SEOUL_DATA_HYBRID, [(w.BUSAN_DATA, low), (w.BUSAN_BACKEND, cfg.expanded_min_similarity - 0.01)])
    calls = []

    def no_hits(vector, *, top_k, filter=None):
        calls.append(filter)
        return []

    monkeypatch.setattr(deps.vectors, "query", no_hits)
    response = find(deps, as_of, w.SEOUL_DATA_HYBRID, leave_reason=LeaveReason.NO_JOB_IN_BUSAN)
    assert response.expanded and not response.no_alternative
    assert alt_ids(response) == [w.BUSAN_DATA]
    assert response.alternatives[0].why_shown == copy_rules.WHY_SHOWN_BY_REASON[LeaveReason.NO_JOB_IN_BUSAN]
    assert calls and calls[0]["isBusan"] is True and calls[0]["jobMajor"] == "D" and calls[0]["active"] is True


def test_t22_want_seoul_life_keeps_mini_cards_only(deps, as_of):
    set_reason(deps, "demo1", LeaveReason.WANT_SEOUL_LIFE)
    set_alts(deps, w.SEOUL_DATA, [(w.BUSAN_DATA, 0.86), (w.BUSAN_DATA_PUBLIC, 0.81), (w.BUSAN_BACKEND, 0.75)])
    response = find(deps, as_of, w.SEOUL_DATA)  # 인자가 없으면 저장된 이유를 쓴다
    assert response.leave_reason_applied == LeaveReason.WANT_SEOUL_LIFE
    assert response.suggest_compare is False
    assert len(response.alternatives) <= deps.config.alternatives.mini_card_max
    assert all(a.why_shown == copy_rules.WHY_SHOWN_DEFAULT for a in response.alternatives)
    other = find(deps, as_of, w.SEOUL_DATA, leave_reason=LeaveReason.SALARY)  # 인자가 저장값보다 앞선다
    assert other.suggest_compare is True and len(other.alternatives) == 3


def test_reason_reorders_alternatives(deps, as_of):
    salary = find(deps, as_of, w.SEOUL_DATA, leave_reason=LeaveReason.SALARY)
    assert alt_ids(salary)[0] == w.BUSAN_DATA
    assert salary.alternatives[0].why_shown == copy_rules.WHY_SHOWN_BY_REASON[LeaveReason.SALARY]
    growth = find(deps, as_of, w.SEOUL_DATA, leave_reason=LeaveReason.GROWTH)
    assert alt_ids(growth)[0] == w.BUSAN_DATA_PUBLIC  # 이전기관이라 성장 이유에 맞는다
    assert growth.alternatives[0].why_shown == copy_rules.WHY_SHOWN_BY_REASON[LeaveReason.GROWTH]
    assert set(alt_ids(salary)) == set(alt_ids(growth))  # 순서만 바뀐다


def test_reason_fit_rules(deps):
    latest = deps.catalog.get_latest
    fit = alternatives.reason_fit
    assert fit(LeaveReason.SALARY, latest(w.BUSAN_DATA), expanded=False) == 1
    assert fit(LeaveReason.SALARY, latest(w.BUSAN_ACCOUNT_GANGSO), expanded=False) == 0  # 급여 미기재
    assert fit(LeaveReason.NO_JOB_IN_BUSAN, latest(w.BUSAN_DATA), expanded=True) == 1
    assert fit(LeaveReason.NO_JOB_IN_BUSAN, latest(w.BUSAN_DATA), expanded=False) == 0
    assert fit(LeaveReason.NO_JOB_IN_BUSAN, latest(w.BUSAN_DATA_PUBLIC), expanded=False) == 1
    assert fit(LeaveReason.WORK_LIFE, latest(w.BUSAN_ACCOUNT), expanded=False) == 1
    assert fit(LeaveReason.WORK_LIFE, latest(w.BUSAN_DATA), expanded=False) == 0
    assert fit(LeaveReason.HOUSING, latest(w.BUSAN_DATA), expanded=False) == 0
    assert fit(None, latest(w.BUSAN_DATA), expanded=False) == 0


def test_unknown_region_is_never_a_busan_alternative(deps, as_of):
    set_alts(deps, w.SEOUL_DATA, [(w.DATA_UNKNOWN_REGION, 0.95), (w.BUSAN_DATA, 0.86)])
    assert alt_ids(find(deps, as_of, w.SEOUL_DATA)) == [w.BUSAN_DATA]


def test_already_busan(deps, as_of):
    response = find(deps, as_of, w.BUSAN_DATA)
    assert response.alternatives == [] and response.reason == alternatives.ALREADY_BUSAN
    assert not response.no_alternative


def test_falls_back_to_vector_query_without_alts(deps, as_of):
    assert deps.catalog.get_alts(w.SEOUL_FINANCE_PUBLIC) is None
    response = find(deps, as_of, w.SEOUL_FINANCE_PUBLIC, "demo3")
    assert response.alternatives
    threshold = deps.config.alternatives.expanded_min_similarity if response.expanded \
        else deps.config.alternatives.min_similarity
    for alt in response.alternatives:
        latest = deps.catalog.get_latest(alt.job_posting_id)
        assert latest.is_busan and not latest.is_expired and alt.similarity >= threshold


def test_limit_and_not_found(deps, as_of):
    assert len(find(deps, as_of, w.SEOUL_DATA, limit=1).alternatives) == 1
    with pytest.raises(OppError) as e:
        find(deps, as_of, "wk24-NOPE")
    assert e.value.code == "POSTING_NOT_FOUND"
    with pytest.raises(OppError) as e:
        find(deps, as_of, w.SEOUL_DATA, limit=0)
    assert e.value.code == "INVALID_INPUT"


# ---------------------------------------------------------------- 해외 공고
OVERSEAS = "wk24-T-OVERSEAS"
OVERSEAS_SIDO26 = "wk24-T-OVERSEAS-26"  # sido=26이 남아 있는 해외 공고
WORK24_DATA = Job(code="D0101", middle="D01", major="D", name="데이터 분석가")


def add_overseas(deps):
    add_posting(deps, OVERSEAS, job=WORK24_DATA, work_region=OVERSEAS_VN)
    add_posting(deps, OVERSEAS_SIDO26, job=WORK24_DATA,
                work_region=OVERSEAS_VN.model_copy(update={"sido": "26", "unknown": False}))


def test_overseas_is_never_a_busan_alternative(deps, as_of):
    add_overseas(deps)
    set_alts(deps, w.SEOUL_DATA, [(OVERSEAS, 0.97), (OVERSEAS_SIDO26, 0.96), (w.BUSAN_DATA, 0.86)])
    assert alt_ids(find(deps, as_of, w.SEOUL_DATA)) == [w.BUSAN_DATA]


def test_overseas_not_found_by_vector_fallback(deps, as_of):
    add_overseas(deps)
    assert deps.catalog.get_alts(w.SEOUL_FINANCE_PUBLIC) is None
    deps.vectors.query = lambda vector, *, top_k, filter=None: [  # 필터를 무시하고 해외 공고를 돌려주는 경우
        VectorHit(key=key, similarity=0.95) for key in (OVERSEAS, OVERSEAS_SIDO26)]
    response = find(deps, as_of, w.SEOUL_FINANCE_PUBLIC, "demo3")
    assert not {OVERSEAS, OVERSEAS_SIDO26} & set(alt_ids(response))


@pytest.mark.parametrize("base", [OVERSEAS, OVERSEAS_SIDO26])
def test_overseas_base_finds_busan_alternatives_like_capital(deps, as_of, base):
    add_overseas(deps)
    response = find(deps, as_of, base)
    assert response.reason is None  # ALREADY_BUSAN이 아니다
    assert response.alternatives and not response.no_alternative
    for alt in response.alternatives:
        latest = deps.catalog.get_latest(alt.job_posting_id)
        assert latest.is_busan and not latest.is_overseas
    assert base not in alt_ids(response)


# ---------------------------------------------------------------- 통근 사실
def test_alternative_commute_fact_only_with_table_value(deps, as_of):
    label = copy_rules.COMMUTE_LABEL.format(minutes=35)
    assert not any(label in a.facts for a in find(deps, as_of, w.SEOUL_DATA).alternatives)
    deps.local_life = LocalLifeData(commute_minutes={"26290>26350": 35}, commute_source="부산교통공사 (테스트)",
                                    commute_as_of="2026-11-20")
    items = {a.job_posting_id: a for a in find(deps, as_of, w.SEOUL_DATA).alternatives}
    assert label in items[w.BUSAN_DATA].facts  # 해운대구. demo1은 남구에 산다
    assert label not in items[w.BUSAN_DATA_PUBLIC].facts  # 남구 → 남구는 표에 없다
