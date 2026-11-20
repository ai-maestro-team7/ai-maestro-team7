"""로그인 없이 보는 채용 공고 목록 (B-D10). 이 경로에 LLM은 없다.

프로필을 쓰지 않으므로 적합도·자격 판정·부산 대안 수 같은 개인 값이 없고, 정렬은 마감 임박순 하나다(상시 채용은 뒤).
부산 공고를 앞으로 올리지 않는다. 맞춤 순서는 로그인 뒤 맞춤 피드(`search_postings`)가 맡는다.

이름 색인(`POSTNAMES`)을 Query 한 번으로 읽어 분류와 검색어로 거른 뒤, 한 쪽에 보일 공고만 LATEST를 읽는다.
Scan은 쓰지 않는다.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import PublicPostingCard, PublicPostingList
from ..models.enums import CareerType, EmploymentType, OrgType
from ..models.errors import invalid_input
from ..models.posting import PostingLatest, PostingName
from . import clock, regions
from .context import freshness
from .ranking import (
    REGION_ALL,
    REGION_OVERSEAS,
    _check_region,
    check_sector,
    sector_ok,
    _decode_cursor,
    _encode_cursor,
    _keyword_hit,
    _region_sidos,
    is_open,
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
CHOICE_ALL = "ALL"
# 경력 분류: "신입"을 고르면 신입·경력 무관 공고도 함께 보인다 (경력도 같다)
CAREER_FILTERS = {
    CareerType.NEW.value: {CareerType.NEW, CareerType.ANY},
    CareerType.EXPERIENCED.value: {CareerType.EXPERIENCED, CareerType.ANY},
}
EMPLOYMENT_FILTERS = {t.value for t in (EmploymentType.FULL_TIME, EmploymentType.CONTRACT, EmploymentType.PART_TIME,
                                        EmploymentType.INTERN)}
ORG_FILTERS = {t.value for t in OrgType}


def list_public_postings(deps: Deps, *, keyword: str | None = None, region: str | None = REGION_ALL,
                         sector: str | None = None, org_type: str | None = None, career: str | None = None,
                         employment: str | None = None,
                         cursor: str | None = None, limit: int = DEFAULT_LIMIT,
                         as_of: str | date | datetime | None = None) -> PublicPostingList:
    """분류(지역·기관 구분·경력·고용 형태)와 검색어로 진행 중 공고를 거른다. 각 분류는 ALL이나 None이면 거르지 않는다.

    sector는 공기업(PUBLIC: 공공기관·지방공공기관)과 사기업(PRIVATE)으로 나눈다. org_type은 그보다 잘게 한 가지만 고른다.
    """
    when = clock.parse_as_of(as_of)
    region = (region or REGION_ALL).strip().upper()
    _check_region(region)
    sector = check_sector(sector)
    org = _choice(org_type, ORG_FILTERS, "orgType")
    careers = CAREER_FILTERS.get(_choice(career, set(CAREER_FILTERS), "career") or "")
    employment_type = _choice(employment, EMPLOYMENT_FILTERS, "employment")
    if not 1 <= limit <= MAX_LIMIT:
        raise invalid_input(f"limit은 1~{MAX_LIMIT} 사이여야 해요.", field="limit")
    offset = _decode_cursor(cursor)
    sidos = _region_sidos(deps.config, region)

    rows = [n for n in deps.catalog.posting_names()
            if not clock.is_expired(n.closes_at, when)
            and _region_ok(n, region, sidos)
            and sector_ok(n.org_type, sector)
            and (org is None or n.org_type == org)
            and (careers is None or n.career_type in careers)
            and (employment_type is None or n.employment_type == employment_type)
            and _keyword_hit(keyword, (n.title, n.organization, n.job_name))]
    rows.sort(key=lambda n: (n.closes_at, n.job_posting_id))  # 상시 채용(9999-12-31)은 맨 뒤

    page = rows[offset:offset + limit]
    latest = deps.catalog.batch_get_latest([n.job_posting_id for n in page])
    items = [_card(latest[n.job_posting_id]) for n in page
             if n.job_posting_id in latest and is_open(latest[n.job_posting_id], when)]
    data_as_of, stale = freshness(deps, when)
    return PublicPostingList(items=items, total=len(rows),
                             next_cursor=_encode_cursor(offset + limit) if offset + limit < len(rows) else None,
                             data_as_of=data_as_of, stale=stale)


def _choice(value: str | None, allowed: set[str], field: str) -> str | None:
    """분류 값 하나. 비었거나 ALL이면 None(거르지 않음). 모르는 값이면 400."""
    value = (value or "").strip().upper()
    if not value or value == CHOICE_ALL:
        return None
    if value not in allowed:
        raise invalid_input(f"{field} 값이 올바르지 않아요.", field=field, allowed=sorted([CHOICE_ALL, *allowed]))
    return value


def _region_ok(row: PostingName, region: str, sidos: list[str] | None) -> bool:
    """맞춤 피드의 지역 거르기(`ranking._in_region`)와 같다. 근무지를 모르는 공고는 시·도를 골랐을 때 빠진다."""
    if region == REGION_OVERSEAS:
        return row.is_overseas
    if sidos is None:
        return True
    return not row.is_overseas and row.sido is not None and row.sido in sidos


def _card(posting: PostingLatest) -> PublicPostingCard:
    return PublicPostingCard(
        job_posting_id=posting.job_posting_id, title=posting.title, organization=posting.organization,
        org_type=posting.org_type, work_region=posting.work_region, is_busan=posting.is_busan,
        is_overseas=posting.is_overseas or regions.is_overseas(posting.work_region), job=posting.job, closes_at=posting.closes_at, rolling=posting.rolling,
        salary=posting.salary, career_type=posting.career_type, employment_type=posting.employment_type,
        badges=posting.badges, is_sample=posting.is_sample)
