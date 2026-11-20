"""역량 추출 모델 출력의 고정 스키마 (Requirement 6 기준 4).
모델이 낸 값은 이 형식을 통과해도 아직 사실이 아니다. 근거 검증을 거친 것만 프로필에 들어간다.
"""
from pydantic import Field

from .base import MentoringModel
from .enums import EvidenceLevel


class QuoteRef(MentoringModel):
    quoted_text: str = Field(min_length=1)
    start_char: int | None = None
    end_char: int | None = None


class ExtractedSkill(MentoringModel):
    name: str = Field(min_length=1)
    normalized_name: str | None = None
    ncs_unit_code: str | None = None
    evidence_level: EvidenceLevel
    quotes: list[QuoteRef] = Field(default_factory=list)


class ExtractedEntry(MentoringModel):
    name: str = Field(min_length=1)
    summary: str | None = None
    period: str | None = None
    quotes: list[QuoteRef] = Field(default_factory=list)


class ExtractedCertificate(MentoringModel):
    name: str = Field(min_length=1)
    quotes: list[QuoteRef] = Field(default_factory=list)


class ExtractionOutput(MentoringModel):
    skills: list[ExtractedSkill] = Field(default_factory=list)
    projects: list[ExtractedEntry] = Field(default_factory=list)
    experiences: list[ExtractedEntry] = Field(default_factory=list)
    certificates: list[ExtractedCertificate] = Field(default_factory=list)
    needs_confirmation: list[str] = Field(default_factory=list)
