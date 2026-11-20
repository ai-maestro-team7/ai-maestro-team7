"""지역인재 전형 해당 가능성 (B-02). 판정이 아니라 "대상일 수 있어요"를 보여 줄 근거만 만든다.

- 이전기관 공고이고 원문에 지역인재 전형·가점·채용목표제가 나오면 LIKELY, basis에 그 문장을 둔다.
- 이전기관인데 원문에서 못 찾으면 CHECK_NEEDED. 이전기관이 아니면 NOT_APPLICABLE.
"""

import re

from ..models.enums import RegionalTalentStatus
from ..models.posting import CompanyRecord, RegionalTalent

KEYWORDS = ("지역인재", "채용목표제")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def find_basis(text: str) -> str | None:
    """지역인재 언급이 있는 첫 문장. 없으면 None."""
    for sentence in _sentences(text):
        if any(word in sentence for word in KEYWORDS):
            return sentence
    return None


def judge_regional_talent(company: CompanyRecord | None, text: str) -> RegionalTalent:
    if company is None or not company.regional_talent:
        return RegionalTalent(status=RegionalTalentStatus.NOT_APPLICABLE)
    basis = find_basis(text)
    if basis is None:
        return RegionalTalent(status=RegionalTalentStatus.CHECK_NEEDED)
    return RegionalTalent(status=RegionalTalentStatus.LIKELY, basis=basis)
