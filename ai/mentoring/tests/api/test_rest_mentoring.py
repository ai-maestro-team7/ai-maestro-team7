"""REST 입구 (Requirement 1·2, UT-15, INT-01)."""
import json
import logging
from urllib.parse import urlencode

import pytest
from team07_contracts import validate

from mentoring.api import rest_handler, task_handler
from mentoring.core.summary import to_career_profile_summary
from support.data import DATA_ANALYST_RESUME, QUOTE_PANDAS
from support.factory import make_deps, run_pending

BASE = "/api/v1/mentoring"


def http_event(method, path, *, body=None, headers=None, raw_body=None):
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": urlencode({}),
        "headers": {"content-type": "application/json", **(headers or {})},
        "requestContext": {"requestId": "req-test", "stage": "$default",
                           "http": {"method": method, "path": path, "protocol": "HTTP/1.1", "sourceIp": "127.0.0.1",
                                    "userAgent": "pytest"}},
        "body": raw_body if raw_body is not None else (json.dumps(body, ensure_ascii=False) if body is not None
                                                       else None),
        "isBase64Encoded": False,
    }


def call(deps, method, path, *, user_id="user-a", **kwargs):
    response = rest_handler.handle(http_event(method, BASE + path, **kwargs), deps, user_id)
    return response["statusCode"], json.loads(response["body"]) if response.get("body") else None


def assert_error(status, body, expected_status, code):
    assert status == expected_status
    assert set(body["error"]) == {"code", "message", "requestId", "retryable", "details"}
    assert body["error"]["code"] == code


@pytest.fixture
def deps():
    return make_deps()


# ---------------------------------------------------------------- INT-01 텍스트 → 추출 → 프로필 → 확인 → 면접 요약
def test_int01_text_resume_to_confirmed_profile_and_interview_summary(deps):
    status, body = call(deps, "POST", "/documents/text",
                        body={"text": DATA_ANALYST_RESUME, "documentType": "RESUME", "title": "데이터 분석 이력서"})
    assert status == 202 and body["status"] == "PENDING"
    doc_id = body["documentId"]

    status, view = call(deps, "GET", f"/documents/{doc_id}")
    assert status == 200 and view["extractionStatus"] == "EXTRACTED"
    assert "text" not in view and "textKey" not in view

    [result] = run_pending(deps)
    assert result["status"] == "COMPLETED"

    status, view = call(deps, "GET", f"/documents/{doc_id}")
    assert view["extractionStatus"] == "COMPLETED" and view["taskStatus"] == "COMPLETED"

    status, profile = call(deps, "GET", "/profiles/me")
    assert status == 200 and profile["profileVersion"] == 1 and "ownerUserId" not in profile
    ids = {s["name"]: s["skillId"] for s in profile["skills"]}

    status, confirmed = call(deps, "POST", f"/profiles/{profile['profileId']}/confirm", body={
        "baseVersion": 1,
        "decisions": [{"skillId": ids["데이터 전처리"], "action": "CONFIRM"},
                      {"skillId": ids["SQL"], "action": "CONFIRM"}],
        "additions": [{"name": "통계 분석"}]})
    assert status == 201 and confirmed["profileVersion"] == 2

    stored = deps.users.get_profile_version("user-a", profile["profileId"], 2)
    summary = to_career_profile_summary(stored.to_api())
    validate("CareerProfileSummary", summary, schema_version="1.0")
    assert summary["skills"] == ["데이터 전처리", "SQL", "통계 분석"]


# ---------------------------------------------------------------- UT-15 다른 사용자 조회 차단
def test_ut15_other_user_cannot_read_document_or_profile(deps):
    _, body = call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME, "title": "비밀 제목"})
    run_pending(deps)
    status, error = call(deps, "GET", f"/documents/{body['documentId']}", user_id="user-b")
    assert_error(status, error, 404, "DOCUMENT_NOT_FOUND")
    assert "비밀 제목" not in json.dumps(error, ensure_ascii=False)
    missing_status, missing = call(deps, "GET", "/documents/doc-none", user_id="user-b")
    assert (missing_status, missing["error"]["code"]) == (status, error["error"]["code"])  # 존재 여부를 드러내지 않는다

    status, error = call(deps, "GET", "/profiles/me", user_id="user-b")
    assert_error(status, error, 404, "NOT_FOUND")
    _, profile = call(deps, "GET", "/profiles/me")
    status, error = call(deps, "POST", f"/profiles/{profile['profileId']}/confirm", user_id="user-b",
                         body={"baseVersion": 1})
    assert_error(status, error, 404, "NOT_FOUND")
    assert QUOTE_PANDAS not in json.dumps(error, ensure_ascii=False)


