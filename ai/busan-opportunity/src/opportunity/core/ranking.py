"""맞춤 공고 피드 (B-03). matchScore에는 부산 가산점을 넣지 않는다. 가산점은 rankScore에만 넣는다.

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-03, §4.4, §4.5. 테스트: T-01, T-02, T-04, T-21.
"""

import base64
import binascii
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ..config import OpportunityConfig
from ..deps import Deps
from ..models.api import EligibilityResult, FeedResponse, PostingCard, Ranking
from ..models.enums import (
    CareerType,
    CheonggeulType,
    EmploymentType,
    MatchLevel,
    RegionalTalentStatus,
    RemoteWork,
    Sort,
)
from ..models.errors import invalid_input
from ..models.posting import AltCandidates, Job, PostingLatest
from ..models.profile import BasicProfile, DesiredJob
from . import clock, copy_rules, facts, regions
from .context import UserContext, freshness, load_context
from .eligibility import judge, required_ratio
from .texts import profile_text

REGION_ALL, REGION_BUSAN, REGION_CAPITAL, REGION_OVERSEAS = "ALL", "BUSAN", "CAPITAL", "OVERSEAS"

# 데이터 범위 (개발계획서4 §9.1). OFFICIAL = 공공 API로 모은 공고, TEAM = 팀이 넣어 둔 공고(지금은 시연용 DEMO)
SCOPE_ALL, SCOPE_OFFICIAL, SCOPE_TEAM = "ALL", "OFFICIAL", "TEAM"
SCOPES = (SCOPE_ALL, SCOPE_OFFICIAL, SCOPE_TEAM)
NAME_MATCH_LIMIT = 300  # 이름 색인에서 더하는 후보 상한 (B-D08). 넘으면 기관·회사 이름이 맞는 공고부터 넣는다

# 직무 일치의 근거. 사실 문구를 고를 때 쓴다 (facts.job_fact)
BASIS_WORK24, BASIS_NAME, BASIS_NCS = facts.BASIS_WORK24, facts.BASIS_NAME, facts.BASIS_NCS
BASIS_NCS_MAJOR_NAME = facts.BASIS_NCS_MAJOR_NAME
BASIS_NCS_MAJOR = facts.BASIS_NCS_MAJOR

# NCS 코드: 대분류 2 + 중분류 2 + 소분류 2 + 세분류 2 = 8자리
NCS_FULL = 8
NCS_MIDDLE = 4
NCS_MAJOR = 2
_NCS_DIGITS = re.compile(r"^\d{2}(?:\d{2}){0,3}$")
_ALIO_NCS = re.compile(r"^R6000(\d{2})$")  # 잡알리오 코드. 끝 2자리가 NCS 대분류 번호


@dataclass
class MatchBreakdown:
    """적합도와 항목별 값. 측정하지 못한 항목은 None이고 가중치를 나머지로 다시 나눈다."""

    score: float
    job_match: float | None = None
    job_basis: str | None = None  # BASIS_* 가운데 job_match를 정한 쪽
    content_sim: float | None = None
    required_ok: float | None = None
    preferred_ok: float | None = None


# ---------------------------------------------------------------- 적합도 항목
def _norm(text: str | None) -> str:
    return "".join((text or "").lower().replace("·", "").split())


def _work24_match(config: OpportunityConfig, desired: DesiredJob, job: Job) -> float | None:
    """고용24 직종 코드 비교. 공고에 세분류·중분류 코드가 없으면 None.

    잡알리오 공고는 `job.major`에 NCS 대분류 이름이 들어 있어 고용24 코드로 보지 않는다.
    """
    levels = config.match.job_match_levels
    code = (desired.work24_code or "").strip()
    if not code or not (job.code or job.middle):
        return None
    if job.code and code == job.code:
        return levels.exact
    if job.middle and code.startswith(job.middle):
        return levels.same_middle
    if job.major and code.startswith(job.major):
        return levels.same_major
    return 0.0


