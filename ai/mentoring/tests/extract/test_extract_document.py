from __future__ import annotations

from io import BytesIO

import pytest
from hypothesis import given, strategies as st
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from mentoring.extract import (
    ExtractError,
    ExtractThresholds,
    TextractOcr,
    extract_document,
    extract_text_layer,
    judge_quality,
    load_thresholds,
    normalize_text,
)


def _pdf(*pages: str) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    for text in pages:
        document.drawString(72, 720, text)
        document.showPage()
    document.save()
    return output.getvalue()


def _encrypted_pdf() -> bytes:
    reader = PdfReader(BytesIO(_pdf("virtual resume text")))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("virtual-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _thresholds(**changes: object) -> ExtractThresholds:
    data = {
        "minTotalChars": 10,
        "minPageChars": 3,
        "minPrintableRatio": 0.8,
        "maxBrokenRatio": 0.05,
        "ocrMaxPolls": 3,
        "ocrPollSeconds": 0,
    }
    data.update(changes)
    return ExtractThresholds.model_validate(data)


class FakeTextract:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    def detect_document_text(self, **kwargs):
        self.calls.append(("detect", kwargs))
        return self.responses.pop(0)

    def start_document_text_detection(self, **kwargs):
        self.calls.append(("start", kwargs))
        return {"JobId": "virtual-job"}

    def get_document_text_detection(self, **kwargs):
        self.calls.append(("get", kwargs))
        return self.responses.pop(0)


def test_normalizes_unicode_newlines_spaces_and_blank_lines() -> None:
    raw = " e\u0301\t  test \r\n\r\n\r\n next  "

    assert normalize_text(raw) == "é test\n\n next"


@given(st.text())
def test_normalization_is_idempotent(text: str) -> None:
    assert normalize_text(normalize_text(text)) == normalize_text(text)


def test_extracts_text_layer_and_page_starts() -> None:
    result = extract_text_layer(_pdf("virtual first page text", "virtual second page text"))

    assert result.method == "TEXT_LAYER"
    assert result.page_count == 2
    assert result.page_starts == [0, result.text.index("virtual second")]
    assert result.quality.ok


def test_falls_back_to_async_ocr_for_scanned_pdf() -> None:
    client = FakeTextract(
        [{"JobStatus": "SUCCEEDED", "Blocks": [{"BlockType": "LINE", "Text": "virtual OCR resume text", "Page": 1}]}]
    )

    result = extract_document(
        _pdf(""), thresholds=_thresholds(), ocr=TextractOcr(client), s3_location=("virtual-bucket", "virtual-key")
    )

    assert result.status == "EXTRACTED"
    assert result.extracted.method == "OCR"
    assert client.calls[0] == (
        "start",
        {"DocumentLocation": {"S3Object": {"Bucket": "virtual-bucket", "Name": "virtual-key"}}},
    )


def test_collects_all_textract_pages_with_next_token() -> None:
    client = FakeTextract(
        [
            {"JobStatus": "IN_PROGRESS"},
            {
                "JobStatus": "SUCCEEDED",
                "Blocks": [{"BlockType": "LINE", "Text": "page one", "Page": 1}],
                "NextToken": "virtual-next",
            },
            {"JobStatus": "SUCCEEDED", "Blocks": [{"BlockType": "LINE", "Text": "page two", "Page": 2}]},
        ]
    )
    sleeps: list[float] = []

    pages = TextractOcr(client).collect(
        "virtual-job", max_polls=3, poll_seconds=0.25, sleep=sleeps.append
    )

    assert pages == ["page one", "page two"]
    assert sleeps == [0.25]
    assert client.calls[-1][1]["NextToken"] == "virtual-next"


def test_detects_single_page_lines() -> None:
    client = FakeTextract(
        [{"Blocks": [{"BlockType": "WORD", "Text": "ignore"}, {"BlockType": "LINE", "Text": "virtual line"}]}]
    )

    assert TextractOcr(client).detect_single_page(b"virtual-image") == ["virtual line"]


@pytest.mark.parametrize("pdf_bytes", [b"not-a-pdf", _encrypted_pdf()])
def test_unreadable_pdf_raises_safe_error(pdf_bytes: bytes) -> None:
    with pytest.raises(ExtractError) as caught:
        extract_text_layer(pdf_bytes)

    assert caught.value.code == "DOCUMENT_UNREADABLE"
    assert caught.value.retryable is False
    assert "not-a-pdf" not in caught.value.message


def test_too_little_text_requires_user_review_without_ocr() -> None:
    result = extract_document(
        _pdf("short"), thresholds=_thresholds(minTotalChars=100), ocr=None, s3_location=None
    )

    assert result.status == "REQUIRES_USER_REVIEW"
    assert result.reason == "TOO_LITTLE_TEXT"


def test_ocr_still_too_short_requires_user_review() -> None:
    client = FakeTextract(
        [{"JobStatus": "SUCCEEDED", "Blocks": [{"BlockType": "LINE", "Text": "tiny", "Page": 1}]}]
    )

    result = extract_document(
        _pdf(""),
        thresholds=_thresholds(minTotalChars=100),
        ocr=TextractOcr(client),
        s3_location=("virtual-bucket", "virtual-key"),
    )

    assert result.status == "REQUIRES_USER_REVIEW"
    assert result.reason == "TOO_LITTLE_TEXT"


@pytest.mark.parametrize(
    "responses",
    [
        [{"JobStatus": "FAILED"}],
        [{"JobStatus": "IN_PROGRESS"}, {"JobStatus": "IN_PROGRESS"}],
    ],
)
def test_textract_failure_and_timeout_are_retryable(responses: list[dict]) -> None:
    with pytest.raises(ExtractError) as caught:
        TextractOcr(FakeTextract(responses)).collect(
            "virtual-job", max_polls=len(responses), poll_seconds=0, sleep=lambda _: None
        )

    assert caught.value.code == "AWS_SERVICE_ERROR"
    assert caught.value.retryable is True


def test_quality_detects_broken_encoding() -> None:
    report = judge_quality(["정상 텍스트\ufffd\ufffd"], _thresholds(maxBrokenRatio=0.01))

    assert not report.ok
    assert report.reason == "BROKEN_ENCODING"


def test_load_thresholds_rejects_invalid_range(tmp_path) -> None:
    path = tmp_path / "thresholds.json"
    path.write_text(
        '{"minTotalChars": 1, "minPageChars": 1, "minPrintableRatio": 2, '
        '"maxBrokenRatio": 0, "ocrMaxPolls": 1, "ocrPollSeconds": 0}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="임계값"):
        load_thresholds(path)
