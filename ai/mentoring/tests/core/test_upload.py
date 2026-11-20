"""PDF 업로드와 텍스트 추출 작업 (Requirement 3·4·5·12, 개발계획서1 §13 UT-20·INT-01)."""
from dataclasses import replace
from datetime import timedelta
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from mentoring.core.documents import get_document
from mentoring.core.pdf_extractor import PdfExtractor
from mentoring.core.profiles import get_latest_profile
from mentoring.core.upload import complete_upload, create_upload_url
from mentoring.errors import MentoringError
from mentoring.extract import ExtractThresholds
from mentoring.models import UploadUrlRequest
from support.factory import FIXED_NOW, make_deps, metric_values, run_pending, small_config

USER = "user-a"

# reportlab 기본 글꼴은 한글을 그리지 못해서 영문 가상 이력서를 쓴다
LINES = [
    "Virtual Applicant A - Data Analysis",
    "Project: Busan bus ridership analysis (2025.03-2025.06)",
    "Cleaned missing values with Python pandas and aggregated ridership per stop.",
    "Built a Tableau dashboard and presented the results.",
    "Ran a SQL study group in the campus data club for one year.",
    "Certificate: ADsP",
]
QUOTE_PANDAS = "Cleaned missing values with Python pandas and aggregated ridership per stop."
QUOTE_TABLEAU = "Built a Tableau dashboard and presented the results."


def pdf(lines=LINES, *, pages=1) -> bytes:
    out = BytesIO()
    doc = canvas.Canvas(out)
    for _ in range(pages):
        y = 760
        for line in lines:
            doc.drawString(50, y, line)
            y -= 18
        doc.showPage()
    doc.save()
    return out.getvalue()


def thresholds(**changes):
    data = {"minTotalChars": 40, "minPageChars": 5, "minPrintableRatio": 0.8, "maxBrokenRatio": 0.05,
            "ocrMaxPolls": 3, "ocrPollSeconds": 0}
    data.update(changes)
    return ExtractThresholds.model_validate(data)


def llm_output():
    return {
        "skills": [
            {"name": "data cleaning", "evidenceLevel": "EVIDENCED", "quotes": [{"quotedText": QUOTE_PANDAS}]},
            {"name": "data visualization", "evidenceLevel": "EVIDENCED", "quotes": [{"quotedText": QUOTE_TABLEAU}]},
        ],
        "projects": [], "experiences": [], "certificates": [{"name": "ADsP", "quotes": []}],
        "needsConfirmation": [],
    }


class FakeTextract:
    """스캔 PDF용 OCR 대역. 비동기 시작 → 완료 응답 두 장(NextToken)."""

    def __init__(self, lines=LINES):
        self.calls = []
        half = len(lines) // 2
        self.pages = [
            {"JobStatus": "SUCCEEDED", "NextToken": "t2",
             "Blocks": [{"BlockType": "LINE", "Page": 1, "Text": t} for t in lines[:half]]},
            {"JobStatus": "SUCCEEDED", "Blocks": [{"BlockType": "LINE", "Page": 1, "Text": t} for t in lines[half:]]},
        ]

    def start_document_text_detection(self, **kwargs):
        self.calls.append(("start", kwargs))
        return {"JobId": "virtual-job"}

    def get_document_text_detection(self, **kwargs):
        self.calls.append(("get", kwargs))
        return self.pages[0] if "NextToken" not in kwargs else self.pages[1]


def make(*, ocr=None, responses=None, **config):
    from mentoring.extract import TextractOcr

    extractor = PdfExtractor(ocr=TextractOcr(ocr) if ocr else None, bucket="virtual-bucket" if ocr else None,
                             thresholds=thresholds())
    return make_deps(responses or [llm_output()], extractor=extractor, config=small_config(**config))


def request(**kwargs):
    data = {"fileName": "resume.pdf", "contentType": "application/pdf", "sizeBytes": 1000, "documentType": "RESUME"}
    data.update(kwargs)
    return UploadUrlRequest.model_validate(data)


def upload(deps, data: bytes, *, content_type="application/pdf", size=None):
    body = create_upload_url(deps, USER, request(sizeBytes=size or len(data), contentType=content_type))
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    deps.objects.upload(version.original_key, data, content_type)
    return body


