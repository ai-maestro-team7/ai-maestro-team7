"""근거 사실과 배지 거르기 도우미. 피드·대안·상세가 같은 규칙으로 사실 목록을 만든다.

사실 목록은 문장이 아니라 짧은 사실이다. 출처·기준일이 없는 배지는 여기서 뺀다 (T-08).
"""

import math

from datetime import datetime

from ..config import OpportunityConfig
from ..models.api import EligibilityResult, RegionalTalentView
from ..models.enums import (
    BadgeType,
    CheonggeulType,
    ConditionResult,
    OrgType,
    RegionalBenefitKind,
    RegionalTalentStatus,
)
from ..models.posting import Badge, PostingLatest, RegionalCondition, Salary, WorkRegion
from ..models.profile import BasicProfile
from ..models.region import LocalLifeData
from . import clock, copy_rules
from .regions import same_sido, sido_name, sigungu_name

SCORE_DIGITS = 4       # 응답에 싣는 점수의 소수 자리 (표시용)
SIMILARITY_DIGITS = 2  # 사실 목록에 쓰는 유사도 자리

FACT_JOB_EXACT = "희망 직무와 같은 직종"
FACT_JOB_MIDDLE = "희망 직무와 가까운 직종 (같은 중분류)"
FACT_JOB_MAJOR = "희망 직무와 같은 대분류 직종"
FACT_JOB_NCS_EXACT = "희망 직무와 같은 NCS 세분류"
FACT_JOB_NCS_MIDDLE = "희망 직무와 가까운 분야 (NCS 중분류)"
FACT_JOB_NCS_MAJOR = "희망 직무와 같은 분야 (NCS 대분류)"
FACT_OVERSEAS_NO_COUNTRY = "해외 근무 · 국가는 공고문 확인"
FACT_REQUIRED = "필수 조건 {total}개 중 {met}개 충족"
FACT_UNKNOWN = "확인이 필요한 조건 {count}개"
FACT_SIMILAR = "하는 일이 비슷함 (유사도 {similarity})"
FACT_SALARY_DISCLOSED = "급여가 공고에 적혀 있음"
FACT_REGIONAL_TALENT = "{label} · 지역인재 전형 대상일 수 있음"
FACT_REGIONAL_TALENT_CARD = "지역 혜택 대상일 수 있음 · 공고문 확인"

GRADUATION_LABEL = {"GRADUATING": "졸업 예정", "GRADUATED": "졸업", "ENROLLED": "재학 중"}
GRADUATION_DEFAULT = "출신"

PUBLIC_ORG_TYPES = (OrgType.PUBLIC_INSTITUTION, OrgType.LOCAL_PUBLIC)


# ---------------------------------------------------------------- 배지
def has_source(badge: Badge) -> bool:
    return bool(badge.source) and bool(badge.as_of)


def valid_badges(badges: list[Badge]) -> list[Badge]:
    """출처와 기준일이 둘 다 있는 배지만 남긴다."""
    return [b for b in badges if has_source(b)]


def has_cheonggeul(badges: list[Badge], kind: CheonggeulType) -> bool:
    return any(b.type == BadgeType.CHEONGKKEUL and b.cheonggeul_type == kind for b in valid_badges(badges))


def is_relocated(badges: list[Badge]) -> bool:
    """부산 이전 공공기관 배지가 출처와 함께 붙어 있는지."""
    return any(b.type == BadgeType.RELOCATED_INSTITUTION for b in valid_badges(badges))


def salary_disclosed(salary: Salary) -> bool:
    return salary.disclosed and (salary.min is not None or salary.max is not None)


# ---------------------------------------------------------------- 사실
# 직무 일치의 근거 (`ranking.MatchBreakdown.job_basis`)
BASIS_WORK24, BASIS_NAME, BASIS_NCS = "WORK24", "NAME", "NCS"
BASIS_NCS_MAJOR_NAME = "NCS_MAJOR_NAME"  # NCS 대분류 이름과 희망 직무 이름이 겹침
BASIS_NCS_MAJOR = "NCS_MAJOR"  # 공고에 NCS 대분류 분류만 있고 그 대분류가 같음
BASIS_NCS_KINDS = (BASIS_NCS, BASIS_NCS_MAJOR_NAME, BASIS_NCS_MAJOR)
BASIS_NCS_MAJOR_ONLY = (BASIS_NCS_MAJOR_NAME, BASIS_NCS_MAJOR)  # 값이 몇이든 "대분류"라고만 말한다


