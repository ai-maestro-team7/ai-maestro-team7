from mentoring.fit.gaps import classify_gaps
from mentoring.fit.models import RequirementMatch
from mentoring.models import EvidenceLevel


def req(requirement_id, category, level):
    return RequirementMatch(
        requirement_id=requirement_id,
        category=category,
        evidence_level=level,
    )


def test_four_way_classification_and_priority():
    result = classify_gaps([
        req("exp-partial", "EXPERIENCE", EvidenceLevel.PARTIAL),
        req("preferred-strength", "PREFERRED", EvidenceLevel.EVIDENCED),
        req("required-unknown", "REQUIRED", EvidenceLevel.NOT_FOUND),
        req("preferred-gap", "PREFERRED", EvidenceLevel.USER_CONFIRMED_GAP),
        req("required-partial", "REQUIRED", EvidenceLevel.SELF_REPORTED),
        req("required-gap", "REQUIRED", EvidenceLevel.USER_CONFIRMED_GAP),
    ])
    assert [item.requirement_id for item in result.confirmed_strengths] == ["preferred-strength"]
    assert [item.requirement_id for item in result.partial_evidence] == ["required-partial", "exp-partial"]
    assert [item.requirement_id for item in result.verification_tasks] == ["required-unknown"]
    assert [item.requirement_id for item in result.confirmed_gaps] == ["required-gap", "preferred-gap"]


def test_unknown_is_question_not_mandatory_learning():
    result = classify_gaps([req("unknown", "REQUIRED", EvidenceLevel.NOT_FOUND)])
    assert result.verification_tasks[0].must_learn is False
    assert result.confirmed_gaps == []


def test_eligibility_failure_overrides_evidence_and_is_mandatory():
    result = classify_gaps(
        [req("degree", "REQUIRED", EvidenceLevel.EVIDENCED)],
        eligibility_failures={"degree"},
    )
    assert result.confirmed_strengths == []
    assert result.confirmed_gaps[0].requirement_id == "degree"
    assert result.confirmed_gaps[0].must_learn is True


def test_duplicate_requirement_is_classified_once():
    result = classify_gaps([
        req("same", "REQUIRED", EvidenceLevel.NOT_FOUND),
        req("same", "PREFERRED", EvidenceLevel.EVIDENCED),
    ])
    all_ids = [
        item.requirement_id
        for values in (
            result.confirmed_strengths,
            result.partial_evidence,
            result.verification_tasks,
            result.confirmed_gaps,
        )
        for item in values
    ]
    assert all_ids == ["same"]
