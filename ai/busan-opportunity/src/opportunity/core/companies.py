"""부산 기업 둘러보기 (DECISIONS.md B-D01). 부산시가 선정한 청끌기업을 회사 정보로만 보여 준다.

- 청끌기업 명단은 채용공고가 아니다. 채용 여부, 직무, 급여, 마감일을 만들지 않는다.
- 카드의 사실(facts)은 시드에 적힌 값과 출처 있는 배지에서만 만든다. "추천", "좋은 회사" 같은 평가 문구는 넣지 않는다.
- 정렬에 쓰는 점수는 응답에 싣지 않는다. 화면에는 고른 기준(`COMPANIES_BASIS`)만 보여 준다.
- LLM을 부르지 않는다.
"""

import re
from datetime import date, datetime

from ..deps import Deps
from ..models.api import CompaniesResponse, CompanyCard
from ..models.enums import BadgeType, CheonggeulType
from ..models.errors import invalid_input
from ..models.posting import Badge, CompanyRecord
from ..models.profile import BasicProfile
from . import copy_rules, facts
from .context import freshness, load_context

# 사실 한 줄 (값은 모두 시드 원문)
FACT_MAIN_PRODUCT = "주력 제품: {value}"
FACT_INDUSTRY = "업종: {value}"
FACT_SIZE = "규모: {value}"
FACT_WORD_OVERLAP = "희망 직무·전공과 겹치는 낱말: {words}"

# 사용자 중요 조건(priorities) → 청끌 유형. STABILITY는 청끌 유형에 대응하는 것이 없어 정렬에 쓰지 않는다
PRIORITY_TO_CHEONGGEUL = {
    "SALARY": CheonggeulType.SALARY,
    "WORK_LIFE": CheonggeulType.WORK_LIFE,
    "GROWTH": CheonggeulType.FUTURE,
}

# 낱말 비교 규칙
# 1. 희망 직무 이름과 전공을 공백·기호(한글·영문·숫자가 아닌 글자)에서 끊어 낱말로 나눈다.
#    예: "사무·회계" → ["사무", "회계"], "데이터 분석" → ["데이터", "분석"]
# 2. 2자 미만인 낱말은 버린다 (한 글자는 아무 데나 걸린다).
# 3. 전공이 "…학"으로 끝나고 3자 이상이면 "학"을 뗀 낱말도 쓴다. 예: "통계학" → "통계", "경영학" → "경영"
# 4. 회사의 업종과 주력 제품도 공백·기호를 지운 뒤, 사용자 낱말이 그 안에 그대로 들어 있으면 겹친다고 본다.
#    한국어 업종 이름은 띄어 쓰지 않은 합성어가 많아("소프트웨어개발") 낱말 단위가 아니라 포함 여부로 본다.
# 5. 영문은 소문자로 맞춘다.
_SPLIT = re.compile(r"[^0-9A-Za-z가-힣]+")
MIN_WORD_LEN = 2
MAJOR_SUFFIX = "학"

# 이름순 정렬에서 빼는 법인 표기. "(주)KTE"와 "㈜저스트컴퍼니"가 표기 때문에 앞으로 몰리지 않게 한다.
# 화면에 보이는 이름은 원문 그대로 둔다
_LEGAL_MARK = re.compile(r"\((주|의|유|사|재|합)\)|㈜|㈔|㈐|주식회사|유한회사")


def _norm(text: str | None) -> str:
    """공백·기호를 지우고 소문자로 맞춘다."""
    return _SPLIT.sub("", text or "").lower()


def _words(text: str | None) -> list[str]:
    return [w.lower() for w in _SPLIT.split(text or "") if len(w) >= MIN_WORD_LEN]


def name_key(name: str) -> str:
    """이름순 정렬 키. 법인 표기와 공백·기호를 지운다."""
    return _norm(_LEGAL_MARK.sub("", name)) or _norm(name)


def user_words(profile: BasicProfile) -> list[str]:
    """희망 직무 이름과 전공에서 비교할 낱말을 뽑는다. 순서를 지키고 중복을 뺀다."""
    out: list[str] = []
    for job in profile.desired_jobs:
        out.extend(_words(job.name))
    for word in _words(profile.major):
        out.append(word)
        if word.endswith(MAJOR_SUFFIX) and len(word) > MIN_WORD_LEN:
            out.append(word[: -len(MAJOR_SUFFIX)])
    return list(dict.fromkeys(out))


