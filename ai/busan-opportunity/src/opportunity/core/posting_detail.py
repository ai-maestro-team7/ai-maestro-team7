"""공고 상세 (B-04).

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-04. 관련 정책은 `core.policies.related_policies`를 부른다.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import PostingDetailResponse, RegionalTalentResponse


def get_posting(deps: Deps, user_id: str, job_posting_id: str, *,
                as_of: str | date | datetime | None = None) -> PostingDetailResponse:
    """LATEST → SNAP#을 읽어 요건, 지원 자격, 배지, 지역인재, 관련 정책, 대안 미리보기(최대 miniCardMax)를 돌려준다.

    필수 조건을 못 맞춘 공고도 숨기지 않고 이유를 붙여 보여 준다. 마감된 공고는 오류가 아니라 closed=true.
    출처·기준일이 없는 배지는 뺀다 (T-08). 없는 공고는 POSTING_NOT_FOUND.
    """
    raise NotImplementedError("core-match 워크트리에서 구현한다")


def get_regional_talent(deps: Deps, user_id: str, job_posting_id: str, *,
                        as_of: str | date | datetime | None = None) -> RegionalTalentResponse:
    """공공기관 공고의 지역인재 전형 해당 가능성. 문구는 "대상일 수 있어요"로만 쓴다."""
    raise NotImplementedError("core-match 워크트리에서 구현한다")
