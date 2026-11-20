"""문서 텍스트 추출의 결정적 규칙과 주입 가능한 Textract 어댑터."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from pypdf import PdfReader


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class ExtractThresholds(_Model):
    min_total_chars: int = Field(ge=0)
    min_page_chars: int = Field(ge=0)
    min_printable_ratio: float = Field(ge=0.0, le=1.0)
    max_broken_ratio: float = Field(ge=0.0, le=1.0)
    ocr_max_polls: int = Field(ge=1)
    ocr_poll_seconds: float = Field(ge=0.0)


class QualityReport(_Model):
    total_chars: int = Field(ge=0)
    page_chars: list[int]
    printable_ratio: float = Field(ge=0.0, le=1.0)
    broken_ratio: float = Field(ge=0.0, le=1.0)
    ok: bool
    reason: Literal["TOO_LITTLE_TEXT", "BROKEN_ENCODING"] | None = None


class ExtractedText(_Model):
    text: str
    page_starts: list[int]
    page_count: int = Field(ge=1)
    method: Literal["TEXT_LAYER", "OCR"]
    quality: QualityReport


class ExtractResult(_Model):
    status: Literal["EXTRACTED", "REQUIRES_USER_REVIEW"]
    extracted: ExtractedText | None = None
    reason: Literal["TOO_LITTLE_TEXT", "BROKEN_ENCODING"] | None = None


class ExtractError(Exception):
    """원문을 포함하지 않는 안전한 추출 오류."""

    def __init__(self, code: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


_INLINE_WHITESPACE = re.compile(r"[^\S\r\n]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(raw: str) -> str:
    """NFC·개행·공백 규칙을 적용한 멱등 텍스트 정규화."""

    text = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_INLINE_WHITESPACE.sub(" ", line).rstrip() for line in text.split("\n")]
    return _EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def load_thresholds(path: str | Path | None = None) -> ExtractThresholds:
    """JSON 임계값을 읽고 모든 범위를 Pydantic으로 검사한다."""

    source = Path(path) if path is not None else Path(__file__).with_name("thresholds.json")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return ExtractThresholds.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"추출 임계값 설정이 올바르지 않습니다: {source}") from exc


def _is_broken(character: str) -> bool:
    return character == "\ufffd" or (unicodedata.category(character) == "Cc" and character not in "\n\t\r")


def judge_quality(page_texts: list[str], thresholds: ExtractThresholds) -> QualityReport:
    """페이지 텍스트의 양, 인쇄 가능 문자, 깨진 문자 비율을 계산한다."""

    normalized = [normalize_text(page) for page in page_texts]
    page_chars = [len(page) for page in normalized]
    combined = "".join(normalized)
    total = len(combined)
    printable = sum(character.isprintable() or character in "\n\t\r" for character in combined)
    broken = sum(_is_broken(character) for character in combined)
    printable_ratio = printable / total if total else 0.0
    broken_ratio = broken / total if total else 0.0

    broken_encoding = (
        broken_ratio > thresholds.max_broken_ratio
        or (total > 0 and printable_ratio < thresholds.min_printable_ratio)
    )
    too_little = total < thresholds.min_total_chars or any(
        count < thresholds.min_page_chars for count in page_chars
    )
    reason: Literal["TOO_LITTLE_TEXT", "BROKEN_ENCODING"] | None
    if broken_encoding:
        reason = "BROKEN_ENCODING"
    elif too_little:
        reason = "TOO_LITTLE_TEXT"
    else:
        reason = None
    return QualityReport(
        total_chars=total,
        page_chars=page_chars,
        printable_ratio=printable_ratio,
        broken_ratio=broken_ratio,
        ok=reason is None,
        reason=reason,
    )


def _combine_pages(
    page_texts: list[str], method: Literal["TEXT_LAYER", "OCR"], thresholds: ExtractThresholds
) -> ExtractedText:
    if not page_texts:
        page_texts = [""]
    pages = [normalize_text(page) for page in page_texts]
    starts: list[int] = []
    parts: list[str] = []
    position = 0
    for index, page in enumerate(pages):
        if index:
            parts.append("\n\n")
            position += 2
        starts.append(position)
        parts.append(page)
        position += len(page)
    return ExtractedText(
        text="".join(parts),
        page_starts=starts,
        page_count=len(pages),
        method=method,
        quality=judge_quality(pages, thresholds),
    )


def _read_pdf_pages(pdf_bytes: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise ExtractError("DOCUMENT_UNREADABLE", "암호화된 PDF는 읽을 수 없습니다.", False)
        return [page.extract_text() or "" for page in reader.pages]
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError("DOCUMENT_UNREADABLE", "PDF 문서를 읽을 수 없습니다.", False) from exc


def extract_text_layer(pdf_bytes: bytes) -> ExtractedText:
    """PDF의 텍스트 레이어를 페이지별로 추출한다."""

    return _combine_pages(_read_pdf_pages(pdf_bytes), "TEXT_LAYER", load_thresholds())


class TextractOcr:
    """호출자가 제공한 Textract 호환 client만 사용하는 OCR 어댑터."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @staticmethod
    def _page_lines(blocks: list[dict[str, Any]]) -> dict[int, list[str]]:
        pages: dict[int, list[str]] = defaultdict(list)
        for block in blocks:
            if block.get("BlockType") == "LINE" and isinstance(block.get("Text"), str):
                pages[int(block.get("Page", 1))].append(block["Text"])
        return pages

    def detect_single_page(self, document_bytes: bytes) -> list[str]:
        try:
            response = self._client.detect_document_text(Document={"Bytes": document_bytes})
        except Exception as exc:
            raise ExtractError("AWS_SERVICE_ERROR", "OCR 서비스를 호출하지 못했습니다.", True) from exc
        pages = self._page_lines(response.get("Blocks", []))
        return ["\n".join(pages[page]) for page in sorted(pages)] or [""]

    def start(self, bucket: str, key: str) -> str:
        try:
            response = self._client.start_document_text_detection(
                DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
            )
            job_id = response["JobId"]
        except Exception as exc:
            raise ExtractError("AWS_SERVICE_ERROR", "OCR 작업을 시작하지 못했습니다.", True) from exc
        if not isinstance(job_id, str) or not job_id:
            raise ExtractError("AWS_SERVICE_ERROR", "OCR 작업 식별자를 받지 못했습니다.", True)
        return job_id

    def collect(
        self,
        job_id: str,
        *,
        max_polls: int,
        poll_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> list[str]:
        if max_polls < 1 or poll_seconds < 0:
            raise ValueError("max_polls는 1 이상이고 poll_seconds는 0 이상이어야 합니다.")
        first: dict[str, Any] | None = None
        for attempt in range(max_polls):
            try:
                first = self._client.get_document_text_detection(JobId=job_id)
            except Exception as exc:
                raise ExtractError("AWS_SERVICE_ERROR", "OCR 결과를 조회하지 못했습니다.", True) from exc
            status = first.get("JobStatus")
            if status == "SUCCEEDED":
                break
            if status == "FAILED":
                raise ExtractError("AWS_SERVICE_ERROR", "OCR 작업이 실패했습니다.", True)
            if status != "IN_PROGRESS":
                raise ExtractError("AWS_SERVICE_ERROR", "OCR 작업 상태가 올바르지 않습니다.", True)
            if attempt + 1 < max_polls:
                sleep(poll_seconds)
        else:
            raise ExtractError("AWS_SERVICE_ERROR", "OCR 작업 시간이 초과되었습니다.", True)

        pages: dict[int, list[str]] = defaultdict(list)
        while first is not None:
            for page, lines in self._page_lines(first.get("Blocks", [])).items():
                pages[page].extend(lines)
            token = first.get("NextToken")
            if not token:
                break
            try:
                first = self._client.get_document_text_detection(JobId=job_id, NextToken=token)
            except Exception as exc:
                raise ExtractError("AWS_SERVICE_ERROR", "OCR 다음 페이지를 조회하지 못했습니다.", True) from exc
            if first.get("JobStatus") not in (None, "SUCCEEDED"):
                raise ExtractError("AWS_SERVICE_ERROR", "OCR 다음 페이지 상태가 올바르지 않습니다.", True)
        return ["\n".join(pages[page]) for page in sorted(pages)] or [""]


def extract_document(
    pdf_bytes: bytes,
    *,
    thresholds: ExtractThresholds,
    ocr: TextractOcr | None,
    s3_location: tuple[str, str] | None,
) -> ExtractResult:
    """텍스트 레이어를 우선 사용하고 품질 미달일 때만 비동기 OCR로 전환한다."""

    text_layer = _combine_pages(_read_pdf_pages(pdf_bytes), "TEXT_LAYER", thresholds)
    if text_layer.quality.ok:
        return ExtractResult(status="EXTRACTED", extracted=text_layer)
    if ocr is None or s3_location is None:
        return ExtractResult(
            status="REQUIRES_USER_REVIEW", extracted=text_layer, reason=text_layer.quality.reason
        )

    job_id = ocr.start(*s3_location)
    page_texts = ocr.collect(
        job_id,
        max_polls=thresholds.ocr_max_polls,
        poll_seconds=thresholds.ocr_poll_seconds,
    )
    extracted = _combine_pages(page_texts, "OCR", thresholds)
    if extracted.quality.ok:
        return ExtractResult(status="EXTRACTED", extracted=extracted)
    return ExtractResult(status="REQUIRES_USER_REVIEW", extracted=extracted, reason=extracted.quality.reason)
