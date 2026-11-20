"""맞춤 공고 피드 (B-03). matchScore에는 부산 가산점을 넣지 않는다. 가산점은 rankScore에만 넣는다.

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-03, §4.4, §4.5. 테스트: T-01, T-02, T-04, T-21.
"""

import base64
import binascii
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ..config import OpportunityConfig
from ..deps import Deps
from ..models.api import EligibilityResult, FeedResponse, PostingCard, Ranking
from ..models.enums import CheonggeulType, EmploymentType, MatchLevel, RemoteWork, Sort
from ..models.errors import invalid_input
from ..models.posting import AltCandidates, Job, PostingLatest
from ..models.profile import BasicProfile, DesiredJob
from . import clock, copy_rules, facts, regions
from .context import UserContext, freshness, load_context
from .eligibility import judge, required_ratio
from .texts import profile_text

REGION_ALL, REGION_BUSAN, REGION_CAPITAL = "ALL", "BUSAN", "CAPITAL"


@dataclass
class MatchBreakdown:
    """적합도와 항목별 값. 측정하지 못한 항목은 None이고 가중치를 나머지로 다시 나눈다."""

    score: float
    job_match: float | None = None
    content_sim: float | None = None
    required_ok: float | None = None
    preferred_ok: float | None = None


# ---------------------------------------------------------------- 적합도 항목
def _norm(text: str | None) -> str:
    return "".join((text or "").lower().replace("·", "").split())


def _job_match_one(config: OpportunityConfig, desired: DesiredJob, job: Job) -> float | None:
    levels = config.match.job_match_levels
    code = (desired.work24_code or "").strip()
    if code and (job.code or job.middle or job.major):
        if job.code and code == job.code:
            return levels.exact
        if job.middle and code.startswith(job.middle):
            return levels.same_middle
        if job.major and code.startswith(job.major):
            return levels.same_major
        return 0.0
    mine, theirs = _norm(desired.name), _norm(job.name)
    if not mine or not theirs:
        return None
    return levels.exact if (mine in theirs or theirs in mine) else 0.0


def job_match_value(config: OpportunityConfig, profile: BasicProfile, job: Job) -> float | None:
    """희망 직무가 여러 개면 가장 높은 값. 비교할 정보가 없으면 None."""
    values = [v for v in (_job_match_one(config, d, job) for d in profile.desired_jobs) if v is not None]
    return max(values) if values else None


def content_sim_value(config: OpportunityConfig, similarity: float | None) -> float | None:
    """코사인 값을 contentSimRange(low, high)로 0~1로 바꾼다."""
    if similarity is None:
        return None
    low, high = config.match.content_sim_range.low, config.match.content_sim_range.high
    return min(1.0, max(0.0, (similarity - low) / (high - low)))


def _priority_met(priority: str, posting: PostingLatest) -> bool | None:
    """사용자 중요 조건이 공고에서 확인되는지. 모르는 조건은 None."""
    if priority == "SALARY":
        return facts.salary_disclosed(posting.salary)
    if priority == "STABILITY":
        return posting.org_type in facts.PUBLIC_ORG_TYPES or posting.employment_type == EmploymentType.FULL_TIME
    if priority == "WORK_LIFE":
        return (facts.has_cheonggeul(posting.badges, CheonggeulType.WORK_LIFE)
                or posting.remote_work in (RemoteWork.FULL, RemoteWork.HYBRID))
    if priority == "GROWTH":
        return facts.has_cheonggeul(posting.badges, CheonggeulType.FUTURE) or facts.is_relocated(posting.badges)
    return None


def preferred_ok_value(profile: BasicProfile, posting: PostingLatest) -> float | None:
    """우대 요건 일치 비율과 중요 조건 충족 비율의 평균. 잴 수 없는 쪽은 뺀다.

    프로필에 기술·자격증이 하나도 없으면 우대 요건은 "부족"이 아니라 "미확인"이라 재지 않는다.
    """
    parts = []
    owned = {_norm(s) for s in [*profile.skills, *profile.certificates] if _norm(s)}
    if posting.preferred_names and owned:
        hit = sum(1 for name in posting.preferred_names if _norm(name) in owned)
        parts.append(hit / len(posting.preferred_names))
    checks = [m for m in (_priority_met(p, posting) for p in profile.priorities) if m is not None]
    if checks:
        parts.append(sum(1 for m in checks if m) / len(checks))
    return sum(parts) / len(parts) if parts else None


