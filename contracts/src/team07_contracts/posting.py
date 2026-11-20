"""Posting_For_Analysis와 변환 함수 (R8, D-09·D-10·D-34·D-39, docs/db-schema.md §3, docs/api.md §6.4).

소유 B, 소비 A·C. 필드 이름은 catalog SNAP# 스냅샷과 LATEST.isExpired를 따른다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Optional

from pydantic import Field, StrictBool, StringConstraints, field_validator, model_validator

from .base import Code20, ContractModel, ExtractedBy, IsoDate, KstDateTime, SafeId, SidoCode, SigunguCode, _check
from .validation import ContractValidationError, CrossFieldError, field_error


def _text(max_len: int):
    return Annotated[str, StringConstraints(min_length=1, max_length=max_len)]


Quote = Annotated[str, StringConstraints(min_length=1)]  # 원문 인용, 1자 이상


class Requirement(ContractModel):
    requirement_id: SafeId
    name: _text(200)
    kind: Literal["REQUIRED_SKILL", "PREFERRED_SKILL"]
    weight: float = Field(default=1.0, gt=0)  # 기본값 1.0 (D-10)
    source_quote: Quote
    extracted_by: ExtractedBy

    @field_validator("weight", mode="before")
    @classmethod
    def _number_only(cls, v: Any) -> Any:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CrossFieldError([("", "type")])
        return v


class EligibilityRule(ContractModel):
    rule_id: SafeId
    type: Annotated[str, _check(r"[A-Z_]{1,30}")]  # EDUCATION, CAREER, CERTIFICATE, MAJOR, ...
    value: Any
    source_quote: Quote
    extracted_by: ExtractedBy


class WorkRegion(ContractModel):
    sido: Optional[SidoCode] = None
    sigungu: Optional[SigunguCode] = None
    label: _text(50)
    unknown: StrictBool

    @model_validator(mode="after")
    def _sido_when_known(self):
        if not self.unknown and self.sido is None:
            raise CrossFieldError([("sido", "required")])
        return self


class PostingJob(ContractModel):
    name: _text(200)
    code: Optional[Code20] = None
    ncs_codes: Optional[list[Code20]] = None


SnapshotId = Annotated[str, _check(r"\d{8}-[0-9a-f]{8}")]  # {수집일}-{contentHash 앞 8자} (D-09)
HttpsUrl = Annotated[str, StringConstraints(max_length=2000), _check(r"https://\S+")]
SourceType = Annotated[str, _check(r"[A-Z0-9_]{1,30}")]


def _unique_ids(items, attr: str, field: str) -> None:
    seen, dup = set(), []
    for i, item in enumerate(items):
        value = getattr(item, attr)
        if value in seen:
            dup.append((f"{field}[{i}].{_camel(attr)}", "duplicate"))
        seen.add(value)
    if dup:
        raise CrossFieldError(dup)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.title() for w in rest)


class PostingForAnalysis(ContractModel):
    job_posting_id: SafeId
    snapshot_id: SnapshotId
    title: _text(200)
    organization: _text(100)
    job: PostingJob
    requirements: list[Requirement]
    eligibility_rules: list[EligibilityRule]
    career_type: Optional[str] = None
    education_min: Optional[Literal["NONE", "HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "DOCTOR"]] = None
    job_description: Optional[str] = None
    official_url: HttpsUrl
    checked_at: KstDateTime
    updated_at: KstDateTime
    work_region: WorkRegion
    closes_at: Optional[IsoDate] = None  # 상시 채용은 9999-12-31
    rolling: Optional[StrictBool] = None
    source_type: SourceType  # 예시 데이터는 DEMO
    is_expired: StrictBool  # D-34

    @model_validator(mode="after")
    def _unique(self):
        _unique_ids(self.requirements, "requirement_id", "requirements")
        _unique_ids(self.eligibility_rules, "rule_id", "eligibilityRules")
        return self


class JobRequirementView(ContractModel):
    """A §4.4 JobRequirement 형식으로 본 공고 (소유 B, 소비 A)."""

    job_posting_id: SafeId
    snapshot_id: SnapshotId
    title: _text(200)
    organization: _text(100)
    work_region: WorkRegion
    closes_at: Optional[IsoDate] = None
    official_url: HttpsUrl
    job_description: Optional[str] = None
    requirements: list[Requirement]
    eligibility_rules: list[EligibilityRule]
    checked_at: KstDateTime
    source_type: SourceType
    is_expired: StrictBool

    @model_validator(mode="after")
    def _unique(self):
        _unique_ids(self.requirements, "requirement_id", "requirements")
        return self


class InterviewJobContext(ContractModel):
    """C start_interview의 job 값 (소유 C, 소비 BACKEND, C §5.2)."""

    job: _text(50)


_VIEW_KEYS = ("jobPostingId", "snapshotId", "title", "organization", "workRegion", "closesAt", "officialUrl",
              "jobDescription", "requirements", "eligibilityRules", "checkedAt", "sourceType", "isExpired")


def to_job_requirement_view(posting: PostingForAnalysis) -> JobRequirementView:
    """요건 순서·kind·name·sourceQuote·requirementId·weight·extractedBy와 sourceType·isExpired를 그대로 옮긴다.

    마감된 공고도 오류 없이 변환한다 (R8.11). 입력은 frozen이라 바뀌지 않는다 (R8.9).
    """
    dumped = posting.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return JobRequirementView.model_validate({k: dumped[k] for k in _VIEW_KEYS if k in dumped})


def to_interview_job_context(posting: PostingForAnalysis) -> InterviewJobContext:
    """job.name이 1~50자(유니코드 문자 수)면 그대로 옮기고, 아니면 INVALID_INPUT (R8.6, R8.7)."""
    name = posting.job.name
    if not 1 <= len(name) <= 50:
        raise ContractValidationError("InterviewJobContext", [field_error("job.name", "length")])
    return InterviewJobContext.model_validate({"job": name})


_HASH_EXCLUDE = {"snapshotId", "checkedAt", "updatedAt", "isExpired"}


def compute_content_hash(posting: PostingForAnalysis) -> str:
    """스냅샷 ID·확인 시각·마감 여부를 뺀 내용의 sha256 hex 64자 [D-39 PROPOSED].

    B가 새 스냅샷이 필요한지 판단하고 snapshotId 뒤 8자를 만들 때 쓴다. 보내지 않은 선택 필드와 기본값은
    같은 값으로 정규화한다 (전체 필드를 직렬화).
    """
    data = {k: v for k, v in posting.model_dump(mode="json", by_alias=True).items() if k not in _HASH_EXCLUDE}
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
