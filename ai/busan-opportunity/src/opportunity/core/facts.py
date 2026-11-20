"""근거 사실과 배지 거르기 도우미. 피드·대안·상세가 같은 규칙으로 사실 목록을 만든다.

사실 목록은 문장이 아니라 짧은 사실이다. 출처·기준일이 없는 배지는 여기서 뺀다 (T-08).
"""

from datetime import datetime

from ..config import OpportunityConfig
from ..models.api import EligibilityResult, RegionalTalentView
from ..models.enums import BadgeType, CheonggeulType, ConditionResult, OrgType, RegionalTalentStatus
from ..models.posting import Badge, PostingLatest, Salary
from ..models.profile import BasicProfile
from . import clock, copy_rules
from .regions import sido_name

SCORE_DIGITS = 4       # 응답에 싣는 점수의 소수 자리 (표시용)
SIMILARITY_DIGITS = 2  # 사실 목록에 쓰는 유사도 자리

FACT_JOB_EXACT = "희망 직무와 같은 직종"
FACT_JOB_MIDDLE = "희망 직무와 가까운 직종 (같은 중분류)"
FACT_JOB_MAJOR = "희망 직무와 같은 대분류 직종"
FACT_REQUIRED = "필수 조건 {total}개 중 {met}개 충족"
FACT_UNKNOWN = "확인이 필요한 조건 {count}개"
FACT_SIMILAR = "하는 일이 비슷함 (유사도 {similarity})"
FACT_SALARY_DISCLOSED = "급여가 공고에 적혀 있음"
FACT_REGIONAL_TALENT = "{label} · 지역인재 전형 대상일 수 있음"

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
def job_fact(config: OpportunityConfig, job_match: float | None) -> str | None:
    levels = config.match.job_match_levels
    if job_match is None or job_match <= 0:
        return None
    if job_match >= levels.exact:
        return FACT_JOB_EXACT
    if job_match >= levels.same_middle:
        return FACT_JOB_MIDDLE
    return FACT_JOB_MAJOR


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


# ---------------------------------------------------------------- 지역인재
def regional_talent_view(config: OpportunityConfig, profile: BasicProfile, posting: PostingLatest, *,
                         company_regional_talent: bool = False) -> RegionalTalentView:
    """지역인재 전형 해당 가능성. "대상일 수 있어요"는 학교 소재지가 부산일 때만 말한다.

    공고 쪽 판정(LIKELY, CHECK_NEEDED)이 있어도 사용자의 학교 소재지를 모르거나 부산이 아니면
    단정하지 않고 CHECK_NEEDED로 둔다.
    """
    talent = posting.regional_talent
    relocated = is_relocated(posting.badges) or company_regional_talent
    if talent is None:
        if relocated:
            return RegionalTalentView(status=RegionalTalentStatus.CHECK_NEEDED, message=copy_rules.REGIONAL_TALENT_CHECK)
        return RegionalTalentView(status=RegionalTalentStatus.NOT_APPLICABLE)
    if talent.status == RegionalTalentStatus.NOT_APPLICABLE:
        return RegionalTalentView(status=RegionalTalentStatus.NOT_APPLICABLE, basis=talent.basis)
    busan = config.data.busan_sido
    if talent.status == RegionalTalentStatus.LIKELY and profile.university_region == busan:
        status = GRADUATION_LABEL.get(profile.graduation_status or "", GRADUATION_DEFAULT)
        message = copy_rules.REGIONAL_TALENT_LIKELY.format(school=sido_name(busan), status=status)
        return RegionalTalentView(status=RegionalTalentStatus.LIKELY, basis=talent.basis, message=message)
    return RegionalTalentView(status=RegionalTalentStatus.CHECK_NEEDED, basis=talent.basis,
                              message=copy_rules.REGIONAL_TALENT_CHECK)


def needs_regional_view(posting: PostingLatest, company_regional_talent: bool = False) -> bool:
    """상세 화면에 지역인재 칸을 보여 줄 공고인지. 공공기관, 이전기관, 공고 쪽 판정이 있는 공고."""
    return (posting.regional_talent is not None or posting.org_type in PUBLIC_ORG_TYPES
            or is_relocated(posting.badges) or company_regional_talent)