def test_user_id_in_body_is_ignored(deps):
    status, body = call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME, "userId": "user-b"})
    assert status == 202
    assert deps.users.get_document_latest("user-a", body["documentId"]) is not None
    assert deps.users.get_document_latest("user-b", body["documentId"]) is None


def test_missing_user_id_is_401(deps):
    response = rest_handler.handle(http_event("GET", BASE + "/profiles/me"), deps, "")
    assert response["statusCode"] == 401 and json.loads(response["body"])["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------- 요청 검사와 오류 형식
def test_bad_bodies_are_400(deps):
    assert_error(*call(deps, "POST", "/documents/text"), 400, "INVALID_INPUT")
    assert_error(*call(deps, "POST", "/documents/text", raw_body="{not json"), 400, "INVALID_INPUT")
    assert_error(*call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME, "documentType": "X"}),
                 400, "INVALID_INPUT")
    assert_error(*call(deps, "GET", "/documents/doc%23x"), 400, "INVALID_INPUT")


def test_idempotency_header_replays(deps):
    headers = {"Idempotency-Key": "k-1"}
    s1, b1 = call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME}, headers=headers)
    s2, b2 = call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME}, headers=headers)
    assert (s1, s2) == (202, 202) and b1 == b2


def test_routes_not_built_yet_are_501(deps):
    for method, path in [("POST", "/agent/chat"), ("GET", "/health/readiness")]:
        assert_error(*call(deps, method, path), 501, "NOT_IMPLEMENTED")


def test_unknown_route_is_404(deps):
    assert_error(*call(deps, "GET", "/nothing-here"), 404, "NOT_FOUND")


def test_alias_codes_are_answered_with_representative_codes():
    from mentoring.api.errors import error_body

    _, body = error_body(400, "VALIDATION_ERROR", "x", "req-1")
    assert body["error"]["code"] == "INVALID_INPUT"
    _, body = error_body(503, "MODEL_UNAVAILABLE", "x", "req-1")
    assert body["error"]["code"] == "AWS_SERVICE_ERROR"


# ---------------------------------------------------------------- 작업 입구
def test_task_handler_ignores_other_events(deps):
    assert task_handler.handle({"task": {"x": 1}}, deps)["reason"] == "NOT_A_MENTORING_TASK"
    assert task_handler.handle({"mentoringTask": {"taskId": "t"}}, deps)["reason"] == "INVALID_MESSAGE"


# ---------------------------------------------------------------- 로그 (Requirement 12)
def test_logs_contain_no_resume_text_or_user_id(deps, caplog):
    caplog.set_level(logging.INFO, logger="mentoring")
    call(deps, "POST", "/documents/text", body={"text": DATA_ANALYST_RESUME, "title": "내 이력서.pdf"})
    run_pending(deps)
    call(deps, "GET", "/profiles/me")
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert logged
    for secret in (QUOTE_PANDAS, "010-0000-1234", "applicant-a@example.com", "내 이력서.pdf", "user-a"):
        assert secret not in logged


# ---------------------------------------------------------------- PDF 업로드 경로
def test_upload_routes_over_http(deps):
    status, body = call(deps, "POST", "/documents/upload-url", body={
        "fileName": "resume.pdf", "contentType": "application/pdf", "sizeBytes": 2048})
    assert status == 201 and body["status"] == "PENDING" and body["uploadUrl"].startswith("https://")
    status, error = call(deps, "POST", f"/documents/{body['documentId']}/complete")
    assert_error(status, error, 501, "NOT_IMPLEMENTED")  # 이 Deps에는 추출기가 없다
    status, error = call(deps, "POST", "/documents/upload-url", body={
        "fileName": "a.png", "contentType": "image/png", "sizeBytes": 10})
    assert_error(status, error, 400, "INVALID_INPUT")
