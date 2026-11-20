"""비동기 작업 실행 (Requirement 4 기준 5~7, D-19).
같은 작업이 두 번 와도 결과는 한 번만 저장한다: PENDING → PROCESSING 조건부 전이에 성공한 쪽만 실행한다 (UT-17).
"""
import time

from ..errors import MentoringError
from ..models import ExtractionStatus, Task, TaskMessage, TaskStatus, TaskType
from .logs import log_event, user_hash

EVENT_KEY = "mentoringTask"  # 백엔드가 A 작업을 알아보는 키 (BE-2)


def build_message(task: Task) -> dict:
    message = TaskMessage(task_id=task.task_id, task_type=task.task_type, user_id=task.owner_user_id,
                          resource_id=task.resource_id, resource_version=task.resource_version)
    return {EVENT_KEY: message.to_api()}


def run_task(deps, message: TaskMessage) -> dict:
    """작업 하나를 실행하고 요약을 돌려준다. 예외를 밖으로 던지지 않는다 (비동기 호출이라 받을 쪽이 없다)."""
    from .extraction import run_profile_extraction  # 순환 import 방지
    from .upload import run_document_extraction

    started = time.perf_counter()
    uid = message.user_id
    task = deps.users.get_task(uid, message.task_id)
    if task is None or task.resource_id != message.resource_id or task.resource_version != message.resource_version:
        log_event("task.skipped", userHash=user_hash(deps, uid), taskId=message.task_id, status="NOT_FOUND")
        return {"taskId": message.task_id, "status": "SKIPPED", "reason": "TASK_NOT_FOUND"}
    if task.status != TaskStatus.PENDING:
        log_event("task.skipped", userHash=user_hash(deps, uid), taskId=task.task_id, status=task.status.value)
        return {"taskId": task.task_id, "status": "SKIPPED", "reason": f"ALREADY_{task.status.value}"}

    now = deps.now_iso()
    claimed = task.model_copy(update={"status": TaskStatus.PROCESSING, "started_at": now, "updated_at": now})
    if not deps.users.update_task(claimed, expected_status=TaskStatus.PENDING):
        return {"taskId": task.task_id, "status": "SKIPPED", "reason": "CLAIMED_BY_OTHER"}

    try:
        if claimed.task_type == TaskType.PROFILE_EXTRACT:
            outcome = run_profile_extraction(deps, claimed)
        elif claimed.task_type == TaskType.DOCUMENT_EXTRACT:
            outcome = run_document_extraction(deps, claimed)
        else:
            raise MentoringError(500, "INTERNAL_ERROR", "알 수 없는 작업이에요.", False)
        final = claimed.model_copy(update={
            "status": outcome.status, "result_id": outcome.result_id, "review_reason": outcome.review_reason,
            "retry_count": outcome.retry_count, "error_code": None, "retryable": None,
            "updated_at": deps.now_iso(), "completed_at": deps.now_iso()})
    except MentoringError as error:
        final = _failed(deps, claimed, error.code, error.retryable)
    except Exception as error:  # noqa: BLE001 - 비동기 작업은 어떤 오류든 FAILED로 남겨야 한다
        log_event("task.error", userHash=user_hash(deps, uid), taskId=task.task_id, errorCode=type(error).__name__)
        final = _failed(deps, claimed, "INTERNAL_ERROR", True)

    deps.users.update_task(final, expected_status=TaskStatus.PROCESSING)
    log_event("task.finished", userHash=user_hash(deps, uid), taskId=final.task_id, taskType=final.task_type.value,
              status=final.status.value, errorCode=final.error_code, retryCount=final.retry_count,
              durationMs=round((time.perf_counter() - started) * 1000, 1))
    return {"taskId": final.task_id, "status": final.status.value, "resultId": final.result_id,
            "errorCode": final.error_code}


def _failed(deps, task: Task, code: str, retryable: bool) -> Task:
    from .documents import set_document_status

    set_document_status(deps, task.owner_user_id, task.resource_id, task.resource_version, ExtractionStatus.FAILED,
                        error_code=code)
    now = deps.now_iso()
    return task.model_copy(update={"status": TaskStatus.FAILED, "error_code": code, "retryable": retryable,
                                   "updated_at": now, "completed_at": now})