def match_score(config: OpportunityConfig, profile: BasicProfile, posting: PostingLatest, *,
                content_similarity: float | None = None,
                eligibility: EligibilityResult | None = None) -> MatchBreakdown:
    """적합도 0~1. 공고의 부산 여부는 계산에 쓰지 않는다 (T-04)."""
    w = config.match.weights
    jm = job_match_value(config, profile, posting.job)
    cs = content_sim_value(config, content_similarity)
    ro = required_ratio(eligibility, config.match.unknown_condition_value) if eligibility is not None else None
    po = preferred_ok_value(profile, posting)
    measured = [(weight, value) for weight, value in
                ((w.job_match, jm), (w.content_sim, cs), (w.required_ok, ro), (w.preferred_ok, po))
                if value is not None]
    total = sum(weight for weight, _ in measured)
    score = sum(weight * value for weight, value in measured) / total if total else 0.0
    return MatchBreakdown(score=score, job_match=jm, content_sim=cs, required_ok=ro, preferred_ok=po)


def rank_score(config: OpportunityConfig, match: float, *, is_busan: bool, sort: Sort) -> float:
    """정렬 점수. sort=BUSAN_FIRST이고 부산 근무이며 match >= boostMinMatch일 때만 busanBoost를 더한다."""
    r = config.ranking
    if sort == Sort.BUSAN_FIRST and is_busan and match >= r.boost_min_match:
        return match + r.busan_boost
    return match


def match_level(config: OpportunityConfig, match: float) -> MatchLevel:
    """화면에 보여 줄 3단계. good 이상 GOOD, fair 이상 FAIR, 그 밖은 LOW."""
    levels = config.match.levels
    if match >= levels.good:
        return MatchLevel.GOOD
    if match >= levels.fair:
        return MatchLevel.FAIR
    return MatchLevel.LOW


# ---------------------------------------------------------------- 벡터 도우미 (대안·상세도 쓴다)
def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def profile_vector(deps: Deps, profile: BasicProfile) -> list[float]:
    return deps.embedder.embed(profile_text(profile), kind="query")


def active_filter(as_of: datetime, **extra) -> dict:
    """진행 중 공고만 찾는 벡터 필터 (active=true, deadline >= 오늘)."""
    return {**extra, "active": True, "deadline": {"$gte": clock.deadline_number(clock.day(as_of))}}


def is_open(posting: PostingLatest, as_of: datetime) -> bool:
    """isExpired가 아직 false여도 마감일이 지났으면 닫힌 공고다 (T-21)."""
    return not posting.is_expired and not clock.is_expired(posting.closes_at, as_of)


def score_posting(deps: Deps, ctx: UserContext, posting: PostingLatest,
                  similarity: float | None) -> tuple[MatchBreakdown, EligibilityResult]:
    result = judge(deps, ctx.profile, posting.eligibility_rules)
    return match_score(deps.config, ctx.profile, posting, content_similarity=similarity, eligibility=result), result


# ---------------------------------------------------------------- 피드
def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = json.loads(base64.urlsafe_b64decode(cursor.encode()))["offset"]
    except (binascii.Error, ValueError, KeyError, TypeError) as e:
        raise invalid_input("cursor가 올바르지 않아요.", field="cursor") from e
    if not isinstance(offset, int) or offset < 0:
        raise invalid_input("cursor가 올바르지 않아요.", field="cursor")
    return offset


def _check_region(region: str) -> None:
    if region in (REGION_ALL, REGION_BUSAN, REGION_CAPITAL) or region in regions.SIDO_NAMES:
        return
    raise invalid_input("region 값이 올바르지 않아요.", field="region")


def _in_region(posting: PostingLatest, sidos: list[str] | None) -> bool:
    if sidos is None:
        return True
    return not posting.work_region.unknown and posting.work_region.sido in sidos


