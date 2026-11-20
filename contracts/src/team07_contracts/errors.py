"""Error_Envelope와 Error_Code_Catalog (R4, docs/api.md §5, D-03·D-04·D-32).

모양: {"error": {"code", "message", "requestId", "retryable", "details"?}}. requestId는 error 안에 둔다 (D-03).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Optional

from pydantic import AfterValidator, StrictBool, StringConstraints, ValidationError

from .base import ContractModel, Part
from .validation import ContractValidationError, CrossFieldError, field_error, from_pydantic

A, B, C, BE = Part.A, Part.B, Part.C, Part.BACKEND


@dataclass(frozen=True)
class ErrorCodeSpec:
    http: int
    retryable: bool
    parts: tuple[Part, ...]
    alias_of: Optional[str] = None
    decisions: tuple[str, ...] = ()


def _spec(http, retryable, parts, alias_of=None, decisions=()):
    return ErrorCodeSpec(http, retryable, tuple(parts), alias_of, tuple(decisions))


# 출처: A §6.6, B §5.8, C §5.1, docs/api.md §5 (BACKEND 코드). D-32 규칙: A 코드에 retryable이 없으면 4xx false, 5xx true.
ERROR_CODES: dict[str, ErrorCodeSpec] = {
    "INVALID_INPUT": _spec(400, False, (B, C, BE), decisions=("D-04",)),
    "VALIDATION_ERROR": _spec(400, False, (A,), alias_of="INVALID_INPUT", decisions=("D-04", "D-32")),
    "URL_NOT_ALLOWED": _spec(400, False, (B,)),
    "UNAUTHORIZED": _spec(401, False, (A, BE), decisions=("D-32",)),
    "INVALID_CREDENTIALS": _spec(401, False, (BE,)),
    "RESOURCE_NOT_OWNED": _spec(404, False, (A,), decisions=("D-32",)),
    "NOT_FOUND": _spec(404, False, (BE,)),
    "DOCUMENT_NOT_FOUND": _spec(404, False, (A, BE), decisions=("D-32",)),
    "PROFILE_NOT_FOUND": _spec(404, False, (BE,)),
    "WORKSPACE_NOT_FOUND": _spec(404, False, (BE,)),
    "POSTING_NOT_FOUND": _spec(404, False, (B,)),
    "POLICY_NOT_FOUND": _spec(404, False, (B,)),
    "SESSION_NOT_FOUND": _spec(404, False, (C,)),
    "PRECONDITION_NOT_MET": _spec(409, False, (A, BE), decisions=("D-32",)),
    "INVALID_STATE": _spec(409, False, (C,)),
    "ANSWER_ALREADY_SUBMITTED": _spec(409, False, (C,)),
    "FILE_TOO_LARGE": _spec(413, False, (A, C), decisions=("D-32",)),
    "PROFILE_INCOMPLETE": _spec(422, False, (B,)),
    "DOCUMENT_UNREADABLE": _spec(422, False, (A,), decisions=("D-32",)),
    "EVIDENCE_MISMATCH": _spec(422, False, (A,), decisions=("D-32",)),
    "RATE_LIMITED": _spec(429, True, (A, BE), decisions=("D-32",)),
    "AI_OUTPUT_INVALID": _spec(500, True, (B, C)),
    "INTERNAL_ERROR": _spec(500, True, (A, B, C), decisions=("D-32",)),
    "NOT_IMPLEMENTED": _spec(501, False, (BE,)),
    "AWS_SERVICE_ERROR": _spec(503, True, (B, C), decisions=("D-04",)),
    "MODEL_UNAVAILABLE": _spec(503, True, (A,), alias_of="AWS_SERVICE_ERROR", decisions=("D-04", "D-32")),
    "SOURCE_UNAVAILABLE": _spec(503, True, (A,), alias_of="AWS_SERVICE_ERROR", decisions=("D-04", "D-32")),
}


def _known_code(value: str) -> str:
    if value not in ERROR_CODES:
        raise CrossFieldError([("", "enum")])
    return value


NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class ErrorBody(ContractModel):
    code: Annotated[str, AfterValidator(_known_code)]
    message: NonEmpty  # 한국어 문장 (R3.8)
    request_id: NonEmpty
    retryable: StrictBool
    details: dict[str, Any] = None  # 선택. 보내지 않으면 직렬화에서 빠진다


class ErrorEnvelope(ContractModel):
    error: ErrorBody


def normalize_code(code: str) -> str:
    """별칭 코드를 대표 코드로 바꾼다 (D-04). 목록에 없으면 ContractValidationError."""
    spec = ERROR_CODES.get(code)
    if spec is None:
        raise ContractValidationError("ErrorEnvelope", [field_error("code", "enum")])
    return spec.alias_of or code


def interview_error_to_envelope(err: object, request_id: str) -> ErrorEnvelope:
    """C의 InterviewError(code, message, retryable)를 Error_Envelope로 바꾼다 (R4.8, R4.9).

    err는 code·message·retryable 속성만 읽는다. interview 패키지를 import하지 않는다.
    """
    code = getattr(err, "code", None)
    problems = []
    if not isinstance(code, str) or code not in ERROR_CODES:
        problems.append(field_error("code", "enum"))
    if not isinstance(request_id, str) or not request_id:
        problems.append(field_error("requestId", "required"))
    if problems:
        raise ContractValidationError("ErrorEnvelope", problems)
    data = {"error": {"code": code, "message": getattr(err, "message", None),
                      "requestId": request_id, "retryable": getattr(err, "retryable", None)}}
    try:
        return ErrorEnvelope.model_validate(data)
    except ValidationError as exc:
        raise from_pydantic("ErrorEnvelope", exc) from None