# ---------------------------------------------------------------- 업로드 URL
def test_upload_url_is_signed_with_type_and_size_and_not_stored():
    deps = make()
    body = create_upload_url(deps, USER, request(sizeBytes=1234), "idem-1")
    assert body["status"] == "PENDING" and body["expiresInSeconds"] == deps.config.upload.presign_expires_seconds
    signed = deps.objects.presigned[-1]
    assert (signed["contentType"], signed["sizeBytes"]) == ("application/pdf", 1234)
    # 완료 전에는 수명 주기 규칙이 지우는 임시 경로에 올린다
    assert signed["key"].startswith(f"pending/users/{deps.hash_user_id(USER)}/documents/{body['documentId']}/v1/")
    stored = str(deps.users.items)
    assert body["uploadUrl"] not in stored  # URL은 DB·멱등 결과에 남기지 않는다 (Requirement 3 기준 6)
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "PENDING"


def test_upload_url_replay_returns_same_document_with_fresh_url():
    deps = make()
    first = create_upload_url(deps, USER, request(), "idem-1")
    again = create_upload_url(deps, USER, request(), "idem-1")
    assert again["documentId"] == first["documentId"] and len(deps.objects.presigned) == 2
    with pytest.raises(MentoringError) as error:
        create_upload_url(deps, USER, request(sizeBytes=999), "idem-1")
    assert error.value.status == 409


@pytest.mark.parametrize("kwargs, status, code", [
    ({"contentType": "image/png"}, 400, "INVALID_INPUT"),
    ({"sizeBytes": 0}, 400, "INVALID_INPUT"),
    ({"sizeBytes": 10 * 1024 * 1024 + 1}, 413, "FILE_TOO_LARGE"),
    ({"fileName": "  "}, 400, "INVALID_INPUT"),
    ({"workspaceId": "ws#1"}, 400, "INVALID_INPUT"),
])
def test_upload_url_rejects_bad_requests(kwargs, status, code):
    deps = make()
    with pytest.raises(MentoringError) as error:
        create_upload_url(deps, USER, request(**kwargs))
    assert (error.value.status, error.value.code) == (status, code)


def test_pending_document_records_expire_after_ttl():
    deps = make()
    body = create_upload_url(deps, USER, request())
    expected = int((FIXED_NOW + timedelta(hours=deps.config.upload.pending_ttl_hours)).timestamp())
    assert deps.users.get_document_version(USER, body["documentId"], 1).expires_at == expected
    assert deps.users.get_document_latest(USER, body["documentId"]).expires_at == expected


def test_upload_url_replay_after_record_expired_is_404():
    deps = make()
    body = create_upload_url(deps, USER, request(), "idem-1")
    # DynamoDB TTL이 PENDING 기록을 지웠다고 친다 (멱등 키는 남아 있다)
    for sk in (f"DOC_LATEST#{body['documentId']}", f"DOC#{body['documentId']}#V#0001"):
        deps.users.items.pop((f"USER#{USER}", sk))
    with pytest.raises(MentoringError) as error:
        create_upload_url(deps, USER, request(), "idem-1")
    assert error.value.code == "DOCUMENT_NOT_FOUND"


# ---------------------------------------------------------------- 업로드 완료
def test_complete_moves_original_out_of_pending_and_clears_ttl():
    deps = make()
    data = pdf()
    body = upload(deps, data)
    staged = deps.users.get_document_version(USER, body["documentId"], 1).original_key
    complete_upload(deps, USER, body["documentId"])
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    assert version.original_key == f"users/{deps.hash_user_id(USER)}/documents/{body['documentId']}/v1/original.pdf"
    assert version.expires_at is None
    assert deps.users.get_document_latest(USER, body["documentId"]).expires_at is None
    assert deps.objects.get_bytes(version.original_key) == data
    assert deps.objects.get_bytes(staged) is None


def test_complete_after_pending_ttl_is_400():
    deps = make()
    body = upload(deps, pdf())
    late = replace(deps, now=lambda: FIXED_NOW + timedelta(hours=deps.config.upload.pending_ttl_hours))
    with pytest.raises(MentoringError) as error:
        complete_upload(late, USER, body["documentId"])
    assert error.value.status == 400 and deps.tasks.sent == []


def test_complete_succeeds_when_pending_cleanup_fails():
    deps = make()
    body = upload(deps, pdf())

    def broken_delete(key):
        raise RuntimeError("S3 unavailable")

    deps.objects.delete = broken_delete
    result = complete_upload(deps, USER, body["documentId"])
    assert result["extractionStatus"] == "UPLOADED" and len(deps.tasks.sent) == 1


