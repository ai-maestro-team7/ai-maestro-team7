"""계약 검사·직렬화·버전 확인과 봉투 문서 읽기 (R10).

봉투: {"contract", "schemaVersion", "examples": [{"name", "data", ...}]} 또는 {"contract", "schemaVersion", "data"}.
schemaVersion은 계약 본문에 넣지 않는다. 이미 배포된 API 응답 모양을 바꾸지 않으려는 것이다.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import ValidationError

from .async_status import parse_async_status
from .base import ContractModel, Part
from .registry import CONTRACTS
from .validation import ContractValidationError, ContractVersionError, field_error, from_pydantic

_VERSION = re.compile(r"\d+\.\d+")


def _meta(contract: str):
    if contract not in CONTRACTS:
        raise KeyError(f"알 수 없는 계약이에요: {contract}")
    return CONTRACTS[contract]


def check_schema_version(contract: str, value: object) -> None:
    """형식이 "주.부"가 아니거나 주 버전이 다르면 ContractVersionError. 부 버전만 다르면 통과 (R10.3, R10.6)."""
    meta = _meta(contract)
    supported = f"{meta.major}.x"
    if not isinstance(value, str) or not _VERSION.fullmatch(value) or int(value.split(".")[0]) != meta.major:
        raise ContractVersionError(contract, value, supported)


def validate(contract: str, data: Mapping, *, schema_version: str, part: Part | str | None = None) -> ContractModel:
    check_schema_version(contract, schema_version)
    meta = _meta(contract)
    if contract == "AsyncTaskStatus":
        if part is None:
            raise ValueError("AsyncTaskStatus는 part가 필요해요")
        return parse_async_status(part, data)
    if not isinstance(data, Mapping):
        raise ContractValidationError(contract, [field_error("", "type")])
    try:
        return meta.model.model_validate(dict(data))
    except ValidationError as exc:
        raise from_pydantic(contract, exc) from None


def dump(model: ContractModel) -> dict:
    """JSON용 dict. 보내지 않은 선택 필드는 빠지고, 명시한 null은 그대로 남는다."""
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def load_document(doc: Mapping) -> list[ContractModel]:
    contract, version = doc.get("contract"), doc.get("schemaVersion")
    if "examples" in doc:
        items = [(e.get("data"), (e.get("context") or {}).get("part")) for e in doc["examples"]]
    else:
        items = [(doc.get("data"), (doc.get("context") or {}).get("part"))]
    return [validate(contract, data, schema_version=version, part=part) for data, part in items]
