"""같은 일, 부산에서 (B-05). 수도권 공고와 하는 일이 비슷한 부산 공고를 찾는다.

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-05, §4.5 altScore, §4.6 이유별 재정렬. 테스트: T-15, T-21, T-22.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import AlternativeItem, AlternativesResponse
from ..models.enums import CheonggeulType, LeaveReason, TrackEvent
from ..models.errors import invalid_input, posting_not_found
from ..models.posting import PostingLatest
from . import copy_rules, facts, regions
from .context import UserContext, freshness, load_context
from .ranking import (
    active_filter,
    cosine_similarity,
    is_open,
    match_level,
    profile_vector,
    score_posting,
)
from .texts import posting_text

ALREADY_BUSAN = "ALREADY_BUSAN"


def reason_fit(reason: LeaveReason | None, posting: PostingLatest, *, expanded: bool) -> float:
    """이유 적합도 r (§4.6). 조건에 맞으면 1, 아니면 0."""
    badges = posting.badges
    if reason == LeaveReason.SALARY:
        ok = facts.salary_disclosed(posting.salary) or facts.has_cheonggeul(badges, CheonggeulType.SALARY)
    elif reason == LeaveReason.NO_JOB_IN_BUSAN:
        ok = expanded or facts.is_relocated(badges)
    elif reason == LeaveReason.GROWTH:
        ok = facts.has_cheonggeul(badges, CheonggeulType.FUTURE) or facts.is_relocated(badges)
    elif reason == LeaveReason.WORK_LIFE:
        ok = facts.has_cheonggeul(badges, CheonggeulType.WORK_LIFE)
    else:
        ok = False
    return 1.0 if ok else 0.0


def _base_vector(deps: Deps, base: PostingLatest) -> list[float] | None:
    vector = deps.vectors.get(base.job_posting_id)
    if vector is not None:
        return vector
    snapshot = deps.catalog.get_snapshot(base.job_posting_id, base.snapshot_id)
    return deps.embedder.embed(posting_text(snapshot), kind="document") if snapshot else None


def _vector_candidates(deps: Deps, ctx: UserContext, base: PostingLatest, **extra) -> dict[str, float]:
    vector = _base_vector(deps, base)
    if vector is None:
        return {}
    hits = deps.vectors.query(vector, top_k=deps.config.alternatives.precompute_top_k,
                              filter=active_filter(ctx.as_of, isBusan=True, **extra))
    return {h.key: h.similarity for h in hits}


def _first_pass(deps: Deps, ctx: UserContext, base: PostingLatest) -> dict[str, float]:
    """미리 계산한 후보(ALTS). 없으면 벡터 인덱스를 바로 질의한다."""
    alts = deps.catalog.get_alts(base.job_posting_id)
    if alts is not None:
        return {c.job_posting_id: c.similarity for c in alts.candidates}
    return _vector_candidates(deps, ctx, base)


def _expanded_pass(deps: Deps, ctx: UserContext, base: PostingLatest, first: dict[str, float]) -> dict[str, float]:
    """직종 상위 분류(대분류)로 한 단계 넓혀 다시 찾는다. ALTS 후보도 함께 본다."""
    extra = {"jobMajor": base.job.major} if base.job.major else {}
    found = dict(first)
    for key, sim in _vector_candidates(deps, ctx, base, **extra).items():
        found[key] = max(sim, found.get(key, sim))
    return found


def _eligible(deps: Deps, ctx: UserContext, base: PostingLatest, sims: dict[str, float],
              threshold: float) -> list[tuple[PostingLatest, float]]:
    """유사도 기준을 넘고, 근무지가 부산으로 확인되고, 진행 중인 공고만 남긴다."""
    keys = [k for k, s in sims.items() if s >= threshold and k != base.job_posting_id]
    latest = deps.catalog.batch_get_latest(keys) if keys else {}
    cfg = deps.config
    return [(p, sims[k]) for k, p in latest.items()
            if regions.is_busan(cfg, p.work_region) and is_open(p, ctx.as_of)]


def _items(deps: Deps, ctx: UserContext, rows: list[tuple[PostingLatest, float]], reason: LeaveReason | None, *,
           expanded: bool, size: int, profile_vec: list[float] | None) -> list[AlternativeItem]:
    cfg = deps.config
    w = cfg.alternatives.weights
    scored = []
    for posting, similarity in rows:
        vector = deps.vectors.get(posting.job_posting_id) if profile_vec is not None else None
        content = cosine_similarity(profile_vec, vector) if vector is not None else None
        match, _ = score_posting(deps, ctx, posting, content)
        r = reason_fit(reason, posting, expanded=expanded)
        alt = w.similarity * similarity + w.match * match.score + w.reason * r
        scored.append((alt, similarity, posting, match, r))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2].job_posting_id))

    items = []
    for alt, similarity, posting, match, r in scored[:size]:
        talent = facts.regional_talent_view(cfg, ctx.profile, posting)
        why = copy_rules.WHY_SHOWN_BY_REASON.get(reason, copy_rules.WHY_SHOWN_DEFAULT) if r else None
        reason_facts = [facts.FACT_SALARY_DISCLOSED] if facts.salary_disclosed(posting.salary) else []
        items.append(AlternativeItem(
            job_posting_id=posting.job_posting_id, title=posting.title, organization=posting.organization,
            work_region=posting.work_region, closes_at=posting.closes_at,
            similarity=round(similarity, facts.SCORE_DIGITS), match_score=round(match.score, facts.SCORE_DIGITS),
            match_level=match_level(cfg, match.score), alt_score=round(alt, facts.SCORE_DIGITS),
            badges=facts.valid_badges(posting.badges),
            facts=facts.compact([facts.similarity_fact(similarity), *reason_facts,
                                 *facts.badge_facts(posting.badges, talent),
                                 facts.deadline_fact(posting.closes_at, ctx.as_of)]),
            why_shown=why or copy_rules.WHY_SHOWN_DEFAULT, is_sample=posting.is_sample,
        ))
    return items


def alternatives_for(deps: Deps, ctx: UserContext, base: PostingLatest, *, leave_reason: LeaveReason | None,
                     size: int, profile_vec: list[float] | None = None) -> AlternativesResponse:
    """이미 읽은 사용자 문맥으로 대안을 찾는다. 상세 화면의 미리보기도 이 함수를 쓴다."""
    cfg = deps.config
    reason = LeaveReason(leave_reason) if leave_reason is not None else ctx.prefs.leave_reason
    seoul_life = reason == LeaveReason.WANT_SEOUL_LIFE
    if seoul_life:
        size = min(size, cfg.alternatives.mini_card_max)
    data_as_of, _ = freshness(deps, ctx.as_of)
    response = AlternativesResponse(base_job_posting_id=base.job_posting_id, leave_reason_applied=reason,
                                    suggest_compare=not seoul_life, data_as_of=data_as_of)
    if regions.is_busan(cfg, base.work_region):
        response.reason = ALREADY_BUSAN
        return response

    if profile_vec is None:
        profile_vec = profile_vector(deps, ctx.profile)
    first = _first_pass(deps, ctx, base)
    rows = _eligible(deps, ctx, base, first, cfg.alternatives.min_similarity)
    expanded = False
    if not rows:
        expanded = True
        rows = _eligible(deps, ctx, base, _expanded_pass(deps, ctx, base, first),
                         cfg.alternatives.expanded_min_similarity)
    response.expanded = expanded
    response.alternatives = _items(deps, ctx, rows, reason, expanded=expanded, size=size, profile_vec=profile_vec)

    if response.alternatives:
        deps.events.emit(TrackEvent.ALT_SHOWN, baseJobPostingId=base.job_posting_id,
                         count=len(response.alternatives), expanded=expanded)
    else:
        response.no_alternative = True
        deps.events.emit(TrackEvent.NO_ALTERNATIVE, baseJobPostingId=base.job_posting_id,
                         jobMajor=base.job.major or "")
    return response


def find_busan_alternatives(deps: Deps, user_id: str, job_posting_id: str, *,
                            leave_reason: LeaveReason | None = None, limit: int | None = None,
                            as_of: str | date | datetime | None = None) -> AlternativesResponse:
    """미리 계산한 후보(ALTS)를 이 사용자 기준으로 다시 정렬한다. 없으면 벡터 인덱스를 바로 질의한다.

    유사도 minSimilarity 이상만 남기고 altScore로 정렬해 최대 viewMax개 (limit로 줄일 수 있음).
    0개면 직종 상위 분류로 넓혀 expandedMinSimilarity로 다시 찾는다. 그래도 0개면 noAlternative=true이고
    NO_ALTERNATIVE 이벤트를 남긴다 (T-15). 부산 공고를 넣으면 빈 목록과 reason=ALREADY_BUSAN.
    보여 준 대안이 있으면 ALT_SHOWN 이벤트를 남긴다. 마감된 공고는 뺀다 (T-21).
    """
    if limit is not None and limit < 1:
        raise invalid_input("limit은 1 이상이어야 해요.", field="limit")
    ctx = load_context(deps, user_id, as_of)
    base = deps.catalog.get_latest(job_posting_id)
    if base is None:
        raise posting_not_found(job_posting_id)
    view_max = deps.config.alternatives.view_max
    size = min(limit, view_max) if limit is not None else view_max
    return alternatives_for(deps, ctx, base, leave_reason=leave_reason, size=size)
