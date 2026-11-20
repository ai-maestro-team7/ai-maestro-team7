"""Pure, deterministic fit-score calculation (개발계획서1 F-02)."""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mentoring.models import EvidenceLevel

from .models import CategoryBreakdown, FitScore, RequirementCategory, RequirementMatch


class FitConfig(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: value.split("_")[0] + "".join(
        part.capitalize() for part in value.split("_")[1:]
    ), populate_by_name=True)

    score_policy_version: str
    category_weights: dict[RequirementCategory, Decimal]
    evidence_lower_bounds: dict[EvidenceLevel, Decimal]
    evidence_upper_bounds: dict[EvidenceLevel, Decimal]

    @model_validator(mode="after")
    def _valid_policy(self):
        categories = {"REQUIRED", "PREFERRED", "EXPERIENCE"}
        levels = set(EvidenceLevel)
        if set(self.category_weights) != categories:
            raise ValueError("categoryWeights must define all categories")
        if sum(self.category_weights.values(), Decimal("0")) != Decimal("1"):
            raise ValueError("categoryWeights must sum to 1")
        if set(self.evidence_lower_bounds) != levels or set(self.evidence_upper_bounds) != levels:
            raise ValueError("evidence bounds must define every EvidenceLevel")
        for value in [*self.category_weights.values(), *self.evidence_lower_bounds.values(), *self.evidence_upper_bounds.values()]:
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError("fit policy values must be between 0 and 1")
        for level in levels:
            if self.evidence_lower_bounds[level] > self.evidence_upper_bounds[level]:
                raise ValueError("evidence lower bound must not exceed upper bound")
        return self


def load_fit_config(*, path: Path | None = None, data: dict[str, Any] | None = None) -> FitConfig:
    if data is None:
        source = path or Path(__file__).with_name("fit_config.json")
        data = json.loads(source.read_text(encoding="utf-8"))
    return FitConfig.model_validate(data)


def _weighted_average(requirements: list[RequirementMatch], values: dict[EvidenceLevel, Decimal]) -> Decimal:
    total_weight = sum((item.weight for item in requirements), Decimal("0"))
    return sum((item.weight * values[item.evidence_level] for item in requirements), Decimal("0")) / total_weight


def _percent(value: Decimal) -> int:
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_fit(requirements: list[RequirementMatch]) -> FitScore:
    """Return evidence-based match bounds; this score is not a hiring probability."""
    config = load_fit_config()
    if not requirements:
        return FitScore(
            status="INSUFFICIENT_REQUIREMENTS",
            score_policy_version=config.score_policy_version,
        )

    grouped: dict[RequirementCategory, list[RequirementMatch]] = {}
    for requirement in requirements:
        grouped.setdefault(requirement.category, []).append(requirement)

    active_weight = sum((config.category_weights[category] for category in grouped), Decimal("0"))
    lower = Decimal("0")
    upper = Decimal("0")
    breakdown = {}
    for category, items in grouped.items():
        category_lower = _weighted_average(items, config.evidence_lower_bounds)
        category_upper = _weighted_average(items, config.evidence_upper_bounds)
        normalized_weight = config.category_weights[category] / active_weight
        lower += normalized_weight * category_lower
        upper += normalized_weight * category_upper
        breakdown[category] = CategoryBreakdown(
            lower_bound=float(category_lower),
            upper_bound=float(category_upper),
            requirement_count=len(items),
        )

    return FitScore(
        fit_score=_percent(lower),
        potential_upper_bound=_percent(upper),
        status="SCORED",
        score_policy_version=config.score_policy_version,
        category_breakdown=breakdown,
    )
