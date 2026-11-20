"""근거 인용 위치와 생성 문장의 정량 사실을 검증한다.

호출자는 ``source``와 ``generated``를 미리 같은 방식으로 정규화해야 한다. 이 모듈은
문자 위치가 바뀌지 않도록 입력을 정규화하지 않는다. 한글 수사(예: "세 번"), 고유명사,
자격 이름 검사는 범위 밖이다.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["EXACT", "RELOCATED", "NOT_FOUND"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)


class UnsupportedFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["NUMBER", "PERCENT", "DATE", "PERIOD"]
    value: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


def check_evidence(source: str, quote: str, start: int | None, end: int | None) -> EvidenceCheck:
    """인용 위치를 확인하고 틀린 위치는 같은 원문 안에서 다시 찾는다."""

    if not quote or not quote.strip():
        return EvidenceCheck(status="NOT_FOUND")
    if (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start <= end <= len(source)
        and source[start:end] == quote
    ):
        return EvidenceCheck(status="EXACT", start=start, end=end)

    positions: list[int] = []
    cursor = 0
    while True:
        position = source.find(quote, cursor)
        if position < 0:
            break
        positions.append(position)
        cursor = position + 1
    if not positions:
        return EvidenceCheck(status="NOT_FOUND")
    if isinstance(start, int) and not isinstance(start, bool):
        position = min(positions, key=lambda candidate: (abs(candidate - start), candidate))
    else:
        position = positions[0]
    return EvidenceCheck(status="RELOCATED", start=position, end=position + len(quote))


_PERCENT = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?\s*(?:%|퍼센트)")
_DATE_NUMERIC = re.compile(r"(?<!\d)(?:20)?\d{2}[./-](?:0?[1-9]|1[0-2])(?!\d)")
_DATE_KOREAN = re.compile(r"(?<!\d)(?:20)?\d{2}년\s*(?:0?[1-9]|1[0-2])월")
_PERIOD = re.compile(
    r"(?<![\d.])(?:\d[\d,]*\s*년(?:\s*\d[\d,]*\s*개월)?|\d[\d,]*\s*개월|\d[\d,]*\s*주)(?![\d.])"
)
_NUMBER = re.compile(
    r"(?<![\d.])\d[\d,]*(?:\.\d+)?\s*(?:만원|시간|명|건|개|회|원|억|배|점)"
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PERCENT", _PERCENT),
    ("DATE", _DATE_KOREAN),
    ("DATE", _DATE_NUMERIC),
    ("PERIOD", _PERIOD),
    ("NUMBER", _NUMBER),
)


def _number(value: str) -> str:
    raw = value.replace(",", "")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return raw
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _normalize(kind: str, raw: str) -> str:
    compact = re.sub(r"\s+", "", raw)
    if kind == "PERCENT":
        number = re.match(r"\d[\d,]*(?:\.\d+)?", compact)
        return f"{_number(number.group(0))}%"
    if kind == "DATE":
        match = re.match(r"(?P<year>(?:20)?\d{2})(?:[./-]|년)(?P<month>\d{1,2})", compact)
        year = match.group("year")
        if len(year) == 2:
            year = f"20{year}"
        return f"{year}-{int(match.group('month')):02d}"
    if kind == "PERIOD":
        return compact.replace(",", "")
    match = re.match(r"(?P<number>\d[\d,]*(?:\.\d+)?)(?P<unit>.+)", compact)
    return f"{_number(match.group('number'))}{match.group('unit')}"


def _facts(text: str) -> list[UnsupportedFact]:
    facts: list[UnsupportedFact] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            facts.append(
                UnsupportedFact(kind=kind, value=_normalize(kind, match.group()), start=start, end=end)
            )
            occupied.append((start, end))
    return sorted(facts, key=lambda fact: (fact.start, fact.end))


def find_unsupported_facts(source: str, generated: str) -> list[UnsupportedFact]:
    """생성 문장에만 등장하는 지원되지 않은 정량 사실을 위치와 함께 반환한다."""

    supported = {(fact.kind, fact.value) for fact in _facts(source)}
    return [fact for fact in _facts(generated) if (fact.kind, fact.value) not in supported]