def test_complete_retry_after_copy_without_record_update_still_works():
    deps = make()
    body = upload(deps, pdf())
    original_save = deps.users.save_document
    calls = []

    def fail_once(latest, version):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("DynamoDB unavailable")
        original_save(latest, version)

    deps.users.save_document = fail_once
    with pytest.raises(RuntimeError):
        complete_upload(deps, USER, body["documentId"])
    # 복사는 됐지만 기록은 아직 PENDING이라 다시 부르면 이어서 끝난다
    result = complete_upload(deps, USER, body["documentId"])
    assert result["extractionStatus"] == "UPLOADED"
    assert deps.users.get_document_version(USER, body["documentId"], 1).original_key.startswith("users/")


def test_complete_keeps_documents_issued_before_pending_prefix():
    deps = make()
    data = pdf()
    body = create_upload_url(deps, USER, request(sizeBytes=len(data)))
    # 이 변경 전에 발급된 문서: 정식 키에 바로 올렸고 expiresAt이 없다
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    final = version.original_key.removeprefix("pending/")
    legacy = version.model_copy(update={"original_key": final, "expires_at": None})
    deps.users.save_document(deps.users.get_document_latest(USER, body["documentId"]).model_copy(
        update={"expires_at": None}), legacy)
    deps.objects.upload(final, data, "application/pdf")
    complete_upload(deps, USER, body["documentId"])
    assert deps.objects.get_bytes(final) == data
    assert deps.users.get_document_version(USER, body["documentId"], 1).original_key == final


def test_complete_without_uploaded_file_is_400_and_creates_no_task():
    deps = make()
    body = create_upload_url(deps, USER, request())
    with pytest.raises(MentoringError) as error:
        complete_upload(deps, USER, body["documentId"])
    assert error.value.status == 400 and deps.tasks.sent == []


def test_complete_with_different_size_or_type_is_400():
    deps = make()
    body = create_upload_url(deps, USER, request(sizeBytes=500))
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    deps.objects.upload(version.original_key, b"%PDF-1.4 " + b"x" * 600, "application/pdf")
    with pytest.raises(MentoringError):
        complete_upload(deps, USER, body["documentId"])
    deps.objects.upload(version.original_key, b"x" * 500, "text/html")
    with pytest.raises(MentoringError):
        complete_upload(deps, USER, body["documentId"])


def test_complete_twice_creates_one_task():
    deps = make()
    body = upload(deps, pdf())
    first = complete_upload(deps, USER, body["documentId"])
    again = complete_upload(deps, USER, body["documentId"])
    assert first["status"] == "PENDING" and again["taskId"] == first["taskId"]
    assert len(deps.tasks.sent) == 1


def test_complete_by_other_user_is_404():
    deps = make()
    body = upload(deps, pdf())
    with pytest.raises(MentoringError) as error:
        complete_upload(deps, "user-b", body["documentId"])
    assert error.value.code == "DOCUMENT_NOT_FOUND"


def test_complete_without_extractor_is_501():
    deps = make_deps()
    body = create_upload_url(deps, USER, request())
    with pytest.raises(MentoringError) as error:
        complete_upload(deps, USER, body["documentId"])
    assert error.value.status == 501


# ---------------------------------------------------------------- UT-20, INT-01 (업로드 경로)
def test_ut20_text_layer_pdf_goes_upload_to_profile_without_ocr():
    deps = make()
    body = upload(deps, pdf())
    complete_upload(deps, USER, body["documentId"])
    results = run_pending(deps)
    assert [r["status"] for r in results] == ["COMPLETED", "COMPLETED"]  # 텍스트 추출 → 역량 추출
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    assert version.extraction_method == "TEXT_LAYER" and version.page_count == 1
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "COMPLETED"
    profile = get_latest_profile(deps, USER)
    text = deps.objects.get_text(version.text_key)
    assert [s.name for s in profile.skills] == ["data cleaning", "data visualization"]
    for e in profile.evidence:
        assert text[e.start_char:e.end_char] == e.quoted_text and e.page == 1


def test_ut20_scanned_pdf_uses_textract_with_all_pages():
    ocr = FakeTextract()
    deps = make(ocr=ocr)
    body = upload(deps, pdf(lines=[" "]))  # 텍스트 레이어가 없는 스캔본
    complete_upload(deps, USER, body["documentId"])
    results = run_pending(deps)
    assert [r["status"] for r in results] == ["COMPLETED", "COMPLETED"]
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    assert version.extraction_method == "OCR"
    start = next(kw for name, kw in ocr.calls if name == "start")
    assert start["DocumentLocation"]["S3Object"] == {"Bucket": "virtual-bucket", "Name": version.original_key}
    assert any("NextToken" in kw for name, kw in ocr.calls if name == "get")
    assert len(get_latest_profile(deps, USER).skills) == 2


