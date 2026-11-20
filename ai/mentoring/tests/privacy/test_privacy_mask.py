from __future__ import annotations

from hypothesis import given, strategies as st

from mentoring.privacy import mask_pii, overlaps_mask


def test_masks_each_supported_kind_and_preserves_newlines() -> None:
    text = (
        "이름: 가상 지원자 A\n"
        "전화: 010-0000-XXXX\n"
        "메일: applicant@example.com\n"
        "등록번호: 000000-0000000\n"
        "주소: 부산광역시 금정구 부산대학로 63\n"
        "지번: 부산광역시 금정구 장전동 40번지"
    )

    result = mask_pii(text)

    assert {span.kind for span in result.spans} == {"NAME", "PHONE", "EMAIL", "RRN", "ADDRESS"}
    assert len(result.masked_text) == len(text)
    assert result.masked_text.count("\n") == text.count("\n")
    assert "applicant@example.com" not in result.masked_text


def test_masks_phone_variants_on_one_line() -> None:
    text = "+82 10 0000 XXXX, 02.000.XXXX, 051-000-XXXX"

    result = mask_pii(text)

    assert [span.kind for span in result.spans] == ["PHONE", "PHONE", "PHONE"]


def test_does_not_mask_expected_resume_numbers_or_unlabeled_name() -> None:
    text = (
        "가상 지원자 A는 2023.03~2024.02 동안 학점 3.8/4.5를 받았고 "
        "30% 개선, 1,200건 처리, NCS 20010105 프로젝트를 수행했다."
    )

    result = mask_pii(text)

    assert result.masked_text == text
    assert result.spans == []


def test_merges_overlapping_name_and_email_span() -> None:
    text = "Name: applicant@example.com"

    result = mask_pii(text)

    assert len(result.spans) == 1
    assert result.spans[0].kind == "EMAIL"
    assert result.masked_text.startswith("Name: ")


def test_overlap_uses_half_open_intervals() -> None:
    result = mask_pii("메일: applicant@example.com")
    span = result.spans[0]

    assert overlaps_mask(span.start, span.end, result.spans)
    assert not overlaps_mask(0, span.start, result.spans)
    assert not overlaps_mask(span.end, span.end + 2, result.spans)
    assert not overlaps_mask(-1, 1, result.spans)


def test_empty_string() -> None:
    assert mask_pii("").model_dump() == {"masked_text": "", "spans": []}


@given(st.text())
def test_masking_preserves_length_newlines_and_unmasked_characters(text: str) -> None:
    result = mask_pii(text)

    assert len(result.masked_text) == len(text)
    covered = {index for span in result.spans for index in range(span.start, span.end)}
    for index, original in enumerate(text):
        if index not in covered or original in "\r\n":
            assert result.masked_text[index] == original
        else:
            assert result.masked_text[index] == "*"
