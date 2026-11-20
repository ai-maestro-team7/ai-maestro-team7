"""나란히 비교 (B-06). 값만 나란히 두고 승패는 표시하지 않는다. 서울이 높은 칸도 그대로 보여 준다.

담당 워크트리: core-policy. 명세: 개발계획서2 §4.2 B-06, §5.5. 테스트: T-05, T-06, T-22.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import CompareResponse


def compare_postings(deps: Deps, user_id: str, base_job_posting_id: str, alt_job_posting_id: str, *,
                     family_housing: bool = False,
                     as_of: str | date | datetime | None = None) -> CompareResponse:
    """급여, 주거비, 통근, 지역 정책, 지역인재, 인증을 나란히 둔다.

    급여는 두 공고 모두 적혀 있을 때만 비교한다 (T-05). 출처·기준일이 없는 행은 뺀다.
    rentConversionRate가 null이면 주거비 행을 숨긴다. 지역 정책은 `count_regional_policies`로 양쪽을 계산한다.
    """
    raise NotImplementedError("core-policy 워크트리에서 구현한다")