def job_fact(config: OpportunityConfig, job_match: float | None, *, basis: str | None = None) -> str | None:
    """직무 일치 사실. NCS로 맞춘 값은 "직종"이라 하지 않고 NCS 분류 단계를 그대로 말한다.

    basis는 `MatchBreakdown.job_basis`. 없으면 고용24 직종 문구를 쓴다.
    """
    levels = config.match.job_match_levels
    if job_match is None or job_match <= 0:
        return None
    if basis in BASIS_NCS_MAJOR_ONLY:  # 대분류만 아는 공고는 점수(sameMajorCategoryOnly)와 상관없이 대분류라고 말한다
        return FACT_JOB_NCS_MAJOR
    ncs = basis in BASIS_NCS_KINDS
    if job_match >= levels.exact:
        return FACT_JOB_NCS_EXACT if ncs else FACT_JOB_EXACT
    if job_match >= levels.same_middle:
        return FACT_JOB_NCS_MIDDLE if ncs else FACT_JOB_MIDDLE
    return FACT_JOB_NCS_MAJOR if ncs else FACT_JOB_MAJOR


def overseas_fact(region: WorkRegion) -> str:
    """해외 근무 · {국가}. 국가 이름이 원문에 없으면 공고문 확인으로 둔다."""
    country = (region.country or "").strip()
    return copy_rules.OVERSEAS_LABEL.format(country=country) if country else FACT_OVERSEAS_NO_COUNTRY


def commute_minutes(local_life: LocalLifeData, profile: BasicProfile, region: WorkRegion) -> int | None:
    """거주 시군구 → 근무 시군구 대중교통 분. 표에 값이 있고 출처·기준일이 있을 때만. 추정하지 않는다."""
    home, work = profile.residence_sigungu, region.sigungu
    if not home or not work or region.unknown or region.overseas:
        return None
    if not (local_life.commute_source and local_life.commute_as_of):
        return None
    return local_life.commute_minutes.get(f"{home}>{work}")


def distance_km(local_life: LocalLifeData, profile: BasicProfile, region: WorkRegion) -> float | None:
    """거주 구청 → 근무지 구청 직선거리 (km, 소수 한 자리). 두 구청 위치와 출처·기준일이 있을 때만. 같은 구면 None."""
    home, work = profile.residence_sigungu, region.sigungu
    if not home or not work or home == work or region.unknown or region.overseas:
        return None
    if not (local_life.gu_offices_source and local_life.gu_offices_as_of):
        return None
    a, b = local_life.gu_offices.get(home), local_life.gu_offices.get(work)
    if a is None or b is None:
        return None
    # 하버사인 공식. 지구 반지름 6371km
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlng = lat2 - lat1, math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return round(2 * 6371.0 * math.asin(math.sqrt(h)), 1)


def distance_fact(km: float | None) -> str | None:
    return copy_rules.DISTANCE_LABEL.format(km=f"{km:g}") if km is not None else None


def commute_fact(minutes: int | None) -> str | None:
    return copy_rules.COMMUTE_LABEL.format(minutes=minutes) if minutes is not None else None


def eligibility_facts(result: EligibilityResult | None) -> list[str]:
    if result is None or not result.conditions:
        return []
    met = sum(1 for c in result.conditions if c.result == ConditionResult.MET)
    unknown = sum(1 for c in result.conditions if c.result == ConditionResult.UNKNOWN)
    facts = [FACT_REQUIRED.format(total=len(result.conditions), met=met)]
    if unknown:
        facts.append(FACT_UNKNOWN.format(count=unknown))
    return facts


def deadline_fact(closes_at: str | None, as_of: datetime) -> str | None:
    return copy_rules.deadline_label(clock.d_day(closes_at, as_of))


