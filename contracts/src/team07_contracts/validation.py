"""계약 검사 오류 형식 (common-foundation 설계 "Error Handling" > 계약 검사 오류).

오류 메시지에는 입력 값 원문을 넣지 않는다 (개인정보·비밀정보가 로그로 새지 않게).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pydantic import ValidationError

# Pydantic 오류 종류 → 계약 규칙 이름
_RULES = {
    "extra_forbidden": "unknownField",
    "missing": "required",
    "string_too_short": "length",
    "string_too_long": "length",
    "too_short": "minItems",
    "too_long": "maxItems",
    "greater_than": "range",
    "greater_than_equal": "range",
    "less_than": "range",
    "less_than_equal": "range",
    "string_pattern_mismatch": "pattern",
    "literal_error": "enum",
    "enum": "enum",
}

MESSAGES = {
    "unknownField": "정의되지 않은 항목이에요.",
    "required": "꼭 필요한 항목이 없어요.",
    "type": "값의 형식이 맞지 않아요.",
    "length": "글자 수가 허용 범위를 벗어났어요.",
    "minItems": "항목 수가 너무 적어요.",
    "maxItems": "항목 수가 너무 많아요.",
    "range": "값이 허용 범위를 벗어났어요.",
    "pattern": "값의 모양이 규칙과 맞지 않아요.",
    "enum": "허용되지 않은 값이에요.",
    "duplicate": "같은 값이 이미 있어요.",
    "value": "값이 올바르지 않아요.",
}


@dataclass(frozen=True)
class FieldError:
    path: str  # 카멜 경로, 예: "requirements[0].sourceQuote", "error.code"
    rule: str
    message: str


class CrossFieldError(ValueError):
    """검사기 안에서 필드 경로와 규칙을 지정해 오류를 낼 때 쓴다.

    items: [(검사기 위치 기준 상대 경로, 규칙)]. 상대 경로가 ""이면 검사기 위치 그대로다.
    """

    def __init__(self, items: Iterable[tuple[str, str]]):
        self.items = list(items)
        super().__init__(", ".join(f"{p or '<here>'}:{r}" for p, r in self.items))


class ContractValidationError(ValueError):
    code = "INVALID_INPUT"

    def __init__(self, contract: str, errors: Iterable[FieldError]):
        self.contract = contract
        self.errors = list(errors)
        super().__init__(f"{contract}: " + ", ".join(f"{e.path or '<root>'}({e.rule})" for e in self.errors))

    @property
    def fields(self) -> list[str]:
        return [e.path for e in self.errors]


class ContractVersionError(ValueError):
    code = "INVALID_INPUT"

    def __init__(self, contract: str, received: object, supported: str):
        self.contract, self.received, self.supported = contract, received, supported
        super().__init__(f"{contract}: schemaVersion {received!r}는 지원하지 않아요 (지원: {supported})")


def field_error(path: str, rule: str) -> FieldError:
    return FieldError(path, rule, MESSAGES.get(rule, MESSAGES["value"]))


def join_path(base: str, sub: str) -> str:
    if not sub:
        return base
    if not base or sub.startswith("["):
        return base + sub
    return f"{base}.{sub}"


def loc_to_path(loc: Iterable[object]) -> str:
    path = ""
    for part in loc:
        path = path + f"[{part}]" if isinstance(part, int) else join_path(path, str(part))
    return path


def from_pydantic(contract: str, exc: ValidationError, prefix: str = "") -> ContractValidationError:
    out: list[FieldError] = []
    for e in exc.errors(include_url=False, include_input=False):
        base = join_path(prefix, loc_to_path(e["loc"]))
        err = (e.get("ctx") or {}).get("error")
        if isinstance(err, CrossFieldError):
            out.extend(field_error(join_path(base, sub), rule) for sub, rule in err.items)
            continue
        kind = e["type"]
        rule = _RULES.get(kind) or ("type" if kind.endswith("_type") or kind.endswith("_parsing") else "value")
        out.append(field_error(base, rule))
    return ContractValidationError(contract, _dedupe(out))


def _dedupe(errors: list[FieldError]) -> list[FieldError]:
    seen, out = set(), []
    for e in errors:
        if (e.path, e.rule) not in seen:
            seen.add((e.path, e.rule))
            out.append(e)
    return out
