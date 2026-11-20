"""Async_Task_Status (R5, docs/api.md §4, D-05).

공통 status 4개와 Part별 확장(A 추가 상태, C stage 필드). 종료 여부는 status만으로 정한다.
Part 결과 필드(C progress·nextQuestion·report 등)는 검사하지 않고 그대로 보존한다.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import ConfigDict, ValidationError

from .base import ContractModel, Part
from .errors import ErrorBody
from .validation import ContractValidationError, field_error, from_pydantic

COMMON_STATUSES: dict[str, bool] = {"PENDING": False, "PROCESSING": False, "COMPLETED": True, "FAILED": True}


@dataclass(frozen=True)
class PartStatusSpec:
    id_field: str
    extra_statuses: dict[str, bool] = field(default_factory=dict)  # 값 → 종료 여부
    field_extensions: dict[str, frozenset[str]] = field(default_factory=dict)  # 필드 → 허용 값


STATUS_EXTENSIONS: dict[Part, PartStatusSpec] = {
    Part.A: PartStatusSpec("taskId", {"REQUIRES_USER_REVIEW": True, "PARTIAL_SUCCESS": True}),  # A §6, F-01
    Part.B: PartStatusSpec("jobId"),  # B §5.1
    Part.C: PartStatusSpec("sessionId", field_extensions={"stage": frozenset({  # C §5.1
        "QUESTION_GENERATING", "NEXT_QUESTION_READY", "TRANSCRIBING", "JUDGING", "REPORT_GENERATING", "REPORT_READY"})}),
}


def check_status_extensions(extensions: Mapping[Part, PartStatusSpec]) -> None:
    """확장 상태 이름이 공통 상태와 겹치면 ValueError (R5.3)."""
    for part, spec in extensions.items():
        clash = set(spec.extra_statuses) & set(COMMON_STATUSES)
        if clash:
            raise ValueError(f"{part.value} 확장 상태가 공통 상태와 겹쳐요: {sorted(clash)}")


check_status_extensions(STATUS_EXTENSIONS)

_SAFE_ID = re.compile(r"[^#]{1,200}")


class AsyncTaskStatus(ContractModel):
    model_config = ConfigDict(extra="allow")  # Part 결과 필드는 그대로 둔다

    status: str
    error: ErrorBody | None = None


def _spec(part: Part | str) -> tuple[Part, PartStatusSpec]:
    part = Part(part)
    if part not in STATUS_EXTENSIONS:
        raise ValueError(f"비동기 상태를 정의하지 않은 Part예요: {part.value}")
    return part, STATUS_EXTENSIONS[part]


def parse_async_status(part: Part | str, data: Mapping) -> AsyncTaskStatus:
    part, spec = _spec(part)
    if not isinstance(data, Mapping):
        raise ContractValidationError("AsyncTaskStatus", [field_error("", "type")])
    problems = []
    status = data.get("status")
    if "status" not in data:
        problems.append(field_error("status", "required"))
    elif not isinstance(status, str) or status not in {**COMMON_STATUSES, **spec.extra_statuses}:
        problems.append(field_error("status", "enum"))
    task_id = data.get(spec.id_field)
    if spec.id_field not in data:
        problems.append(field_error(spec.id_field, "required"))
    elif not isinstance(task_id, str) or not _SAFE_ID.fullmatch(task_id):
        problems.append(field_error(spec.id_field, "pattern"))
    if status == "FAILED" and data.get("error") is None:
        problems.append(field_error("error", "required"))
    for name, allowed in spec.field_extensions.items():
        if name in data and data[name] not in allowed:
            problems.append(field_error(name, "enum"))
    try:
        model = AsyncTaskStatus.model_validate(dict(data))
    except ValidationError as exc:
        problems.extend(e for e in from_pydantic("AsyncTaskStatus", exc).errors
                        if e.path not in {p.path for p in problems})
        model = None
    if problems:
        raise ContractValidationError("AsyncTaskStatus", problems)
    return model


def is_terminal(part: Part | str, status: str) -> bool:
    """status만으로 종료 여부를 정한다. C stage가 REPORT_READY여도 COMPLETED가 아니면 비종료 (R5.8)."""
    _, spec = _spec(part)
    if status in COMMON_STATUSES:
        return COMMON_STATUSES[status]
    if status in spec.extra_statuses:
        return spec.extra_statuses[status]
    raise ValueError(f"알 수 없는 상태예요: {status}")