def similarity_fact(similarity: float) -> str:
    return FACT_SIMILAR.format(similarity=f"{similarity:.{SIMILARITY_DIGITS}f}")


def badge_facts(badges: list[Badge], talent: RegionalTalentView | None) -> list[str]:
    """출처 있는 배지의 이름. 이전기관이고 지역인재 LIKELY면 그 사실을 붙인다."""
    facts = []
    for badge in valid_badges(badges):
        if (badge.type == BadgeType.RELOCATED_INSTITUTION and talent is not None
                and talent.status == RegionalTalentStatus.LIKELY):
            facts.append(FACT_REGIONAL_TALENT.format(label=badge.label))
        else:
            facts.append(badge.label)
    return facts


def compact(items: list[str | None]) -> list[str]:
    """빈 값과 중복을 빼고 순서를 지킨다."""
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ---------------------------------------------------------------- 지역인재·지역 조건
def _school_text(profile: BasicProfile, template: str, named: str) -> str:
    status = GRADUATION_LABEL.get(profile.graduation_status or "", GRADUATION_DEFAULT)
    school = sido_name(profile.university_region) or ""
    name = (profile.school_name or "").strip()
    return named.format(name=name, school=school, status=status) if name else template.format(school=school,
                                                                                               status=status)


def _home_text(profile: BasicProfile) -> str:
    return " ".join(x for x in (sido_name(profile.residence_sido), sigungu_name(profile.residence_sigungu)) if x)


def _same_sigungu(a: str, b: str) -> bool:
    """"기장군"과 "기장", "구미시"와 "구미"를 같게 본다."""
    trim = (lambda x: x[:-1] if len(x) > 2 and x[-1] in "시군구" else x)
    return trim(a.strip()) == trim(b.strip())


def _school_met(config: OpportunityConfig, profile: BasicProfile, c: RegionalCondition) -> bool | None:
    """학교 소재지 기준. 학교 소재지를 모르거나 조건 지역을 모르면 None."""
    school = profile.university_region
    if c.kind == RegionalBenefitKind.NON_CAPITAL:
        return None if school is None else not any(same_sido(school, s) for s in config.data.capital_area_sido)
    if school is None or c.sido is None:
        return None
    return same_sido(school, c.sido)


def _home_met(profile: BasicProfile, c: RegionalCondition) -> bool | None:
    """거주지 기준. 시·군·구까지 적힌 조건은 구·군을 아는 거주지(부산)만 맞춰 본다."""
    if profile.residence_sido is None or c.sido is None:
        return None
    if not same_sido(profile.residence_sido, c.sido):
        return False
    if not c.sigungu:
        return True
    home = sigungu_name(profile.residence_sigungu)
    return None if home is None else _same_sigungu(home, c.sigungu)


def condition_met(config: OpportunityConfig, profile: BasicProfile,
                  c: RegionalCondition) -> tuple[bool | None, str | None]:
    """(맞는지, 무엇으로 맞았는지 "school"·"home"). 맞는지 모르면 (None, None)."""
    kind = c.kind
    if kind in (RegionalBenefitKind.NON_CAPITAL, RegionalBenefitKind.SCHOOL):
        met = _school_met(config, profile, c)
        return met, ("school" if met else None)
    if kind == RegionalBenefitKind.RESIDENCE:
        met = _home_met(profile, c)
        return met, ("home" if met else None)
    if kind == RegionalBenefitKind.SCHOOL_OR_RESIDENCE:
        school, home = _school_met(config, profile, c), _home_met(profile, c)
        if school:
            return True, "school"
        if home:
            return True, "home"
        return (None if school is None or home is None else False), None
    return None, None  # UNKNOWN


def _met_message(profile: BasicProfile, c: RegionalCondition, via: str) -> str:
    if via == "home":
        return copy_rules.REGIONAL_RESIDENCE.format(home=_home_text(profile))
    if c.kind == RegionalBenefitKind.NON_CAPITAL:
        return _school_text(profile, copy_rules.REGIONAL_NON_CAPITAL, copy_rules.REGIONAL_NON_CAPITAL_NAMED)
    if c.kind == RegionalBenefitKind.SCHOOL_OR_RESIDENCE:
        return _school_text(profile, copy_rules.REGIONAL_LIMIT_SCHOOL, copy_rules.REGIONAL_LIMIT_SCHOOL_NAMED)
    return _school_text(profile, copy_rules.REGIONAL_TALENT_LIKELY, copy_rules.REGIONAL_TALENT_LIKELY_NAMED)


