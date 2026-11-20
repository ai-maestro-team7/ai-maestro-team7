"""비동기 작업 `TASK#{taskId}` (db-schema §2.5). 상태 전이는 조건부 쓰기로만 한다."""
from pydantic import Field

from .base import MentoringModel
from .enums import TaskStatus, TaskType


class Task(MentoringModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus
    owner_user_id: str
    resource_id: str
    resource_version: int = Field(ge=1)
    result_id: str | None = None
    error_code: str | None = None
    retryable: bool | None = None
    review_reason: str | None = None
    retry_count: int = 0
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


class TaskMessage(MentoringModel):
    """비동기 작업 이벤트 본문. 리소스 ID와 버전만 담고 원문·텍스트는 담지 않는다 (A §10.1)."""
    task_id: str
    task_type: TaskType
    user_id: str
    resource_id: str
    resource_version: int = Field(ge=1)
