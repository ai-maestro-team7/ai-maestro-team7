"""텍스트 도구의 테스트용 가짜 (#41 정규화, #42 개인정보 가리기, #43 근거 검증과 같은 모양).
실제 모듈이 들어오면 `load_text_tools()`가 그쪽을 쓴다. 여기 규칙은 core 동작을 시험할 만큼만 단순하게 둔다.
"""
import re
import unicodedata
from dataclasses import dataclass

from mentoring.text_tools import TextTools


@dataclass
class Span:
    start: int
    end: int
    kind: str


@dataclass
class Masked:
    masked_text: str
    spans: list[Span]


@dataclass
class Check:
    status: str
    start: int | None
    end: int | None


@dataclass
class Fact:
    kind: str
    value: str


def normalize(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


_PII = [("PHONE", re.compile(r"01[0-9]-\d{3,4}-\d{4}")), ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"))]


def mask_pii(text: str) -> Masked:
    chars = list(text)
    spans: list[Span] = []
    for kind, pattern in _PII:
        for m in pattern.finditer(text):
            spans.append(Span(m.start(), m.end(), kind))
            for i in range(m.start(), m.end()):
                if chars[i] != "\n":
                    chars[i] = "*"
    return Masked("".join(chars), sorted(spans, key=lambda s: s.start))


def overlaps_mask(start: int, end: int, spans: list) -> bool:
    return any(s.start < end and start < s.end for s in spans)


def check_evidence(source: str, quote: str, start: int | None, end: int | None) -> Check:
    if not quote or not quote.strip():
        return Check("NOT_FOUND", None, None)
    if start is not None and end is not None and 0 <= start < end <= len(source) and source[start:end] == quote:
        return Check("EXACT", start, end)
    found = [m.start() for m in re.finditer(re.escape(quote), source)]
    if not found:
        return Check("NOT_FOUND", None, None)
    best = min(found, key=lambda i: (abs(i - start), i)) if start is not None else found[0]
    return Check("RELOCATED", best, best + len(quote))


_NUMBER = re.compile(r"\d[\d,.]*\s*%?")


def _norm_number(value: str) -> str:
    return re.sub(r"[\s,]", "", value).rstrip(".")


def find_unsupported_facts(source: str, generated: str) -> list[Fact]:
    known = {_norm_number(m.group()) for m in _NUMBER.finditer(source)}
    compact_source = re.sub(r"[\s,]", "", source)
    out = []
    for m in _NUMBER.finditer(generated):
        value = _norm_number(m.group())
        if value and value not in known and value not in compact_source:
            out.append(Fact("NUMBER", value))
    return out


def fake_text_tools() -> TextTools:
    return TextTools(normalize=normalize, mask_pii=mask_pii, overlaps_mask=overlaps_mask,
                     check_evidence=check_evidence, find_unsupported_facts=find_unsupported_facts)