def overlap_words(words: list[str], company: CompanyRecord) -> list[str]:
    """회사 업종·주력 제품에 들어 있는 사용자 낱말."""
    haystack = _norm(company.industry) + " " + _norm(company.main_product)
    return [w for w in words if w in haystack]


def cheonggeul_badges(company: CompanyRecord) -> list[Badge]:
    """출처와 기준일이 있는 청끌 배지."""
    return [b for b in facts.valid_badges(company.highlights) if b.type == BadgeType.CHEONGKKEUL]


def _cheonggeul_types(company: CompanyRecord) -> set[CheonggeulType]:
    return {b.cheonggeul_type for b in cheonggeul_badges(company) if b.cheonggeul_type is not None}


def priority_types(profile: BasicProfile) -> set[CheonggeulType]:
    return {PRIORITY_TO_CHEONGGEUL[p] for p in profile.priorities if p in PRIORITY_TO_CHEONGGEUL}


def _parse_category(category: CheonggeulType | str | None) -> CheonggeulType | None:
    if category is None or category == "":
        return None
    try:
        return CheonggeulType(category)
    except ValueError as e:
        raise invalid_input("category 값이 올바르지 않아요.", field="category",
                            allowed=[t.value for t in CheonggeulType]) from e


def _card(company: CompanyRecord, overlap: list[str]) -> CompanyCard:
    badges = facts.valid_badges(company.highlights)
    lines = [b.label for b in cheonggeul_badges(company)]
    if company.district:
        lines.append(company.district)
    if company.industry:
        lines.append(FACT_INDUSTRY.format(value=company.industry))
    if company.main_product:
        lines.append(FACT_MAIN_PRODUCT.format(value=company.main_product))
    if company.size:
        lines.append(FACT_SIZE.format(value=company.size))
    if overlap:
        lines.append(FACT_WORD_OVERLAP.format(words=", ".join(overlap)))
    return CompanyCard(
        company_id=company.company_id,
        name=company.name,
        industry=company.industry,
        size=company.size,
        district=company.district,
        main_product=company.main_product,
        badges=badges,
        # catalog에 회사별 공고 조회가 없어 지금은 0이다. 포트가 생기면 진행 중 공고 수를 센다
        open_postings=0,
        facts=list(dict.fromkeys(lines)),
        source=company.source,
        as_of=company.as_of,
    )


def list_busan_companies(deps: Deps, user_id: str, *, category: CheonggeulType | str | None = None,
                         limit: int | None = None,
                         as_of: str | date | datetime | None = None) -> CompaniesResponse:
    """부산 청끌기업 회사 카드 목록.

    고르기: 부산(`config.data.busanSido`) 소재이고 출처·기준일이 있는 청끌 배지가 있는 회사. category를 주면 그 유형만.
    정렬: ① 희망 직무·전공 낱말이 업종·주력 제품과 겹치는 회사 ② 중요 조건과 청끌 유형이 맞는 회사 ③ 이름순 (법인 표기 빼고).
    프로필이나 희망 직무가 없으면 이름순으로 돌려준다.
    """
    ctx = load_context(deps, user_id, as_of)
    kind = _parse_category(category)
    size = deps.config.companies.limit if limit is None else max(0, limit)
    words = user_words(ctx.profile)
    wanted = priority_types(ctx.profile)

    rows: list[tuple[tuple, CompanyRecord, list[str]]] = []
    for company in deps.catalog.list_companies(deps.config.data.busan_sido):
        if company.sido != deps.config.data.busan_sido:
            continue
        types = _cheonggeul_types(company)
        if not cheonggeul_badges(company) or (kind is not None and kind not in types):
            continue
        overlap = overlap_words(words, company)
        key = (not overlap, not (types & wanted), name_key(company.name), company.company_id)
        rows.append((key, company, overlap))
    rows.sort(key=lambda r: r[0])

    data_as_of, _stale = freshness(deps, ctx.as_of)
    return CompaniesResponse(
        items=[_card(company, overlap) for _key, company, overlap in rows[:size]],
        basis=copy_rules.COMPANIES_BASIS,
        notice=copy_rules.COMPANIES_NOTICE,
        data_as_of=data_as_of,
    )
