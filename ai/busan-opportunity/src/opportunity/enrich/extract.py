"""요건 추출 (B-02). 공고 텍스트를 `<posting>` 태그로 감싸 데이터로만 넘긴다.

- LLM 출력은 JSON이고 `ExtractOutput`으로 검사한다. 형식이 틀리면 한 번만 다시 시도하고, 또 틀리면 FAILED.
- quote가 원문에 실제로 없으면 그 항목을 버린다 (원문에 없는 요건 0건, 개발계획서2 §7.3).
- API·MANUAL이 만든 값과 마감일·근무지·급여는 덮어쓰지 않는다 (§3.5). 채운 필드는 extractedBy=LLM.
"""

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..deps import Deps
from ..models.enums import (
    CareerType,
    EducationLevel,
    ExtractedBy,
    ExtractStatus,
    RemoteWork,
    RequirementKind,
    RuleType,
)
from ..models.posting import EligibilityRule, PostingSnapshot, Requirement
from . import prompts

# 형식 검사 실패 시 다시 시도는 한 번만 한다 (개발계획서2 B-02). 처음 + 다시 = 2
MAX_ATTEMPTS = 2
# 마감일·근무지·급여는 이 모듈이 아예 쓰지 않는다. 주인이 아래면 다른 필드도 덮어쓰지 않는다
KEEP_OWNERS = (ExtractedBy.API, ExtractedBy.MANUAL)

_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------- LLM 출력 계약
class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class NamedQuote(_Out):
    name: str = Field(min_length=1)
    quote: str


class MajorsOut(_Out):
    values: list[str] = Field(min_length=1)
    quote: str


class EducationOut(_Out):
    value: EducationLevel
    quote: str


class CareerOut(_Out):
    value: CareerType
    min_years: int | None = Field(default=None, alias="minYears", ge=0)
    quote: str


class RemoteOut(_Out):
    value: RemoteWork
    quote: str


class ExtractOutput(_Out):
    """키는 모두 있어야 한다. 못 찾은 값은 null이나 빈 배열로 와야 하고, 키가 빠지면 형식 오류다."""

    required: list[NamedQuote]
    preferred: list[NamedQuote]
    certificates: list[NamedQuote]
    majors: MajorsOut | None
    education_min: EducationOut | None = Field(alias="educationMin")
    career_type: CareerOut | None = Field(alias="careerType")
    remote_work: RemoteOut | None = Field(alias="remoteWork")
    selection_steps: list[NamedQuote] = Field(alias="selectionSteps")
    documents: list[NamedQuote]


class ExtractFormatError(ValueError):
    """LLM 출력이 JSON이 아니거나 스키마에 맞지 않는다."""


