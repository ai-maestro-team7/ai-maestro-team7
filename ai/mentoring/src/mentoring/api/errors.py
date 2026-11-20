"""입구 공용 오류 변환. 팀 공통 형식 `{"error": {code, message, requestId, retryable, details}}` (docs/api.md §5).
A 별칭 코드(`VALIDATION_ERROR`, `MODEL_UNAVAILABLE`, `SOURCE_UNAVAILABLE`)는 대표 코드로 바꿔 응답한다 (D-04).
"""
import json
import uuid

from pydantic import ValidationError
from team07_contracts import normalize_code
from team07_contracts.validation import ContractValidationError

from ..errors import MentoringError


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


def public_code(code: str) -> str:
    try:
        return normalize_code(code)
    except ContractValidationError:
        return code


def error_body(status: int, code: str, message: str, request_id: str, *, retryable: bool = False,
               details: dict | None = None) -> tuple[int, dict]:
    return status, {"error": {"code": public_code(code), "message": message, "requestId": request_id,
                              "retryable": retryable, "details": details or {}}}


def from_mentoring_error(error: MentoringError, request_id: str) -> tuple[int, dict]:
    return error_body(error.status, error.code, error.message, request_id, retryable=error.retryable,
                      details=error.details)


def from_validation_error(error: ValidationError, request_id: str) -> tuple[int, dict]:
    """Pydantic 검증 오류는 400 INVALID_INPUT. 입력값 원문은 details에 넣지 않는다."""
    fields = sorted({".".join(str(p) for p in e["loc"]) for e in error.errors() if e.get("loc")})
    return error_body(400, "INVALID_INPUT", "입력 형식이 올바르지 않아요.", request_id, details={"fields": fields})


def from_unexpected(request_id: str) -> tuple[int, dict]:
    return error_body(500, "INTERNAL_ERROR", "잠시 후 다시 시도해 주세요.", request_id, retryable=True)


def error_code_of(body: str | None) -> str | None:
    """로그용. 응답 본문에서 오류 코드만 꺼낸다."""
    if not body:
        return None
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    error = data.get("error") if isinstance(data, dict) else None
    return error.get("code") if isinstance(error, dict) else None
