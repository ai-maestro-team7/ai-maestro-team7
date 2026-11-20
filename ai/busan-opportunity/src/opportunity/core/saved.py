"""저장·목표 담기 (B-09).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-09, `docs/db-schema.md` §2.3. 테스트: T-09, T-16.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import SavedListResponse, SaveRequest, SaveResponse


def add_target_posting(deps: Deps, user_id: str, request: SaveRequest, *, idempotency_key: str | None = None,
                       as_of: str | date | datetime | None = None) -> SaveResponse:
    """공고를 저장하거나 목표로 담는다. `OPP#SAVED#`와 워크스페이스를 한 트랜잭션으로 쓴다.

    TARGET이면 마감 D-7·D-3 일정을 만든다. 수도권 공고 첫 저장이면 askLeaveReason=true (사용자당 한 번, T-09).
    같은 Idempotency-Key로 다시 오면 한 번만 반영하고 (T-16), 본문이 다르면 409 PRECONDITION_NOT_MET.
    SAVED 이벤트를 남긴다.
    """
    raise NotImplementedError("api 워크트리에서 구현한다")


def list_saved(deps: Deps, user_id: str, *, as_of: str | date | datetime | None = None) -> SavedListResponse:
    """저장 목록. 지원 상태는 워크스페이스에서 읽는다."""
    raise NotImplementedError("api 워크트리에서 구현한다")