def _ncs_prefix(code: str) -> str | None:
    """공고의 NCS 코드에서 알 수 있는 앞자리. 8자리 NCS는 그대로, 잡알리오 R6000NN은 대분류 NN만."""
    code = (code or "").strip()
    alio = _ALIO_NCS.match(code)
    if alio:
        return alio.group(1)
    return code if _NCS_DIGITS.match(code) else None


def _ncs_prefixes(job: Job) -> list[str]:
    return [p for p in (_ncs_prefix(c) for c in job.ncs_codes) if p]


def ncs_match_value(config: OpportunityConfig, desired_ncs: str | None, job: Job) -> float | None:
    """NCS 코드 비교. 8자리가 같으면 exact, 앞 4자리 sameMiddle, 앞 2자리 sameMajor.

    공고 분류가 여러 개면 가장 높은 값을 쓴다. 공고에 대분류 분류만 있으면(잡알리오) 대분류 일치를
    sameMajorCategoryOnly로 본다. 더 잘게 비교할 정보가 공고에 없어서다 (B-D07).
    희망 직무 NCS 코드나 공고 NCS 코드가 없으면 None.
    """
    levels = config.match.job_match_levels
    mine = (desired_ncs or "").strip()
    prefixes = _ncs_prefixes(job)
    if len(mine) != NCS_FULL or not mine.isdigit() or not prefixes:
        return None
    major = levels.same_major_category_only if _category_only(job) else levels.same_major
    best = 0.0
    for prefix in prefixes:
        if len(prefix) == NCS_FULL and prefix == mine:
            return levels.exact
        if len(prefix) >= NCS_MIDDLE and prefix[:NCS_MIDDLE] == mine[:NCS_MIDDLE]:
            best = max(best, levels.same_middle)
        elif prefix[:NCS_MAJOR] == mine[:NCS_MAJOR]:
            best = max(best, major)
    return best


def _category_only(job: Job) -> bool:
    """고용24 코드도 8자리 NCS도 없고 잡알리오 대분류 코드만 있는 공고. 이름은 NCS 대분류 이름이다."""
    prefixes = _ncs_prefixes(job)
    return not (job.code or job.middle) and bool(prefixes) and all(len(p) == NCS_MAJOR for p in prefixes)


def _name_match(config: OpportunityConfig, desired: DesiredJob, job: Job) -> tuple[float | None, str]:
    """이름 포함 관계. 공고 이름이 NCS 대분류 이름뿐이면 겹쳐도 같은 분야(sameMajorCategoryOnly)까지만 본다."""
    levels = config.match.job_match_levels
    mine, theirs = _norm(desired.name), _norm(job.name)
    if not mine or not theirs:
        return None, BASIS_NAME
    hit = mine in theirs or theirs in mine
    if _category_only(job):
        return (levels.same_major_category_only if hit else 0.0), BASIS_NCS_MAJOR_NAME
    return (levels.exact if hit else 0.0), BASIS_NAME


def _job_match_one(config: OpportunityConfig, desired: DesiredJob, job: Job) -> tuple[float | None, str | None]:
    """고용24 코드(없으면 이름) 비교와 NCS 비교 가운데 높은 값. 같으면 고용24·이름 쪽 근거를 쓴다."""
    value, basis = _work24_match(config, desired, job), BASIS_WORK24
    if value is None:
        value, basis = _name_match(config, desired, job)
    ncs = ncs_match_value(config, desired.ncs_code, job)
    if ncs is not None and (value is None or ncs > value):
        return ncs, (BASIS_NCS_MAJOR if _category_only(job) else BASIS_NCS)
    return value, (basis if value is not None else None)