def posting_conditions(config: OpportunityConfig, posting: PostingLatest, relocated: bool) -> list[RegionalCondition]:
    """공고의 지역 조건. 조건 목록이 없는 예전 판정(LIKELY)은 부산 이전기관이면 부산 학교, 아니면 모름으로 본다."""
    talent = posting.regional_talent
    if talent is None or talent.status != RegionalTalentStatus.LIKELY:
        return []
    if talent.conditions:
        return list(talent.conditions)
    if relocated:
        return [RegionalCondition(kind=RegionalBenefitKind.SCHOOL, sido=config.data.busan_sido)]
    return [RegionalCondition(kind=RegionalBenefitKind.UNKNOWN)]


def regional_talent_view(config: OpportunityConfig, profile: BasicProfile, posting: PostingLatest, *,
                         company_regional_talent: bool = False) -> RegionalTalentView:
    """공고의 지역 조건(비수도권·이전지역·권역 인재, 지역 제한, 거주자 우대)이 사용자에게 맞는지.

    - 학교 소재지나 거주지로 맞는 조건이 하나라도 있으면 LIKELY ("…대상일 수 있어요 · 공고문 확인")
    - 맞는지 정할 수 없으면 CHECK_NEEDED (지역을 적지 않았거나, 사용자의 학교·거주 지역을 모름)
    - 조건이 있지만 학교·거주 지역으로 보면 맞지 않으면 NOT_APPLICABLE. 화면에는 띄우지 않는다
    단정하지 않는다. 문구는 늘 "공고문 확인"으로 끝난다.
    """
    talent = posting.regional_talent
    relocated = is_relocated(posting.badges) or company_regional_talent
    if talent is None or talent.status == RegionalTalentStatus.NOT_APPLICABLE:
        if relocated:
            return RegionalTalentView(status=RegionalTalentStatus.CHECK_NEEDED, message=copy_rules.REGIONAL_TALENT_CHECK)
        return RegionalTalentView(status=RegionalTalentStatus.NOT_APPLICABLE, basis=talent.basis if talent else None)
    if talent.status == RegionalTalentStatus.CHECK_NEEDED:
        return RegionalTalentView(status=RegionalTalentStatus.CHECK_NEEDED, basis=talent.basis,
                                  message=copy_rules.REGIONAL_TALENT_CHECK)
    unknown = False
    for c in posting_conditions(config, posting, relocated):
        met, via = condition_met(config, profile, c)
        if met:
            return RegionalTalentView(status=RegionalTalentStatus.LIKELY, basis=talent.basis,
                                      message=_met_message(profile, c, via))
        unknown = unknown or met is None
    if unknown:
        return RegionalTalentView(status=RegionalTalentStatus.CHECK_NEEDED, basis=talent.basis,
                                  message=copy_rules.REGIONAL_TALENT_CHECK_NOTICE)
    return RegionalTalentView(status=RegionalTalentStatus.NOT_APPLICABLE, basis=talent.basis)


def card_regional_talent(config: OpportunityConfig, profile: BasicProfile,
                         posting: PostingLatest) -> RegionalTalentStatus | None:
    """피드 카드용. 지역 조건이 사용자에게 맞을 수 있으면 LIKELY, 맞는지 모르면 CHECK_NEEDED, 아니면 None."""
    view = regional_talent_view(config, profile, posting)
    return None if view.status == RegionalTalentStatus.NOT_APPLICABLE else view.status


def needs_regional_view(posting: PostingLatest, company_regional_talent: bool = False) -> bool:
    """상세 화면에 지역인재 칸을 보여 줄 공고인지. 공공기관, 이전기관, 공고 쪽 판정이 있는 공고."""
    return (posting.regional_talent is not None or posting.org_type in PUBLIC_ORG_TYPES
            or is_relocated(posting.badges) or company_regional_talent)
