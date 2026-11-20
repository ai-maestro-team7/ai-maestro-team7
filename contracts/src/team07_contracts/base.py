"""공통 모델 설정과 공통 타입 (설계 Data Models > 공통 타입).

- JSON 키는 카멜 표기, Python 속성은 snake_case (D-02)
- 정의되지 않은 필드는 거부한다 (R4.6, R7.5, R9.6)
- 모델은 바꿀 수 없다. 변환 함수가 입력을 바꾸지 못하게 하려는 것이다 (R8.9)
- 실행 중 AWS·네트워크·파일을 부르지 않는다
"""
from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool, StrictInt, StringConstraints
from pydantic.alias_generators import to_camel

from .validation import CrossFieldError


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=False,  # snake_case 키는 정의되지 않은 필드로 본다
        frozen=True,
    )


class Part(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    BACKEND = "BACKEND"
    FRONTEND = "FRONTEND"
    COMMON = "COMMON"


def _check(pattern: str, rule: str = "pattern", extra=None):
    regex = re.compile(pattern)

    def check(value: str) -> str:
        if not regex.fullmatch(value) or (extra is not None and not extra(value)):
            raise CrossFieldError([("", rule)])
        return value

    return AfterValidator(check)


def _is_kst_datetime(v: str) -> bool:
    try:
        datetime.fromisoformat(v)
        return True
    except ValueError:
        return False


def _is_date(v: str) -> bool:
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _non_blank(max_len: int):
    """strip() 뒤 1자 이상, 원래 길이 max_len 이하. 값은 바꾸지 않는다."""

    def check(value: str) -> str:
        if not value.strip():
            raise CrossFieldError([("", "length")])
        if len(value) > max_len:
            raise CrossFieldError([("", "length")])
        return value

    return AfterValidator(check)


# 시각: 초 단위 + "+09:00" (R3.4, D-29)
KstDateTime = Annotated[str, _check(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", extra=_is_kst_datetime)]
IsoDate = Annotated[str, _check(r"\d{4}-\d{2}-\d{2}", extra=_is_date)]
YearMonth = Annotated[str, _check(r"\d{4}-(0[1-9]|1[0-2])")]
SidoCode = Annotated[str, _check(r"\d{2}")]
SigunguCode = Annotated[str, _check(r"\d{5}")]
Code20 = Annotated[str, _check(r"[0-9A-Za-z_]{1,20}")]
# ID 안에 '#' 금지 (docs/api.md §2, db-schema §6)
SafeId = Annotated[str, StringConstraints(min_length=1, max_length=200), _check(r"[^#]+")]
ExtractedBy = Literal["API", "LLM", "MANUAL"]
MoneyUnit = Literal["MANWON_YEAR", "MANWON_MONTH", "MANWON", "WON"]  # D-30

__all__ = [
    "ContractModel", "Part", "KstDateTime", "IsoDate", "YearMonth", "SidoCode", "SigunguCode",
    "Code20", "SafeId", "ExtractedBy", "MoneyUnit", "Money", "StrictInt", "StrictBool", "non_blank",
]

non_blank = _non_blank


class Money(ContractModel):
    amount: StrictInt
    unit: MoneyUnit
