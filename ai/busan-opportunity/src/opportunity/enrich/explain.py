"""공고 설명 문장 (GET /postings/{id}/explanation).

담당 워크트리: enrich. 명세: 개발계획서2 §4.2 B-04, §4.7. 테스트: T-19.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import ExplanationResponse


def explain_posting(deps: Deps, user_id: str, job_posting_id: str, *,
                    as_of: str | date | datetime | None = None) -> ExplanationResponse:
    """사실 목록으로 설명 문장을 만든다 (explanation.sentences개). `OPP#EXPL#`에 cacheHours 동안 캐시한다.

    문장의 숫자는 사실 목록에 있는 것만 쓰고, 금지 문구가 있으면 다시 만든다 (T-19).
    한 번 다시 시도해도 실패하면 AI_OUTPUT_INVALID.
    """
    raise NotImplementedError("enrich 워크트리에서 구현한다")
