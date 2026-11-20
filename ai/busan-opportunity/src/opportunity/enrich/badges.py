"""배지 (B-02). 기업 시드에 있는 사실만 배지로 붙인다. 배지마다 source·asOf를 단다 (T-08).

기업은 companyId → 사업자번호 → 정규화한 이름 순서로 맞춘다. 시드에 없으면 붙이지 않는다.
원격 근무(FULL, HYBRID)는 공고에 적힌 사실이라 공고 원문을 출처로 단다.
"""

import re

from ..core import clock
from ..deps import Deps
from ..models.enums import BadgeType, RemoteWork
from ..models.posting import Badge, CompanyRecord, PostingSnapshot

REMOTE_LABEL = "원격 근무 가능"
REMOTE_SOURCE = "공고 원문"
REMOTE_KINDS = (RemoteWork.FULL, RemoteWork.HYBRID)

_CORP_MARKS = re.compile(r"주식회사|유한회사|\(주\)|\(유\)|㈜|㈲")
_NON_WORD = re.compile(r"[\s·.,\-()\[\]]+")


def normalize_name(name: str | None) -> str:
    """'(주) 가상 데이터', '가상데이터 주식회사'를 같은 값으로 만든다."""
    if not name:
        return ""
    return _NON_WORD.sub("", _CORP_MARKS.sub("", name)).lower()


def normalize_biz_no(biz_no: str | None) -> str:
    return re.sub(r"\D", "", biz_no or "")


def _sidos(deps: Deps, snapshot: PostingSnapshot) -> list[str]:
    """시드를 찾아볼 시·도. 근무지, 본사, 부산 순서이고 중복은 뺀다."""
    candidates = [None if snapshot.work_region.unknown else snapshot.work_region.sido, snapshot.company.hq_sido,
                  deps.config.data.busan_sido]
    out: list[str] = []
    for sido in candidates:
        if sido and sido not in out:
            out.append(sido)
    return out


def find_company(deps: Deps, snapshot: PostingSnapshot) -> CompanyRecord | None:
    """공고의 기업을 시드에서 찾는다. 못 찾으면 None."""
    if snapshot.company_id:
        company = deps.catalog.get_company(snapshot.company_id)
        if company is not None:
            return company
    biz_no = normalize_biz_no(snapshot.company.biz_no)
    names = {normalize_name(snapshot.company.name), normalize_name(snapshot.organization)} - {""}
    if not biz_no and not names:
        return None
    by_name = None
    for sido in _sidos(deps, snapshot):
        for company in deps.catalog.list_companies(sido):
            if biz_no and normalize_biz_no(company.biz_no) == biz_no:
                return company  # 사업자번호가 같으면 바로 정한다
            if by_name is None and normalize_name(company.name) in names:
                if not (biz_no and company.biz_no):  # 둘 다 번호가 있는데 다르면 다른 기업이다
                    by_name = company
    return by_name


def company_badges(company: CompanyRecord) -> list[Badge]:
    """시드의 인증을 배지로. 배지에 출처·기준일이 없으면 기업 시드의 값을 쓰고, 그래도 없으면 뺀다."""
    out: list[Badge] = []
    for badge in company.highlights:
        source = badge.source or company.source
        as_of = badge.as_of or company.as_of
        if not source or not as_of:
            continue
        out.append(badge.model_copy(update={"source": source, "as_of": as_of}))
    return out


def remote_badge(snapshot: PostingSnapshot) -> Badge | None:
    if snapshot.remote_work not in REMOTE_KINDS:
        return None
    return Badge(type=BadgeType.REMOTE_WORK, label=REMOTE_LABEL, source=REMOTE_SOURCE,
                 as_of=clock.day(snapshot.checked_at))


def build_badges(deps: Deps, snapshot: PostingSnapshot, company: CompanyRecord | None = None) -> list[Badge]:
    """공고에 붙일 배지 전체. 시드와 공고에서 확인한 것만 담고, 원래 붙어 있던 배지는 다시 만든다."""
    company = company if company is not None else find_company(deps, snapshot)
    badges = company_badges(company) if company else []
    remote = remote_badge(snapshot)
    if remote is not None:
        badges.append(remote)
    seen, out = set(), []
    for badge in badges:
        key = (badge.type, badge.cheonggeul_type, badge.label)
        if key not in seen:
            seen.add(key)
            out.append(badge)
    return out