def job_match_detail(config: OpportunityConfig, profile: BasicProfile, job: Job) -> tuple[float | None, str | None]:
    """희망 직무가 여러 개면 가장 높은 값과 그 근거. 비교할 정보가 전혀 없으면 (None, None)."""
    best: tuple[float | None, str | None] = (None, None)
    for desired in profile.desired_jobs:
        value, basis = _job_match_one(config, desired, job)
        if value is not None and (best[0] is None or value > best[0]):
            best = (value, basis)
    return best


def job_match_value(config: OpportunityConfig, profile: BasicProfile, job: Job) -> float | None:
    """희망 직무가 여러 개면 가장 높은 값. 비교할 정보가 없으면 None."""
    return job_match_detail(config, profile, job)[0]


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
    jm, basis = job_match_detail(config, profile, posting.job)
    cs = content_sim_value(config, content_similarity)
    ro = required_ratio(eligibility, config.match.unknown_condition_value) if eligibility is not None else None
    po = preferred_ok_value(profile, posting)
    measured = [(weight, value) for weight, value in
                ((w.job_match, jm), (w.content_sim, cs), (w.required_ok, ro), (w.preferred_ok, po))
                if value is not None]
    total = sum(weight for weight, _ in measured)
    score = sum(weight * value for weight, value in measured) / total if total else 0.0
    return MatchBreakdown(score=score, job_match=jm, job_basis=basis, content_sim=cs, required_ok=ro,
                          preferred_ok=po)


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


# ---------------------------------------------------------------- 근무지 (대안도 쓴다)
def is_overseas_posting(posting: PostingLatest) -> bool:
    """해외 근무 공고. 부산도 수도권도 아니다."""
    return posting.is_overseas or regions.is_overseas(posting.work_region)


def is_busan_posting(config: OpportunityConfig, posting: PostingLatest) -> bool:
    """근무지가 부산으로 확인된 국내 공고. 부산 가산점과 부산 대안 후보는 이것만 본다."""
    return not is_overseas_posting(posting) and regions.is_busan(config, posting.work_region)


def is_capital_posting(config: OpportunityConfig, posting: PostingLatest) -> bool:
    return not is_overseas_posting(posting) and regions.is_capital_area(config, posting.work_region)


# ---------------------------------------------------------------- 벡터 도우미 (대안·상세도 쓴다)
def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def profile_vector(deps: Deps, profile: BasicProfile, query_terms: Sequence[str] | None = None) -> list[float]:
    """프로필 글로 질의 벡터를 만든다. query_terms(이력서 역량 이름 등)는 질의 글에만 덧붙인다."""
    text = profile_text(profile)
    terms = [t.strip() for t in (query_terms or []) if t and t.strip()]
    if terms:
        text = f"{text} | {', '.join(terms)}"
    return deps.embedder.embed(text, kind="query")


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
    if region in (REGION_ALL, REGION_BUSAN, REGION_CAPITAL, REGION_OVERSEAS) or region in regions.SIDO_NAMES:
        return
    raise invalid_input("region 값이 올바르지 않아요.", field="region")


def _region_sidos(config: OpportunityConfig, region: str) -> list[str] | None:
    """region을 시·도 목록으로. OVERSEAS는 시·도가 없어 빈 목록이다."""
    return [] if region == REGION_OVERSEAS else regions.region_sidos(config, region)


def _in_region(posting: PostingLatest, region: str, sidos: list[str] | None) -> bool:
    """ALL이면 해외 공고도 그대로 섞는다. OVERSEAS는 해외 공고만, 시·도 필터는 국내 공고만 남긴다."""
    if region == REGION_OVERSEAS:
        return is_overseas_posting(posting)
    if sidos is None:
        return True
    return (not is_overseas_posting(posting) and not posting.work_region.unknown
            and posting.work_region.sido in sidos)


def _job_code_ok(posting: PostingLatest, codes: list[str] | None) -> bool:
    """요청한 직종 코드로 거른다. 중분류·대분류 코드를 넣으면 그 아래 공고를 모두 남긴다."""
    if not codes:
        return True
    job = posting.job
    return any(job.code and job.code.startswith(code) or code in (job.middle, job.major) for code in codes)


