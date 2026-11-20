"""`ports.DocumentExtractor` 구현. #41 `mentoring.extract.extract_document`를 감싼다.
텍스트 레이어(pypdf)를 먼저 읽고, 품질이 부족할 때만 Textract OCR을 쓴다 (2026-11-20 결정, 이슈 #41 댓글).
OCR은 원본 PDF가 있는 S3 위치를 직접 읽으므로 bucket이 있어야 켜진다.
"""


class PdfExtractor:
    def __init__(self, *, ocr=None, bucket: str | None = None, thresholds=None):
        from mentoring.extract import load_thresholds

        self.ocr = ocr
        self.bucket = bucket
        self.thresholds = thresholds or load_thresholds()

    def extract(self, pdf_bytes: bytes, key: str):
        from mentoring.extract import extract_document

        location = (self.bucket, key) if self.ocr is not None and self.bucket else None
        return extract_document(pdf_bytes, thresholds=self.thresholds, ocr=self.ocr if location else None,
                                s3_location=location)
