"""부산 대안 후보 미리 계산 (B-02). 수도권 공고마다 부산·진행 중 후보를 유사도와 함께 ALTS에 둔다.

벡터 질의는 `ranking.candidateTopK.busan`개를 받아 진행 중 여부를 카탈로그로 한 번 더 확인하고,
`alternatives.precomputeTopK`개까지 남긴다. 유사도 기준(minSimilarity)은 대안 화면이 적용한다.
"""

from datetime import datetime

from ..core import clock
from ..core.texts import posting_text
from ..deps import Deps
from ..models.posting import AltCandidate, AltCandidates, PostingLatest


def busan_filter(deps: Deps, as_of: datetime) -> dict:
    return {"isBusan": True, "active": True, "deadline": {"$gte": clock.deadline_number(clock.day(as_of))}}


def _open_busan(latest: PostingLatest | None, as_of: datetime) -> bool:
    return (latest is not None and latest.is_busan and not latest.is_expired
            and not clock.is_expired(latest.closes_at, as_of))


def compute_alternatives(deps: Deps, base: PostingLatest, as_of: datetime) -> AltCandidates:
    vector = deps.vectors.get(base.job_posting_id)
    if vector is None:
        snapshot = deps.catalog.get_snapshot(base.job_posting_id, base.snapshot_id)
        vector = deps.embedder.embed(posting_text(snapshot), kind="document") if snapshot else None
    candidates: list[AltCandidate] = []
    if vector is not None:
        hits = deps.vectors.query(vector, top_k=deps.config.ranking.candidate_top_k.busan,
                                  filter=busan_filter(deps, as_of))
        hits = [h for h in hits if h.key != base.job_posting_id]
        latest = deps.catalog.batch_get_latest([h.key for h in hits])
        for hit in hits:
            if _open_busan(latest.get(hit.key), as_of):
                candidates.append(AltCandidate(job_posting_id=hit.key, similarity=round(hit.similarity, 4)))
            if len(candidates) >= deps.config.alternatives.precompute_top_k:
                break
    return AltCandidates(job_posting_id=base.job_posting_id, candidates=candidates, computed_at=clock.iso(as_of))


def precompute_alternatives(deps: Deps, job_posting_ids: list[str], as_of: datetime) -> int:
    """수도권·진행 중 공고의 ALTS를 다시 쓴다. 쓴 건수를 돌려준다."""
    written = 0
    for job_posting_id in job_posting_ids:
        base = deps.catalog.get_latest(job_posting_id)
        if base is None or not base.is_capital_area or base.is_expired or clock.is_expired(base.closes_at, as_of):
            continue
        deps.catalog.put_alts(compute_alternatives(deps, base, as_of))
        written += 1
    return written
