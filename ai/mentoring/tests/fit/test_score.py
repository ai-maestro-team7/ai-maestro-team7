from decimal import Decimal

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from mentoring.fit.models import RequirementMatch
from mentoring.fit.score import calculate_fit, load_fit_config
from mentoring.models import EvidenceLevel


def requirement(requirement_id, category="REQUIRED", level=EvidenceLevel.EVIDENCED, weight="1"):
    return RequirementMatch(
        requirement_id=requirement_id,
        category=category,
        evidence_level=level,
        weight=Decimal(weight),
    )


def test_ut06_missing_categories_are_renormalized():
    score = calculate_fit([
        requirement("required", "REQUIRED", EvidenceLevel.EVIDENCED),
        requirement("experience", "EXPERIENCE", EvidenceLevel.NOT_FOUND),
    ])
    assert score.fit_score == 88
    assert score.potential_upper_bound == 100
    assert set(score.category_breakdown) == {"REQUIRED", "EXPERIENCE"}


def test_ut07_no_requirements_has_no_score():
    score = calculate_fit([])
    assert score.status == "INSUFFICIENT_REQUIREMENTS"
    assert score.fit_score is None and score.potential_upper_bound is None


def test_ut08_same_input_is_deterministic():
    values = [
        requirement("a", "REQUIRED", EvidenceLevel.PARTIAL),
        requirement("b", "PREFERRED", EvidenceLevel.SELF_REPORTED),
    ]
    assert len({calculate_fit(values).model_dump_json() for _ in range(100)}) == 1


def test_not_found_has_zero_lower_and_full_upper():
    score = calculate_fit([requirement("unknown", level=EvidenceLevel.NOT_FOUND)])
    assert (score.fit_score, score.potential_upper_bound) == (0, 100)


def test_user_confirmed_gap_has_zero_upper_too():
    score = calculate_fit([requirement("gap", level=EvidenceLevel.USER_CONFIRMED_GAP)])
    assert (score.fit_score, score.potential_upper_bound) == (0, 0)


def test_round_half_up_boundary():
    score = calculate_fit([
        requirement("full", level=EvidenceLevel.EVIDENCED, weight="1"),
        requirement("partial", level=EvidenceLevel.PARTIAL, weight="99"),
    ])
    assert score.fit_score == 51  # exact lower bound is 0.505


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["REQUIRED", "PREFERRED", "EXPERIENCE"]),
            st.sampled_from(list(EvidenceLevel)),
            st.integers(min_value=1, max_value=100),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_bounds_always_ordered_and_in_range(values):
    requirements = [
        requirement(str(index), category, level, str(weight))
        for index, (category, level, weight) in enumerate(values)
    ]
    score = calculate_fit(requirements)
    assert 0 <= score.fit_score <= score.potential_upper_bound <= 100


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data["categoryWeights"].update(REQUIRED=0.8),
        lambda data: data["evidenceLowerBounds"].update(PARTIAL=1.1),
        lambda data: data["evidenceUpperBounds"].update(PARTIAL=0.4),
    ],
)
def test_invalid_config_is_rejected(change):
    data = {
        "scorePolicyVersion": "fit-v1",
        "categoryWeights": {"REQUIRED": 0.7, "PREFERRED": 0.2, "EXPERIENCE": 0.1},
        "evidenceLowerBounds": {
            "EVIDENCED": 1.0,
            "PARTIAL": 0.5,
            "SELF_REPORTED": 0.25,
            "NOT_FOUND": 0.0,
            "USER_CONFIRMED_GAP": 0.0,
        },
        "evidenceUpperBounds": {
            "EVIDENCED": 1.0,
            "PARTIAL": 0.5,
            "SELF_REPORTED": 0.25,
            "NOT_FOUND": 1.0,
            "USER_CONFIRMED_GAP": 0.0,
        },
    }
    change(data)
    with pytest.raises((ValidationError, ValueError)):
        load_fit_config(data=data)
