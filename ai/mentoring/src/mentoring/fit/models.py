"""Contracts shared by fit scoring and gap classification."""
from decimal import Decimal
from typing import Literal

from pydantic import Field

from mentoring.models import EvidenceLevel
from mentoring.models.base import MentoringModel

RequirementCategory = Literal["REQUIRED", "PREFERRED", "EXPERIENCE"]


class RequirementMatch(MentoringModel):
    requirement_id: str
    category: RequirementCategory
    weight: Decimal = Field(default=Decimal("1.0"), gt=0)
    evidence_level: EvidenceLevel
    evidence_ids: list[str] = Field(default_factory=list)


class CategoryBreakdown(MentoringModel):
    lower_bound: float = Field(ge=0, le=1)
    upper_bound: float = Field(ge=0, le=1)
    requirement_count: int = Field(ge=1)


class FitScore(MentoringModel):
    fit_score: int | None = Field(default=None, ge=0, le=100)
    potential_upper_bound: int | None = Field(default=None, ge=0, le=100)
    status: Literal["SCORED", "INSUFFICIENT_REQUIREMENTS"]
    score_policy_version: str
    category_breakdown: dict[RequirementCategory, CategoryBreakdown] = Field(default_factory=dict)


class GapItem(MentoringModel):
    requirement_id: str
    category: RequirementCategory
    evidence_level: EvidenceLevel
    evidence_ids: list[str] = Field(default_factory=list)
    must_learn: bool = False


class GapResult(MentoringModel):
    confirmed_strengths: list[GapItem] = Field(default_factory=list)
    partial_evidence: list[GapItem] = Field(default_factory=list)
    verification_tasks: list[GapItem] = Field(default_factory=list)
    confirmed_gaps: list[GapItem] = Field(default_factory=list)