def test_multi_page_evidence_has_page_number():
    deps = make()
    body = upload(deps, pdf(pages=2))
    complete_upload(deps, USER, body["documentId"])
    run_pending(deps)
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    assert version.page_count == 2 and len(version.page_starts) == 2
    profile = get_latest_profile(deps, USER)
    pages = {e.page for e in profile.evidence}
    assert pages <= {1, 2} and min(pages) >= 1


# ---------------------------------------------------------------- 추출 실패 (Requirement 5 기준 5·6·7)
def test_scanned_pdf_without_ocr_needs_user_review_and_no_profile():
    deps = make()
    body = upload(deps, pdf(lines=[" "]))
    complete_upload(deps, USER, body["documentId"])
    [result] = run_pending(deps)
    assert result["status"] == "REQUIRES_USER_REVIEW"
    view = get_document(deps, USER, body["documentId"])
    assert view.extraction_status.value == "REQUIRES_USER_REVIEW" and view.review_reason == "TOO_LITTLE_TEXT"
    assert deps.users.get_profile_pointer(USER) is None
    assert metric_values(deps, "DocumentParseFailure") == [1]


def test_broken_pdf_is_unreadable_and_not_retryable():
    deps = make()
    body = upload(deps, b"%PDF-1.4 not really a pdf")
    complete_upload(deps, USER, body["documentId"])
    [result] = run_pending(deps)
    assert (result["status"], result["errorCode"]) == ("FAILED", "DOCUMENT_UNREADABLE")
    task = deps.users.get_task(USER, result["taskId"])
    assert task.retryable is False
    assert get_document(deps, USER, body["documentId"]).extraction_status.value == "FAILED"


def test_textract_failure_is_retryable_aws_error():
    class Broken(FakeTextract):
        def start_document_text_detection(self, **kwargs):
            raise RuntimeError("throttled")

    deps = make(ocr=Broken())
    body = upload(deps, pdf(lines=[" "]))
    complete_upload(deps, USER, body["documentId"])
    [result] = run_pending(deps)
    assert (result["status"], result["errorCode"]) == ("FAILED", "AWS_SERVICE_ERROR")
    assert deps.users.get_task(USER, result["taskId"]).retryable is True


def test_too_many_pages_is_rejected():
    deps = make(responses=None)
    deps.config = deps.config.model_copy(update={"upload": deps.config.upload.model_copy(update={"max_pages": 1})})
    body = upload(deps, pdf(pages=2))
    complete_upload(deps, USER, body["documentId"])
    [result] = run_pending(deps)
    assert (result["status"], result["errorCode"]) == ("FAILED", "FILE_TOO_LARGE")


# ---------------------------------------------------------------- 지표 (Requirement 12 기준 3)
def test_emf_metrics_for_extraction():
    deps = make()
    body = upload(deps, pdf())
    complete_upload(deps, USER, body["documentId"])
    run_pending(deps)
    [latency] = [m for m in deps.metrics if "AnalysisLatency" in m]
    spec = latency["_aws"]["CloudWatchMetrics"][0]
    assert spec["Namespace"] == "team07/mentoring" and spec["Metrics"][0]["Unit"] == "Milliseconds"
    assert latency["feature"] == "profile" and set(latency) == {"_aws", "feature", "AnalysisLatency"}


def test_schema_and_evidence_failures_are_counted():
    bad_quote = llm_output()
    bad_quote["skills"].append({"name": "kubernetes", "evidenceLevel": "EVIDENCED",
                                "quotes": [{"quotedText": "Deployed models on Kubernetes."}]})
    deps = make(responses=["not json", bad_quote])
    body = upload(deps, pdf())
    complete_upload(deps, USER, body["documentId"])
    run_pending(deps)
    assert metric_values(deps, "LLMSchemaFailure") == [1]
    assert metric_values(deps, "EvidenceValidationFailure") == [1]


def test_upload_logs_have_no_file_name_key_or_url(caplog, capsys):
    import logging

    caplog.set_level(logging.INFO, logger="mentoring")
    deps = make()
    body = create_upload_url(deps, USER, request(fileName="김가상_이력서.pdf", sizeBytes=len(pdf())))
    version = deps.users.get_document_version(USER, body["documentId"], 1)
    deps.objects.upload(version.original_key, pdf(), "application/pdf")
    complete_upload(deps, USER, body["documentId"])
    run_pending(deps)
    logged = "\n".join(r.getMessage() for r in caplog.records) + capsys.readouterr().out + str(deps.metrics)
    for secret in ("김가상_이력서.pdf", version.original_key, body["uploadUrl"], QUOTE_PANDAS, USER):
        assert secret not in logged