def _keyword_hit(keyword: str | None, texts: Sequence[str | None]) -> bool:
    """검색어가 제목·기관·직무 이름 가운데 하나에 들어 있는지 (대소문자 무시)."""
    if not keyword or not keyword.strip():
        return True
    needle = keyword.strip().lower()
    return any(needle in (text or "").lower() for text in texts)


def _keyword_ok(posting: PostingLatest, keyword: str | None) -> bool:
    return _keyword_hit(keyword, (posting.title, posting.organization, posting.job.name))


def is_team_data(posting: PostingLatest) -> bool:
    """팀이 넣어 둔 공고인지. 지금은 시연용(sourceType=DEMO)만이다. 크롤링 데이터를 넣으면 여기 한 곳만 고친다."""
    return posting.is_sample


def _scope_ok(posting: PostingLatest, scope: str) -> bool:
    if scope == SCOPE_OFFICIAL:
        return not is_team_data(posting)
    if scope == SCOPE_TEAM:
        return is_team_data(posting)
    return True


def _organization_hit(organization: str | None, name: str | None) -> bool:
    """기관·회사 이름에 들어 있는지. 대소문자·공백·가운뎃점은 무시한다 (개발계획서4 §9)."""
    needle = _norm(organization)
    return not needle or needle in _norm(name)


def _organization_ok(posting: PostingLatest, organization: str | None) -> bool:
    return _organization_hit(organization, posting.organization)


def _name_candidates(deps: Deps, as_of: datetime, keyword: str | None, organization: str | None) -> list[str]:
    """검색어·회사 조건에 맞는 진행 중 공고 ID를 이름 색인에서 찾는다 (B-D08). 조건이 없으면 색인을 읽지 않는다.

    맞는 방식은 `_keyword_ok`·`_organization_ok`와 같다. 상한을 넘으면 기관·회사 이름이 맞는 공고를 먼저 둔다.
    """
    if not (keyword or "").strip() and not (organization or "").strip():
        return []
    needle = (keyword or "").strip().lower()
    rows = [n for n in deps.catalog.posting_names()
            if not clock.is_expired(n.closes_at, as_of)
            and _keyword_hit(keyword, (n.title, n.organization, n.job_name))
            and _organization_hit(organization, n.organization)]
    rows.sort(key=lambda n: (bool(needle) and needle not in n.organization.lower(), n.job_posting_id))
    return [n.job_posting_id for n in rows[:NAME_MATCH_LIMIT]]


def _salary_ok(posting: PostingLatest, min_salary: int | None) -> bool:
    """공개된 급여의 상한(없으면 하한)이 min_salary보다 낮으면 뺀다. 비공개·미확인 급여는 남긴다 (미확인 ≠ 미달)."""
    if min_salary is None:
        return True
    salary = posting.salary
    top = salary.max if salary.max is not None else salary.min
    if not salary.disclosed or top is None:
        return True
    return top >= min_salary


# 요청한 경력 구분마다 남길 공고 값. 무관(ANY)과 미확인(UNKNOWN)은 어느 쪽이든 남긴다
_CAREER_KEEP = {CareerType.NEW: {CareerType.NEW, CareerType.ANY, CareerType.UNKNOWN},
                CareerType.EXPERIENCED: {CareerType.EXPERIENCED, CareerType.ANY, CareerType.UNKNOWN}}


def _career_ok(posting: PostingLatest, career_type: CareerType | None) -> bool:
    keep = _CAREER_KEEP.get(career_type) if career_type is not None else None
    return keep is None or posting.career_type in keep


def _check_conditions(min_salary: int | None, career_type: str | CareerType | None) -> CareerType | None:
    if min_salary is not None and (isinstance(min_salary, bool) or not isinstance(min_salary, int) or min_salary < 0):
        raise invalid_input("minSalary는 0 이상의 정수(만 원/년)여야 해요.", field="minSalary")
    if career_type is None:
        return None
    try:
        return CareerType(str(career_type).strip().upper())
    except ValueError:
        raise invalid_input("careerType 값이 올바르지 않아요.", field="careerType") from None


