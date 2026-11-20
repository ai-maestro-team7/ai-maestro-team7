"""임베딩과 부산 대안 후보."""

from unit.enrich import factories as f

from opportunity.core import clock
from opportunity.core.texts import posting_text
from opportunity.enrich.embed import embed_posting
from opportunity.enrich.precompute_alternatives import compute_alternatives, precompute_alternatives
from opportunity.seeds import demo_world as w


def test_embed_puts_vector_with_meta(deps):
    snap = f.store(deps, f.snapshot())
    latest = deps.catalog.get_latest(snap.job_posting_id)
    vector = embed_posting(deps, snap, latest)
    assert deps.vectors.get(snap.job_posting_id) == vector == deps.embedder.embed(posting_text(snap))
    meta = deps.vectors.rows[snap.job_posting_id][1]
    assert meta == {"isBusan": True, "sido": "26", "jobMajor": "D", "active": True, "deadline": 20261231,
                    "title": "데이터 분석 신입"}


def test_embed_unknown_region_has_empty_sido(deps):
    snap = f.store(deps, f.snapshot(region=(None, None, "근무지 확인 필요")))
    embed_posting(deps, snap, deps.catalog.get_latest(snap.job_posting_id))
    meta = deps.vectors.rows[snap.job_posting_id][1]
    assert meta["sido"] == "" and meta["isBusan"] is False


def test_alternatives_only_open_busan(deps, as_of):
    now = clock.parse_as_of(as_of)
    alts = compute_alternatives(deps, deps.catalog.get_latest(w.SEOUL_DATA), now)
    ids = [c.job_posting_id for c in alts.candidates]
    assert w.BUSAN_DATA in ids and w.BUSAN_DATA_PUBLIC in ids
    for pid in ids:
        latest = deps.catalog.get_latest(pid)
        assert latest.is_busan and not latest.is_expired and not clock.is_expired(latest.closes_at, now)
    # 마감, 어제 마감(isExpired는 아직 false), 근무지 미상, 수도권은 빠진다
    for pid in (w.BUSAN_DATA_EXPIRED, w.BUSAN_DATA_JUST_CLOSED, w.DATA_UNKNOWN_REGION, w.SEOUL_DATA,
                w.SEOUL_DATA_HYBRID):
        assert pid not in ids
    sims = [c.similarity for c in alts.candidates]
    assert sims == sorted(sims, reverse=True)
    assert alts.computed_at == clock.iso(now)


def test_alternatives_respect_precompute_top_k(deps, as_of):
    deps.config.alternatives.precompute_top_k = 1
    alts = compute_alternatives(deps, deps.catalog.get_latest(w.SEOUL_DATA), clock.parse_as_of(as_of))
    assert len(alts.candidates) == 1 and alts.candidates[0].job_posting_id == w.BUSAN_DATA


def test_precompute_only_capital_area(deps, as_of):
    deps.catalog.alts.clear()
    written = precompute_alternatives(deps, [w.SEOUL_DATA, w.BUSAN_DATA, w.SEOUL_GAME, "missing"],
                                      clock.parse_as_of(as_of))
    assert written == 2
    assert set(deps.catalog.alts) == {w.SEOUL_DATA, w.SEOUL_GAME}
