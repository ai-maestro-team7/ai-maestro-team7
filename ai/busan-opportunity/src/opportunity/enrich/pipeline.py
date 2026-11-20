"""보강 배치 입구.

담당 워크트리: enrich. 명세: 개발계획서2 §4.2 B-02. 테스트: T-18.
"""

from datetime import date, datetime

from ..deps import Deps


def enrich_postings(deps: Deps, job_posting_ids: list[str], *,
                    as_of: str | date | datetime | None = None) -> dict:
    """요건 추출, 임베딩, 배지, 지역인재, 부산 대안 후보 계산을 차례로 한다.

    API에서 받은 값(마감일·근무지·급여)은 LLM 결과로 덮어쓰지 않는다. 한 번 다시 시도해도 추출에 실패하면
    extractStatus=FAILED로 둔다. 돌려주는 값은 건수 요약 {"enriched", "failed", "alts"}.
    """
    raise NotImplementedError("enrich 워크트리에서 구현한다")