# ---------------------------------------------------------------- 원문
def source_text(snapshot: PostingSnapshot, raw_text: str | None = None) -> str:
    """LLM에 넘기고 quote를 대조할 원문. 제목, 업무 설명, 공고 원문 순서다."""
    parts = [snapshot.title, snapshot.job_description or "", raw_text or ""]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _norm(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def quote_in_source(quote: str | None, source: str) -> bool:
    """공백 차이만 무시하고 원문에 글자 그대로 있는지 본다."""
    if not quote or not quote.strip():
        return False
    return _norm(quote) in _norm(source)


def parse_output(reply: str) -> ExtractOutput:
    """답에서 JSON 객체를 꺼내 검사한다. 코드 블록으로 감싸 와도 받는다."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        raise ExtractFormatError("JSON 객체가 없다")
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError as e:
        raise ExtractFormatError(f"JSON이 아니다: {e.msg}") from e
    if not isinstance(data, dict):
        raise ExtractFormatError("JSON 객체가 아니다")
    try:
        return ExtractOutput.model_validate(data)
    except ValidationError as e:
        raise ExtractFormatError(f"스키마에 맞지 않는다: {e.error_count()}건") from e


# ---------------------------------------------------------------- 결과
@dataclass
class ExtractResult:
    snapshot: PostingSnapshot
    status: ExtractStatus
    attempts: int = 0
    dropped: list[str] = field(default_factory=list)  # quote가 원문에 없어 버린 항목 이름
    prompt_version: str = prompts.EXTRACT_PROMPT_VERSION


def _keep(items: list[NamedQuote], source: str, dropped: list[str]) -> list[NamedQuote]:
    kept, seen = [], set()
    for item in items:
        if not quote_in_source(item.quote, source):
            dropped.append(item.name)
            continue
        key = _norm(item.name).lower()
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept


def _one(item, source: str, dropped: list[str], label: str):
    if item is None:
        return None
    if not quote_in_source(item.quote, source):
        dropped.append(label)
        return None
    return item


def _owned(snapshot: PostingSnapshot, name: str) -> bool:
    return snapshot.extracted_by.get(name) in KEEP_OWNERS


def _career_value(career: CareerOut) -> dict:
    value = {"type": career.value.value}
    if career.value == CareerType.EXPERIENCED and career.min_years is not None:
        value["minYears"] = career.min_years
    return value


def apply_output(snapshot: PostingSnapshot, out: ExtractOutput, source: str) -> tuple[PostingSnapshot, list[str]]:
    """검사를 통과한 출력을 스냅샷에 넣는다. 원문 대조에 실패한 항목은 버린다."""
    dropped: list[str] = []
    required = _keep(out.required, source, dropped)
    preferred = _keep(out.preferred, source, dropped)
    certificates = _keep(out.certificates, source, dropped)
    steps = _keep(out.selection_steps, source, dropped)
    documents = _keep(out.documents, source, dropped)
    majors = _one(out.majors, source, dropped, "majors")
    education = _one(out.education_min, source, dropped, "educationMin")
    career = _one(out.career_type, source, dropped, "careerType")
    remote = _one(out.remote_work, source, dropped, "remoteWork")

    update: dict = {}
    by = dict(snapshot.extracted_by)

    def put(name: str, attr: str, value) -> None:
        if value in (None, []) or _owned(snapshot, name):
            return
        update[attr] = value
        by[name] = ExtractedBy.LLM

    reqs = [Requirement(requirement_id=f"req-{i + 1}", name=r.name.strip(), kind=RequirementKind.REQUIRED_SKILL,
                        source_quote=r.quote.strip()) for i, r in enumerate(required)]
    reqs += [Requirement(requirement_id=f"pref-{i + 1}", name=r.name.strip(), kind=RequirementKind.PREFERRED_SKILL,
                         source_quote=r.quote.strip()) for i, r in enumerate(preferred)]
    put("requirements", "requirements", reqs)
    put("educationMin", "education_min", education.value if education else None)
    put("careerType", "career_type", career.value if career else None)
    put("remoteWork", "remote_work", remote.value if remote else None)
    put("selectionSteps", "selection_steps", [s.name.strip() for s in steps])
    put("documents", "documents", [d.name.strip() for d in documents])
    if not _owned(snapshot, "eligibilityRules"):
        put("eligibilityRules", "eligibility_rules", _rules(snapshot, education, career, certificates, majors))
    update["extracted_by"] = by
    update["extract_status"] = ExtractStatus.DONE
    return snapshot.model_copy(update=update), dropped


def _rules(snapshot: PostingSnapshot, education, career, certificates, majors) -> list[EligibilityRule]:
    """LLM이 찾은 조건으로 규칙을 만든다. 값의 주인이 API·MANUAL인 종류는 원래 규칙을 둔다."""
    keep_types = set()
    if _owned(snapshot, "educationMin"):
        keep_types.add(RuleType.EDUCATION)
    if _owned(snapshot, "careerType"):
        keep_types.add(RuleType.CAREER)
    found: list[EligibilityRule] = []
    if education is not None and RuleType.EDUCATION not in keep_types:
        found.append(EligibilityRule(rule_id="rule-edu", type=RuleType.EDUCATION, value=education.value.value,
                                     source_quote=education.quote.strip()))
    if career is not None and RuleType.CAREER not in keep_types:
        found.append(EligibilityRule(rule_id="rule-career", type=RuleType.CAREER, value=_career_value(career),
                                     source_quote=career.quote.strip()))
    for i, cert in enumerate(certificates):
        found.append(EligibilityRule(rule_id=f"rule-cert-{i + 1}", type=RuleType.CERTIFICATE, value=cert.name.strip(),
                                     source_quote=cert.quote.strip()))
    values = [m.strip() for m in majors.values if m.strip()] if majors is not None else []
    if values:
        found.append(EligibilityRule(rule_id="rule-major", type=RuleType.MAJOR, value=values,
                                     source_quote=majors.quote.strip()))
    if not found:
        return []  # 새로 찾은 조건이 없으면 원래 규칙을 지우지 않는다
    return [r for r in snapshot.eligibility_rules if r.type in keep_types] + found


def extract_requirements(deps: Deps, snapshot: PostingSnapshot, *, raw_text: str | None = None) -> ExtractResult:
    """LLM으로 요건을 뽑아 스냅샷에 넣는다. 형식이 두 번 틀리면 extractStatus=FAILED."""
    if deps.llm is None:
        return ExtractResult(snapshot, snapshot.extract_status)
    source = source_text(snapshot, raw_text)
    system, user = prompts.EXTRACT_SYSTEM, prompts.extract_user(source)
    attempts = 0
    for _ in range(MAX_ATTEMPTS):
        attempts += 1
        try:
            out = parse_output(deps.llm.invoke(system, user))
        except Exception:  # 형식 오류와 Bedrock 오류 모두 이번 시도의 실패로 센다
            continue
        updated, dropped = apply_output(snapshot, out, source)
        return ExtractResult(updated, ExtractStatus.DONE, attempts, dropped)
    failed = snapshot.model_copy(update={"extract_status": ExtractStatus.FAILED})
    return ExtractResult(failed, ExtractStatus.FAILED, attempts)