def with_job_name(profile: BasicProfile, job_name: str | None) -> BasicProfile:
    """이번 검색에만 쓸 희망 직무. 저장된 희망 직무와 이름이 같으면 저장된 항목(코드 포함)을 쓴다. 저장하지 않는다."""
    name = (job_name or "").strip()
    if not name:
        return profile
    same = [job for job in profile.desired_jobs if _norm(job.name) == _norm(name)]
    return profile.model_copy(update={"desired_jobs": same[:1] or [DesiredJob(name=name)]})


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
                and is_busan_posting(cfg, latest) and is_open(latest, as_of)):
            count += 1
    return min(count, cfg.alternatives.view_max)


def _card(deps: Deps, row: dict, as_of: datetime, alt_count: int | None, profile: BasicProfile) -> PostingCard:
    cfg, posting, match = deps.config, row["posting"], row["match"]
    commute = facts.commute_minutes(deps.local_life, profile, posting.work_region)
    distance = facts.distance_km(deps.local_life, profile, posting.work_region)
    talent = facts.card_regional_talent(cfg, profile, posting)
    fact_list = facts.compact([facts.job_fact(cfg, match.job_match, basis=match.job_basis),
                               facts.FACT_REGIONAL_TALENT_CARD if talent == RegionalTalentStatus.LIKELY else None,
                               facts.overseas_fact(posting.work_region) if is_overseas_posting(posting) else None,
                               facts.commute_fact(commute) or facts.distance_fact(distance),  # 통근 시간이 없으면 거리
                               *facts.eligibility_facts(row["eligibility"]),
                               facts.deadline_fact(posting.closes_at, as_of)])
    return PostingCard(
        job_posting_id=posting.job_posting_id, title=posting.title, organization=posting.organization,
        org_type=posting.org_type, work_region=posting.work_region,
        is_busan=is_busan_posting(cfg, posting), is_capital_area=is_capital_posting(cfg, posting), job=posting.job,
        closes_at=posting.closes_at, rolling=posting.rolling, salary=posting.salary,
        career_type=posting.career_type, match_score=round(match.score, facts.SCORE_DIGITS), match_level=match_level(cfg, match.score),
        rank_score=round(row["rank"], facts.SCORE_DIGITS), eligibility=row["eligibility"],
        badges=facts.valid_badges(posting.badges), facts=fact_list, busan_alternatives_count=alt_count,
        commute_minutes=commute, distance_km=distance, regional_talent=talent, is_sample=posting.is_sample,
    )


def _few_busan_jobs(cfg: OpportunityConfig, rows: list[dict]) -> bool:
    """같은 중분류 이상으로 맞는 부산 공고가 하나도 없으면 True."""
    need = cfg.match.job_match_levels.same_middle
    return not any(is_busan_posting(cfg, r["posting"]) and (r["match"].job_match or 0) >= need
                   for r in rows)


def _add_regional_candidates(deps: Deps, ctx: UserContext, vector: Sequence[float],
                             similarity: dict[str, float | None]) -> None:
    """지역 조건 색인에서 사용자에게 맞을 수 있는 공고를 후보에 더한다.

    벡터 상위 후보는 희망 직무와 가까운 공고만 모아, 지역 조건이 맞는 공고가 빠질 수 있다 (2026-11-21, 열린 공고 3,000건 중
    부산 학교 기준으로 맞는 공고 대부분이 후보 밖이었다). 더한 공고의 유사도는 이름 색인 후보와 같이 `similarities`로 잰다.
    """
    cfg = deps.config
    ids = [i for i in deps.catalog.list_regional_index(closes_from=clock.day(ctx.as_of)) if i not in similarity]
    if not ids:
        return
    latest = deps.catalog.batch_get_latest(ids)
    keep = [i for i, p in latest.items()
            if facts.card_regional_talent(cfg, ctx.profile, p) == RegionalTalentStatus.LIKELY]
    found = deps.vectors.similarities(vector, keep) if keep else {}
    similarity.update({i: found.get(i) for i in keep})  # 벡터가 아직 없는 공고는 None (내용 유사도를 빼고 계산)


