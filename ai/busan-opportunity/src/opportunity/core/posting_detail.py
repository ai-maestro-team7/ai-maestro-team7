"""공고 상세 (B-04).

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-04. 관련 정책은 `core.policies.related_policies`를 부른다.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import PostingDetailResponse, RegionalTalentResponse
from ..models.errors import posting_not_found
from ..models.posting import PostingLatest
from . import facts, policies, regions
from .alternatives import alternatives_for
from .context import freshness, load_context
from .ranking import cosine_similarity, is_open, match_level, profile_vector, score_posting


def _latest(deps: Deps, job_posting_id: str) -> PostingLatest:
    latest = deps.catalog.get_latest(job_posting_id)
    if latest is None:
        raise posting_not_found(job_posting_id)
    return latest


def _company_regional_talent(deps: Deps, posting: PostingLatest) -> bool:
    company = deps.catalog.get_company(posting.company_id) if posting.company_id else None
    return bool(company and company.regional_talent)


def get_posting(deps: Deps, user_id: str, job_posting_id: str, *,
                as_of: str | date | datetime | None = None) -> PostingDetailResponse:
    """LATEST → SNAP#을 읽어 요건, 지원 자격, 배지, 지역인재, 관련 정책, 대안 미리보기(최대 miniCardMax)를 돌려준다.

    필수 조건을 못 맞춘 공고도 숨기지 않고 이유를 붙여 보여 준다. 마감된 공고는 오류가 아니라 closed=true.
    출처·기준일이 없는 배지는 뺀다 (T-08). 없는 공고는 POSTING_NOT_FOUND.
    """
    cfg = deps.config
    ctx = load_context(deps, user_id, as_of)
    latest = _latest(deps, job_posting_id)
    snapshot = deps.catalog.get_snapshot(job_posting_id, latest.snapshot_id)
    if snapshot is None:
        raise posting_not_found(job_posting_id)

    badges = facts.valid_badges(snapshot.badges)
    profile_vec = profile_vector(deps, ctx.profile)
    vector = deps.vectors.get(job_posting_id)
    similarity = cosine_similarity(profile_vec, vector) if vector is not None else None
    match, result = score_posting(deps, ctx, latest, similarity)

    company_talent = _company_regional_talent(deps, latest)
    talent = (facts.regional_talent_view(cfg, ctx.profile, latest, company_regional_talent=company_talent)
              if facts.needs_regional_view(latest, company_talent) else None)

    is_capital = regions.is_capital_area(cfg, snapshot.work_region)
    preview = []
    if is_capital:
        preview = alternatives_for(deps, ctx, latest, leave_reason=None, size=cfg.alternatives.mini_card_max,
                                   profile_vec=profile_vec).alternatives

    related = policies.related_policies(deps, ctx.profile, ctx.prefs, latest, as_of=ctx.as_of)
    data_as_of, _ = freshness(deps, ctx.as_of)
    fact_list = facts.compact([facts.job_fact(cfg, match.job_match), *facts.eligibility_facts(result),
                               facts.deadline_fact(latest.closes_at, ctx.as_of)])
    return PostingDetailResponse(
        posting=snapshot.model_copy(update={"badges": badges}),
        is_busan=regions.is_busan(cfg, snapshot.work_region), is_capital_area=is_capital,
        closed=not is_open(latest, ctx.as_of), is_sample=latest.is_sample,
        match_level=match_level(cfg, match.score), eligibility=result, badges=badges, regional_talent=talent,
        related_policies=related, alternatives_preview=preview, facts=fact_list, data_as_of=data_as_of,
    )


def get_regional_talent(deps: Deps, user_id: str, job_posting_id: str, *,
                        as_of: str | date | datetime | None = None) -> RegionalTalentResponse:
    """공공기관 공고의 지역인재 전형 해당 가능성. 문구는 "대상일 수 있어요"로만 쓴다."""
    ctx = load_context(deps, user_id, as_of)
    latest = _latest(deps, job_posting_id)
    view = facts.regional_talent_view(deps.config, ctx.profile, latest,
                                      company_regional_talent=_company_regional_talent(deps, latest))
    return RegionalTalentResponse(job_posting_id=latest.job_posting_id, organization=latest.organization,
                                  regional_talent=view)
