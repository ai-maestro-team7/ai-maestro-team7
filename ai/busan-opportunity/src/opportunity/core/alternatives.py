"""같은 일, 부산에서 (B-05). 수도권 공고와 하는 일이 비슷한 부산 공고를 찾는다.

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-05, §4.5 altScore, §4.6 이유별 재정렬. 테스트: T-15, T-21, T-22.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import AlternativesResponse
from ..models.enums import LeaveReason


def find_busan_alternatives(deps: Deps, user_id: str, job_posting_id: str, *,
                            leave_reason: LeaveReason | None = None, limit: int | None = None,
                            as_of: str | date | datetime | None = None) -> AlternativesResponse:
    """미리 계산한 후보(ALTS)를 이 사용자 기준으로 다시 정렬한다. 없으면 벡터 인덱스를 바로 질의한다.

    유사도 minSimilarity 이상만 남기고 altScore로 정렬해 최대 viewMax개 (limit로 줄일 수 있음).
    0개면 직종 상위 분류로 넓혀 expandedMinSimilarity로 다시 찾는다. 그래도 0개면 noAlternative=true이고
    NO_ALTERNATIVE 이벤트를 남긴다 (T-15). 부산 공고를 넣으면 빈 목록과 reason=ALREADY_BUSAN.
    보여 준 대안이 있으면 ALT_SHOWN 이벤트를 남긴다. 마감된 공고는 뺀다 (T-21).
    """
    raise NotImplementedError("core-match 워크트리에서 구현한다")
