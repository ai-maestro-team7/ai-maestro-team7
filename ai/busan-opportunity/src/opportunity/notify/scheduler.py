"""일회성 일정 예약 (EventBridge Scheduler).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-09·B-10.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import PolicyAlertResponse, ScheduleView
from ..models.posting import PostingLatest


def schedule_name(user_id: str, kind: str, target_id: str, suffix: str = "") -> str:
    """일정 이름. 사용자·대상 해시로 고정해 64자 안에 둔다. 사용자 ID 원문은 넣지 않는다."""
    raise NotImplementedError("api 워크트리에서 구현한다")


def schedule_target_deadlines(deps: Deps, user_id: str, posting: PostingLatest, *,
                              as_of: datetime) -> list[ScheduleView]:
    """목표 공고의 마감 D-7·D-3 일정을 만든다 (digestHour시). 이미 지난 날짜와 상시 채용은 만들지 않는다."""
    raise NotImplementedError("api 워크트리에서 구현한다")


def subscribe_policy_alert(deps: Deps, user_id: str, policy_id: str, *, idempotency_key: str | None = None,
                           as_of: str | date | datetime | None = None) -> PolicyAlertResponse:
    """정책이 열리면 알림. 이미 신청했으면 같은 결과를 다시 돌려준다."""
    raise NotImplementedError("api 워크트리에서 구현한다")
