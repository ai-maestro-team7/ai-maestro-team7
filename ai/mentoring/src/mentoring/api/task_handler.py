"""비동기 작업 입구 (D-19 Lambda 비동기 자기 호출, BE-2).
백엔드 `backend/app.py`가 이벤트에 `mentoringTask` 키가 있으면 이 함수를 부른다.
"""
from pydantic import ValidationError

from ..core.tasks import EVENT_KEY, run_task
from ..deps import Deps
from ..models import TaskMessage


def is_mentoring_task(event: dict) -> bool:
    return isinstance(event, dict) and isinstance(event.get(EVENT_KEY), dict)


def handle(event: dict, deps: Deps) -> dict:
    if not is_mentoring_task(event):
        return {"status": "SKIPPED", "reason": "NOT_A_MENTORING_TASK"}
    try:
        message = TaskMessage.model_validate(event[EVENT_KEY])
    except ValidationError:
        return {"status": "SKIPPED", "reason": "INVALID_MESSAGE"}
    return run_task(deps, message)
