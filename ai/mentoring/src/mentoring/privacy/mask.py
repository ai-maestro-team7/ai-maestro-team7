"""규칙 기반 개인정보 가리기.

라벨 없이 등장하는 사람 이름은 오탐 위험이 커서 이 모듈의 탐지 범위에 포함하지 않는다.
반환하는 모든 위치는 입력 문자열 기준의 반열린 구간 ``[start, end)`` 이다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MaskKind = Literal["PHONE", "EMAIL", "RRN", "ADDRESS", "NAME"]


class MaskedSpan(BaseModel):
    """가려진 입력 문자열의 반열린 구간."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: MaskKind


class MaskResult(BaseModel):
    """길이를 유지한 마스킹 결과와 가려진 위치."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    masked_text: str
    spans: list[MaskedSpan]


_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_RRN = re.compile(r"(?<!\d)\d{6}[ -]?[0-9]\d{6}(?!\d)")
_PHONE = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+82[ .-]?(?:0)?10|010)[ .-]?\d{3,4}[ .-]?(?:\d{4}|X{4})"
    r"|02[ .-]?\d{3,4}[ .-]?(?:\d{4}|X{4})"
    r"|0(?:3[1-3]|4[1-4]|5[1-5]|6[1-4])[ .-]?\d{3,4}[ .-]?(?:\d{4}|X{4})"
    r")(?!\d)",
    re.IGNORECASE,
)

_SIDO = (
    r"(?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
    r"울산광역시|세종특별자치시|제주특별자치도|강원특별자치도|전북특별자치도|"
    r"경기도|충청북도|충청남도|전라남도|경상북도|경상남도)"
)
_SIGUNGU = r"[가-힣0-9]+(?:시|군|구)"
_ROAD_ADDRESS = re.compile(
    rf"{_SIDO}\s+{_SIGUNGU}(?:\s+[가-힣0-9]+(?:읍|면))?\s+"
    r"[가-힣0-9·.-]+(?:로|길)(?:\d+번길)?\s+\d+(?:-\d+)?"
)
_JIBUN_ADDRESS = re.compile(
    rf"{_SIDO}\s+{_SIGUNGU}(?:\s+[가-힣0-9]+(?:읍|면))?\s+"
    r"[가-힣0-9]+동\s+\d+(?:-\d+)?(?:번지)?"
)
_LABELED_NAME = re.compile(r"(?im)(?:이름|성명|name)\s*[:：]\s*(?P<value>[^\r\n]+)")

_PATTERNS: tuple[tuple[MaskKind, re.Pattern[str]], ...] = (
    ("EMAIL", _EMAIL),
    ("RRN", _RRN),
    ("PHONE", _PHONE),
    ("ADDRESS", _ROAD_ADDRESS),
    ("ADDRESS", _JIBUN_ADDRESS),
)
_KIND_PRIORITY = {"RRN": 0, "EMAIL": 1, "PHONE": 2, "ADDRESS": 3, "NAME": 4}


def _matches(text: str) -> list[tuple[int, int, MaskKind]]:
    found: list[tuple[int, int, MaskKind]] = []
    for kind, pattern in _PATTERNS:
        found.extend((match.start(), match.end(), kind) for match in pattern.finditer(text))
    for match in _LABELED_NAME.finditer(text):
        start, end = match.span("value")
        while start < end and text[start].isspace() and text[start] not in "\r\n":
            start += 1
        while end > start and text[end - 1].isspace() and text[end - 1] not in "\r\n":
            end -= 1
        if start < end:
            found.append((start, end, "NAME"))
    return sorted(found, key=lambda item: (item[0], item[1], _KIND_PRIORITY[item[2]]))


def _merge(matches: list[tuple[int, int, MaskKind]]) -> list[MaskedSpan]:
    merged: list[MaskedSpan] = []
    for start, end, kind in matches:
        if not merged or start >= merged[-1].end:
            merged.append(MaskedSpan(start=start, end=end, kind=kind))
            continue
        previous = merged[-1]
        chosen_kind = min((previous.kind, kind), key=_KIND_PRIORITY.__getitem__)
        merged[-1] = MaskedSpan(start=previous.start, end=max(previous.end, end), kind=chosen_kind)
    return merged


def mask_pii(text: str) -> MaskResult:
    """알려진 개인정보 구간을 같은 길이의 ``*``로 바꾼다.

    줄바꿈은 탐지 패턴에 포함되지 않으며 겹치는 탐지 결과는 하나의 구간으로 합친다.
    """

    spans = _merge(_matches(text))
    if not spans:
        return MaskResult(masked_text=text, spans=[])
    characters = list(text)
    for span in spans:
        for index in range(span.start, span.end):
            if characters[index] not in "\r\n":
                characters[index] = "*"
    return MaskResult(masked_text="".join(characters), spans=spans)


def overlaps_mask(start: int, end: int, spans: list[MaskedSpan]) -> bool:
    """반열린 근거 구간이 마스킹 구간과 하나라도 겹치는지 반환한다."""

    if start < 0 or end <= start:
        return False
    return any(start < span.end and end > span.start for span in spans)