def _job_code_ok(posting: PostingLatest, codes: list[str] | None) -> bool:
    """요청한 직종 코드로 거른다. 중분류·대분류 코드를 넣으면 그 아래 공고를 모두 남긴다."""
    if not codes:
        return True
    job = posting.job
    return any(job.code and job.code.startswith(code) or code in (job.middle, job.major) for code in codes)


def _keyword_ok(posting: PostingLatest, keyword: str | None) -> bool:
    if not keyword or not keyword.strip():
        return True
    needle = keyword.strip().lower()
    return any(needle in (text or "").lower() for text in (posting.title, posting.organization, posting.job.name))


def _sort_key(sort: Sort):
    if sort == Sort.DEADLINE:
        return lambda row: (row["posting"].closes_at, -row["rank"], row["posting"].job_posting_id)
    if sort == Sort.RECENT:
        return lambda row: (_neg_time(row["posting"].checked_at), -row["rank"], row["posting"].job_posting_id)
    return lambda row: (-row["rank"], -row["match"].score, row["posting"].closes_at, row["posting"].job_posting_id)


def _neg_time(iso_text: str) -> float:
    return -clock.parse_as_of(iso_text).timestamp()


def busan_alternatives_count(cfg: OpportunityConfig, alts: AltCandidates | None, as_of: datetime,
                             latest_by_id: dict[str, PostingLatest]) -> int | None:
    """미리 계산한 ALTS 가운데 유사도 기준을 넘고 진행 중인 부산 공고 수 (viewMax까지). ALTS가 없으면 None."""
    if alts is None:
        return None
    count = 0
    for cand in alts.candidates:
        latest = latest_by_id.get(cand.job_posting_id)
        if (latest is not None and cand.similarity >= cfg.alternatives.min_similarity
                and regions.is_busan(cfg, latest.work_region) and is_open(latest, as_of)):
            count += 1
    return min(count, cfg.alternatives.view_max)


def _card(deps: Deps, row: dict, as_of: datetime, alt_count: int | None) -> PostingCard:
    cfg, posting, match = deps.config, row["posting"], row["match"]
    fact_list = facts.compact([facts.job_fact(cfg, match.job_match), *facts.eligibility_facts(row["eligibility"]),
                               facts.deadline_fact(posting.closes_at, as_of)])
    return PostingCard(
        job_posting_id=posting.job_posting_id, title=posting.title, organization=posting.organization,
        org_type=posting.org_type, work_region=posting.work_region,
        is_busan=regions.is_busan(cfg, posting.work_region),
        is_capital_area=regions.is_capital_area(cfg, posting.work_region), job=posting.job,
        closes_at=posting.closes_at, rolling=posting.rolling, salary=posting.salary,
        match_score=round(match.score, facts.SCORE_DIGITS), match_level=match_level(cfg, match.score),
        rank_score=round(row["rank"], facts.SCORE_DIGITS), eligibility=row["eligibility"],
        badges=facts.valid_badges(posting.badges), facts=fact_list, busan_alternatives_count=alt_count,
        is_sample=posting.is_sample,
    )


def _few_busan_jobs(cfg: OpportunityConfig, rows: list[dict]) -> bool:
    """같은 중분류 이상으로 맞는 부산 공고가 하나도 없으면 True."""
    need = cfg.match.job_match_levels.same_middle
    return not any(regions.is_busan(cfg, r["posting"].work_region) and (r["match"].job_match or 0) >= need
                   for r in rows)


