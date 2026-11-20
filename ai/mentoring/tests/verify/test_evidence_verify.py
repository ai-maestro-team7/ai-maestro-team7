from __future__ import annotations

from hypothesis import given, strategies as st

from mentoring.verify import check_evidence, find_unsupported_facts


def test_exact_evidence() -> None:
    source = "가상 프로젝트에서 데이터 1,200건을 정제했다."
    quote = "데이터 1,200건을 정제"
    start = source.index(quote)

    result = check_evidence(source, quote, start, start + len(quote))

    assert result.status == "EXACT"
    assert (result.start, result.end) == (start, start + len(quote))


def test_relocates_to_nearest_occurrence_and_prefers_earlier_tie() -> None:
    source = "분석 경험 / 분석 경험 / 분석 경험"

    result = check_evidence(source, "분석 경험", 9, 10)

    assert result.status == "RELOCATED"
    assert result.start == 8


def test_relocates_to_first_when_start_is_none() -> None:
    result = check_evidence("문서 작성과 문서 검토", "문서", None, None)

    assert result.status == "RELOCATED"
    assert (result.start, result.end) == (0, 2)


def test_not_found_for_blank_missing_or_out_of_range_quote() -> None:
    assert check_evidence("원문", " ", 0, 1).status == "NOT_FOUND"
    assert check_evidence("원문", "다른 문구", 99, 100).status == "NOT_FOUND"


def test_finds_unsupported_number_percent_date_and_period() -> None:
    source = "2023.03부터 6개월 동안 1,200건을 처리해 30% 개선했다."
    generated = "2023년 3월부터 1년 동안 1,500건을 처리해 45퍼센트 개선했다."

    result = find_unsupported_facts(source, generated)

    assert [(fact.kind, fact.value) for fact in result] == [
        ("PERIOD", "1년"),
        ("NUMBER", "1500건"),
        ("PERCENT", "45%"),
    ]


def test_accepts_equivalent_fact_notation() -> None:
    source = "2023-3에 1,200건을 처리해 30 % 개선했다."
    generated = "2023년 3월에 1200건을 처리해 30퍼센트 개선했다."

    assert find_unsupported_facts(source, generated) == []


def test_same_number_with_different_unit_is_unsupported() -> None:
    result = find_unsupported_facts("10건을 처리했다.", "10명을 지원했다.")

    assert [(fact.kind, fact.value) for fact in result] == [("NUMBER", "10명")]


def test_offsets_are_in_generated_text() -> None:
    generated = "처리량을 99건으로 늘렸다."
    result = find_unsupported_facts("처리 경험이 있다.", generated)

    assert generated[result[0].start : result[0].end] == "99건"


@given(st.text())
def test_text_never_has_unsupported_facts_against_itself(text: str) -> None:
    assert find_unsupported_facts(text, text) == []
