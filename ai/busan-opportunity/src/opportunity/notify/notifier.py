"""일정이 울렸을 때 처리와 알림함.

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-10. 테스트: T-10, T-11.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import DemoClockResponse, NotificationsResponse


def handle_schedule(deps: Deps, payload: dict, *, as_of: str | date | datetime | None = None,
                    simulated: bool = False) -> bool:
    """일정이 울리면 실제 상태를 다시 확인하고 알린다. 조건이 아니면 recheckDays 뒤 재확인 일정을 만든다.

    같은 알림은 한 번만 저장·발송한다 (T-10). 즉시 알림은 주 immediatePerWeek회까지이고 넘으면 다음 요약으로
    미룬다 (T-11). quietHours에는 보내지 않는다. 알렸으면 True.
    """
    raise NotImplementedError("api 워크트리에서 구현한다")


def check_new_opportunities(deps: Deps, user_id: str, *, cursor: str | None = None,
                            limit: int = 20) -> NotificationsResponse:
    """알림함 (최신순)."""
    raise NotImplementedError("api 워크트리에서 구현한다")


def mark_read(deps: Deps, user_id: str, notification_id: str) -> bool:
    """읽음 표시. 없는 알림이면 False."""
    raise NotImplementedError("api 워크트리에서 구현한다")


def advance_demo_clock(deps: Deps, user_id: str, as_of: str) -> DemoClockResponse:
    """데모 시간 앞당기기. demoAsOf를 저장하고 그 사이에 울릴 이 사용자의 일정을 바로 실행한다 (simulated=true)."""
    raise NotImplementedError("api 워크트리에서 구현한다")