def search_postings(deps: Deps, user_id: str, *, region: str = "ALL", sort: Sort | None = None,
                    job_codes: list[str] | None = None, keyword: str | None = None, cursor: str | None = None,
                    limit: int = 20, as_of: str | date | datetime | None = None) -> FeedResponse:
    """전국 공고를 찾아 정렬한다. 후보는 벡터 질의 두 번(부산, 전국)으로 모은다. 이 경로에 LLM은 없다.

    sort가 None이면 사용자 설정을 쓴다. BUSAN_FIRST와 MATCH는 공고 집합이 같고 순서만 다르다 (T-01).
    마감된 공고는 뺀다 (T-21). 수도권 공고에는 busanAlternativesCount를 붙인다.
    """
    cfg = deps.config
    region = (region or REGION_ALL).strip().upper()
    _check_region(region)
    if limit < 1:
        raise invalid_input("limit은 1 이상이어야 해요.", field="limit")
    offset = _decode_cursor(cursor)
    ctx = load_context(deps, user_id, as_of, require_jobs=True)
    sort = Sort(sort) if sort is not None else ctx.prefs.sort

    # 1. 후보: 부산 필터 질의와 전국 질의를 합친다. 같은 공고는 높은 유사도를 쓴다.
    vector = profile_vector(deps, ctx.profile)
    top_k = cfg.ranking.candidate_top_k
    similarity: dict[str, float] = {}
    for hits in (deps.vectors.query(vector, top_k=top_k.busan, filter=active_filter(ctx.as_of, isBusan=True)),
                 deps.vectors.query(vector, top_k=top_k.all, filter=active_filter(ctx.as_of))):
        for hit in hits:
            similarity[hit.key] = max(hit.similarity, similarity.get(hit.key, hit.similarity))
    latest_by_id = deps.catalog.batch_get_latest(list(similarity))

    # 2. 거르기: 마감, 지역, 직종 코드, 검색어
    sidos = regions.region_sidos(cfg, region)
    rows = []
    for pid, posting in latest_by_id.items():
        if not (is_open(posting, ctx.as_of) and _in_region(posting, sidos)
                and _job_code_ok(posting, job_codes) and _keyword_ok(posting, keyword)):
            continue
        match, result = score_posting(deps, ctx, posting, similarity[pid])
        rank = rank_score(cfg, match.score, is_busan=regions.is_busan(cfg, posting.work_region), sort=sort)
        rows.append({"posting": posting, "match": match, "eligibility": result, "rank": rank})

    # 3. 정렬과 쪽 나누기
    rows.sort(key=_sort_key(sort))
    page = rows[offset:offset + limit]
    next_cursor = _encode_cursor(offset + limit) if offset + limit < len(rows) else None

    # 4. 수도권 카드의 부산 대안 수. ALTS 후보를 한 번에 읽는다.
    capital = [r["posting"] for r in page if regions.is_capital_area(cfg, r["posting"].work_region)]
    alts_by_id = {p.job_posting_id: deps.catalog.get_alts(p.job_posting_id) for p in capital}
    cand_ids = {c.job_posting_id for alts in alts_by_id.values() if alts for c in alts.candidates}
    cand_latest = deps.catalog.batch_get_latest(sorted(cand_ids)) if cand_ids else {}
    cards = []
    for row in page:
        posting = row["posting"]
        count = None
        if posting.job_posting_id in alts_by_id:
            count = busan_alternatives_count(cfg, alts_by_id[posting.job_posting_id], ctx.as_of, cand_latest)
        cards.append(_card(deps, row, ctx.as_of, count))

    # 5. 이유 질문: 수도권으로 처음 바꿨을 때 한 번
    ask = False
    if (region == REGION_CAPITAL or region in cfg.data.capital_area_sido) and ctx.prefs.leave_reason is None:
        asked = deps.users.mark_leave_reason_asked(user_id, clock.iso(ctx.as_of))
        ask = asked or not cfg.leave_reason.ask_once_per_user

    empty_message = None
    if offset == 0 and (sidos is None or cfg.data.busan_sido in sidos) and _few_busan_jobs(cfg, rows):
        empty_message = copy_rules.EMPTY_BUSAN

    data_as_of, stale = freshness(deps, ctx.as_of)
    ranking = Ranking(sort=sort, basis=copy_rules.RANKING_BASIS[sort],
                      busan_boost=cfg.ranking.busan_boost if sort == Sort.BUSAN_FIRST else None)
    return FeedResponse(items=cards, ranking=ranking, data_as_of=data_as_of, stale=stale, next_cursor=next_cursor,
                        ask_leave_reason=ask, empty_message=empty_message)
