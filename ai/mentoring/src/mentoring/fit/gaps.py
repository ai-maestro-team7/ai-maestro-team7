"""Deterministic four-way requirement gap classification (F-04)."""
from mentoring.models import EvidenceLevel

from .models import GapItem, GapResult, RequirementMatch

_CATEGORY_PRIORITY = {"REQUIRED": 0, "PREFERRED": 1, "EXPERIENCE": 2}


def classify_gaps(
    requirements: list[RequirementMatch],
    *,
    eligibility_failures: set[str] = frozenset(),
) -> GapResult:
    buckets: dict[str, list[tuple[int, GapItem]]] = {
        "confirmed_strengths": [],
        "partial_evidence": [],
        "verification_tasks": [],
        "confirmed_gaps": [],
    }
    seen: set[str] = set()
    for index, requirement in enumerate(requirements):
        if requirement.requirement_id in seen:
            continue
        seen.add(requirement.requirement_id)
        confirmed_gap = (
            requirement.requirement_id in eligibility_failures
            or requirement.evidence_level == EvidenceLevel.USER_CONFIRMED_GAP
        )
        item = GapItem(
            requirement_id=requirement.requirement_id,
            category=requirement.category,
            evidence_level=requirement.evidence_level,
            evidence_ids=list(requirement.evidence_ids),
            must_learn=confirmed_gap,
        )
        if confirmed_gap:
            bucket = "confirmed_gaps"
        elif requirement.evidence_level == EvidenceLevel.EVIDENCED:
            bucket = "confirmed_strengths"
        elif requirement.evidence_level in {EvidenceLevel.PARTIAL, EvidenceLevel.SELF_REPORTED}:
            bucket = "partial_evidence"
        else:
            bucket = "verification_tasks"
        buckets[bucket].append((index, item))

    ordered = {}
    for name, values in buckets.items():
        values.sort(key=lambda pair: (_CATEGORY_PRIORITY[pair[1].category], pair[0]))
        ordered[name] = [item for _, item in values]
    return GapResult(**ordered)
