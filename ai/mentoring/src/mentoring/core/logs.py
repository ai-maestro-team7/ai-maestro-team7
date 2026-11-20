"""구조화 로그. 정해 둔 키만 남긴다 (Requirement 12 기준 1·2, 개발계획서1 F-08).
이력서 원문, 추출 텍스트, 인용문, 경험 원문, presigned URL, 파일 이름은 키 목록에 없어서 넘겨도 버려진다.
"""
import json
import logging

logger = logging.getLogger("mentoring")

ALLOWED_KEYS = {
    "event", "requestId", "userHash", "taskId", "taskType", "feature", "stage", "status", "durationMs",
    "modelId", "promptVersion", "validation", "errorCode", "retryCount", "method", "route", "counts",
}


def user_hash(deps, user_id: str) -> str:
    return deps.hash_user_id(user_id)[:16]


def log_event(event: str, **fields) -> None:
    record = {"event": event}
    record.update({k: v for k, v in fields.items() if k in ALLOWED_KEYS and v is not None})
    logger.info(json.dumps(record, ensure_ascii=False, default=str))
