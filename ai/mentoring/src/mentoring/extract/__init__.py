"""PDF 텍스트 레이어 우선 추출과 Textract OCR 폴백."""

from .document import (
    ExtractedText,
    ExtractError,
    ExtractResult,
    ExtractThresholds,
    QualityReport,
    TextractOcr,
    extract_document,
    extract_text_layer,
    judge_quality,
    load_thresholds,
    normalize_text,
)

__all__ = [
    "ExtractedText",
    "ExtractError",
    "ExtractResult",
    "ExtractThresholds",
    "QualityReport",
    "TextractOcr",
    "extract_document",
    "extract_text_layer",
    "judge_quality",
    "load_thresholds",
    "normalize_text",
]
