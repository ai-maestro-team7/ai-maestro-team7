"""공고 ↔ 공공기관 직원 평균보수 (B-D11). 공고의 기관 이름으로 `ORGPAY`를 찾는다. LLM을 부르지 않는다.

평균보수는 직원 전체의 평균이라 신입 초봉이 아니다. 화면·대화 문구는 늘 "기관 평균"으로 쓰고 출처·연도를 붙인다.
"""

import re

from ..deps import Deps
from ..models.posting import OrgPay, PostingLatest

# 이름을 견줄 때 빼는 법인 표시. 채용공시와 경영공시는 같은 알리오 이름을 써서 대부분 그대로 맞는다
_LEGAL = re.compile(r"\(주\)|㈜|주식회사|\(재\)|재단법인|\(사\)|사단법인|\s+")


def name_key(name: str | None) -> str:
    return _LEGAL.sub("", name or "")


def org_pay_index(deps: Deps) -> dict[str, OrgPay]:
    """기관 이름(법인 표시·공백 제외) → 평균보수. 저장소가 1분 캐시하므로 요청마다 불러도 된다."""
    return {name_key(p.name): p for p in deps.catalog.org_pays()}


def org_pay_for(index: dict[str, OrgPay], posting: PostingLatest) -> OrgPay | None:
    return index.get(name_key(posting.organization)) if index else None


def label(average: int, year: int) -> str:
    """"기관 직원 평균 연 9,118만 원 (2025년 결산 · 알리오 경영공시, 신입 초봉 아님)"."""
    return f"기관 직원 평균 연 {average:,}만 원 ({year}년 결산 · 알리오 경영공시, 신입 초봉 아님)"