def search_postings(deps: Deps, user_id: str, *, region: str = "ALL", sort: Sort | None = None,
                    job_codes: list[str] | None = None, keyword: str | None = None, cursor: str | None = None,
                    limit: int = 20, as_of: str | date | datetime | None = None, job_name: str | None = None,
                    query_terms: Sequence[str] | None = None, min_salary: int | None = None,
                    career_type: str | CareerType | None = None, organization: str | None = None,
                    scope: str | None = None, regional_talent: bool = False) -> FeedResponse:
    """전국 공고를 찾아 정렬한다. 후보는 벡터 질의 두 번(부산, 전국)으로 모으고, 지역을 골랐으면 그 지역 질의를 더한다.
    검색어나 회사 조건이 있으면 이름 색인에서 찾은 공고도 더한다 (B-D08). 이 경로에 LLM은 없다.

    sort가 None이면 사용자 설정을 쓴다. BUSAN_FIRST와 MATCH는 공고 집합이 같고 순서만 다르다 (T-01).
    마감된 공고는 뺀다 (T-21). 수도권 공고에는 busanAlternativesCount를 붙인다.
    해외 공고는 부산도 수도권도 아니라 가산점과 busanAlternativesCount가 없다. region=OVERSEAS면 해외 공고만.

    대화 조건 (개발계획서4 §9): job_name은 이번 검색에만 희망 직무로 쓰고 저장하지 않는다. query_terms는 질의 글에만
    넣는다. min_salary(만 원/년)·career_type·organization은 거르기만 하고 적합도·정렬 계산은 그대로다.
    scope는 OFFICIAL(공공 API로 모은 공고만)·TEAM(팀이 넣어 둔 공고만)·ALL(기본, 둘 다)이다 (§9.1).
    regional_talent=True면 공고문의 지역 조건(비수도권·이전지역·권역 인재, 지역 제한, 거주자 우대)이 사용자의 학교
    소재지나 거주지와 맞을 수 있는(LIKELY) 공고만 남긴다. 순서와 점수는 그대로다. 벡터 상위 후보 밖의 공고도 빠지지
    않게 지역 조건 색인(`INDEX#REGIONAL`)에서 후보를 더한다 (`_add_regional_candidates`).
    """
    cfg = deps.config
    region = (region or REGION_ALL).strip().upper()
    _check_region(region)
    if limit < 1:
        raise invalid_input("limit은 1 이상이어야 해요.", field="limit")
    career = _check_conditions(min_salary, career_type)
    scope = (scope or SCOPE_ALL).strip().upper()
    if scope not in SCOPES:
        raise invalid_input("scope 값이 올바르지 않아요.", field="scope", allowed=list(SCOPES))
    offset = _decode_cursor(cursor)
    has_job_name = bool((job_name or "").strip())
    ctx = load_context(deps, user_id, as_of, require_jobs=not has_job_name)
    if has_job_name:
        ctx.profile = with_job_name(ctx.profile, job_name)
    sort = Sort(sort) if sort is not None else ctx.prefs.sort

    # 1. 후보: 부산 필터 질의와 전국 질의를 합친다. 같은 공고는 높은 유사도를 쓴다.
    #    지역을 골랐으면(수도권, 시·도) 그 지역만 찾는 질의를 하나 더 한다. 전국 상위 후보에서 거르기만 하면
    #    공고가 많을 때 고른 지역 공고가 몇 건밖에 남지 않는다 (수도권 20건을 요청해 9건이 나왔다, 2026-11-21).
    vector = profile_vector(deps, ctx.profile, query_terms)
    top_k = cfg.ranking.candidate_top_k
    sidos = _region_sidos(cfg, region)
    queries = [(top_k.feed, active_filter(ctx.as_of, isBusan=True)), (top_k.feed, active_filter(ctx.as_of))]
    if sidos:
        queries.append((top_k.feed, active_filter(ctx.as_of, sido={"$in": sidos})))
    similarity: dict[str, float | None] = {}
    for hits in (deps.vectors.query(vector, top_k=k, filter=f) for k, f in queries):
        for hit in hits:
            similarity[hit.key] = max(hit.similarity, similarity.get(hit.key, hit.similarity))
    #    검색어나 회사 조건이 있으면 이름 색인에서 찾은 진행 중 공고를 더한다 (B-D08). 벡터 후보는 프로필과 비슷한
    #    공고라서, 프로필과 먼 회사의 공고는 거르기 전에 이미 빠져 있다 ("삼성"을 찾으면 0건이었다, 2026-11-21).
    #    더한 공고의 유사도는 벡터 질의와 같은 값으로 계산해서, 후보로 들어온 길에 따라 적합도가 달라지지 않게 한다.
    #    벡터가 아직 없는 공고는 None이다 (내용 유사도를 빼고 계산한다).
    named = [pid for pid in _name_candidates(deps, ctx.as_of, keyword, organization) if pid not in similarity]
    if named:
        found = deps.vectors.similarities(vector, named)
        similarity.update({pid: found.get(pid) for pid in named})
    #    지역 혜택 필터를 켜면 지역 조건 색인에서 사용자에게 맞을 수 있는 공고를 더한다 (B-D09).
    if regional_talent:
        _add_regional_candidates(deps, ctx, vector, similarity)
    latest_by_id = deps.catalog.batch_get_latest(list(similarity))

    # 2. 거르기: 마감, 지역, 직종 코드, 검색어, 대화 조건(기관, 최소 연봉, 경력 구분)
    rows = []
    for pid, posting in latest_by_id.items():
        if not (is_open(posting, ctx.as_of) and _in_region(posting, region, sidos)
                and _job_code_ok(posting, job_codes) and _keyword_ok(posting, keyword)
                and _organization_ok(posting, organization) and _salary_ok(posting, min_salary)
                and _career_ok(posting, career) and _scope_ok(posting, scope)
                and (not regional_talent
                     or facts.card_regional_talent(cfg, ctx.profile, posting) == RegionalTalentStatus.LIKELY)):
            continue
        match, result = score_posting(deps, ctx, posting, similarity[pid])
        rank = rank_score(cfg, match.score, is_busan=is_busan_posting(cfg, posting), sort=sort)
        rows.append({"posting": posting, "match": match, "eligibility": result, "rank": rank})

    # 3. 정렬과 쪽 나누기
    rows.sort(key=_sort_key(sort))
    page = rows[offset:offset + limit]
    next_cursor = _encode_cursor(offset + limit) if offset + limit < len(rows) else None

    # 4. 수도권 카드의 부산 대안 수. ALTS 후보를 한 번에 읽는다.
    capital = [r["posting"] for r in page if is_capital_posting(cfg, r["posting"])]
    alts_by_id = {p.job_posting_id: deps.catalog.get_alts(p.job_posting_id) for p in capital}
    cand_ids = {c.job_posting_id for alts in alts_by_id.values() if alts for c in alts.candidates}
    cand_latest = deps.catalog.batch_get_latest(sorted(cand_ids)) if cand_ids else {}
    cards = []
    for row in page:
        posting = row["posting"]
        count = None
        if posting.job_posting_id in alts_by_id:
            count = busan_alternatives_count(cfg, alts_by_id[posting.job_posting_id], ctx.as_of, cand_latest)
        cards.append(_card(deps, row, ctx.as_of, count, ctx.profile))

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
