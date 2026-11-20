"""경험 블록 REST 경로 (첫 스펙 Requirement 9, A F-01B·§6.1). 데이터는 모두 가상이다."""
import json

import pytest

from mentoring.api import rest_handler
from mentoring.llm.mock import MockLlm
from support.factory import make_deps

BASE = "/api/v1/mentoring"
RAW = "학교 팀 프로젝트에서 고객 인터뷰를 직접 진행했습니다."
FIRST = {"title": "가상 인터뷰 프로젝트", "situation": "학교 팀 프로젝트에서", "actions": ["고객 인터뷰를 직접 진행했습니다."],
         "questions": ["인터뷰 대상은 몇 명이었나요?", "본인이 맡은 역할은 무엇이었나요?"],
         "competencyCandidates": [{"name": "고객 조사", "evidenceAction": "고객 인터뷰를 직접 진행했습니다.",
                                   "strength": "EVIDENCED"}],
         "fieldStatus": {"situation": "VERIFIED"}}
SECOND = {**FIRST, "questions": ["인터뷰 결과를 어디에 썼나요?"]}


def event(method, path, *, body=None, headers=None):
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": BASE + path, "rawQueryString": "",
        "headers": {"content-type": "application/json", **(headers or {})},
        "requestContext": {"requestId": "req-test", "stage": "$default",
                           "http": {"method": method, "path": BASE + path, "protocol": "HTTP/1.1",
                                    "sourceIp": "127.0.0.1", "userAgent": "pytest"}},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None,
        "isBase64Encoded": False,
    }


def call(deps, method, path, *, user_id="user-a", **kwargs):
    response = rest_handler.handle(event(method, path, **kwargs), deps, user_id)
    return response["statusCode"], json.loads(response["body"])


@pytest.fixture
def deps():
    deps = make_deps()
    deps.llm = MockLlm([FIRST, SECOND], model_id="mock-story")
    return deps


def test_create_list_get_and_answer_story(deps):
    status, story = call(deps, "POST", "/stories", body={"rawExperience": RAW, "targetRole": "데이터 분석"})
    assert status == 201
    assert story["status"] == "QUESTIONS_READY" and story["version"] == 2
    assert story["questions"] == FIRST["questions"]
    assert story["fieldStatus"]["situation"] == "NEEDS_CONFIRMATION"  # 모델이 VERIFIED라고 해도 믿지 않는다
    assert "ownerUserId" not in story and story["modelId"] == "mock-story"
    story_id = story["storyId"]

    status, listed = call(deps, "GET", "/stories")
    assert status == 200
    assert [(s["storyId"], s["latestVersion"]) for s in listed["stories"]] == [(story_id, 2)]
    assert "ownerUserId" not in listed["stories"][0]

    status, detail = call(deps, "GET", f"/stories/{story_id}")
    assert status == 200 and detail == story

    status, answered = call(deps, "PATCH", f"/stories/{story_id}", body={
        "baseVersion": 2, "confirmFields": ["situation"],
        "answers": [{"question": "본인이 맡은 역할은 무엇이었나요?", "answer": "인터뷰 질문지를 만들었습니다."}]})
    assert status == 200
    # 답변을 저장한 버전(3) 뒤에 질문을 다시 만든 버전(4)
    assert answered["version"] == 4 and answered["questions"] == SECOND["questions"]
    assert answered["confirmedFields"] == ["situation"] and answered["fieldStatus"]["situation"] == "VERIFIED"
    assert "warnings" not in answered


def test_confirm_only_patch_does_not_call_model(deps):
    _, story = call(deps, "POST", "/stories", body={"rawExperience": RAW})
    calls = len(deps.llm.calls)
    status, body = call(deps, "PATCH", f"/stories/{story['storyId']}",
                        body={"baseVersion": story["version"], "confirmFields": ["situation"]})
    assert status == 200 and body["version"] == story["version"] + 1
    assert len(deps.llm.calls) == calls


def test_other_user_gets_same_404(deps):
    _, story = call(deps, "POST", "/stories", body={"rawExperience": RAW})
    for method, body in [("GET", None), ("PATCH", {"baseVersion": 2})]:
        status, error = call(deps, method, f"/stories/{story['storyId']}", user_id="user-b", body=body)
        assert status == 404 and error["error"]["code"] == "NOT_FOUND"
    status, listed = call(deps, "GET", "/stories", user_id="user-b")
    assert status == 200 and listed == {"stories": []}


def test_stale_base_version_is_409(deps):
    _, story = call(deps, "POST", "/stories", body={"rawExperience": RAW})
    status, error = call(deps, "PATCH", f"/stories/{story['storyId']}", body={"baseVersion": 1})
    assert status == 409 and error["error"]["code"] == "PRECONDITION_NOT_MET"


def test_bad_inputs_are_400(deps):
    assert call(deps, "POST", "/stories", body={"rawExperience": "짧"})[0] == 400
    assert call(deps, "POST", "/stories", body={})[0] == 400
    assert call(deps, "GET", "/stories/bad%23id")[0] == 400


def test_model_failure_keeps_draft_and_same_key_retries_generation(deps):
    deps.llm = MockLlm(["not-json"])
    headers = {"Idempotency-Key": "story-k1"}
    body = {"rawExperience": RAW}
    status, error = call(deps, "POST", "/stories", body=body, headers=headers)
    assert status == 500 and error["error"]["code"] == "AI_OUTPUT_INVALID" and error["error"]["retryable"] is True
    _, listed = call(deps, "GET", "/stories")
    assert [s["status"] for s in listed["stories"]] == ["DRAFT"]

    deps.llm = MockLlm([FIRST])
    status, story = call(deps, "POST", "/stories", body=body, headers=headers)
    assert status == 201 and story["status"] == "QUESTIONS_READY"
    _, listed = call(deps, "GET", "/stories")
    assert len(listed["stories"]) == 1  # 새 경험 블록을 만들지 않았다

    status, replay = call(deps, "POST", "/stories", body=body, headers=headers)
    assert status == 201 and replay == story and len(deps.llm.calls) == 1


def test_bedrock_error_is_retryable_503(deps):
    def boom(system, user):
        raise RuntimeError("throttled")

    deps.llm = MockLlm([boom])
    status, error = call(deps, "POST", "/stories", body={"rawExperience": RAW})
    assert status == 503 and error["error"]["code"] == "AWS_SERVICE_ERROR" and error["error"]["retryable"] is True


def test_answers_saved_even_if_question_refresh_fails(deps):
    _, story = call(deps, "POST", "/stories", body={"rawExperience": RAW})
    deps.llm = MockLlm(["not-json"])
    status, body = call(deps, "PATCH", f"/stories/{story['storyId']}", body={
        "baseVersion": story["version"], "answers": [{"question": "역할은?", "answer": "질문지를 만들었습니다."}]})
    assert status == 200 and body["warnings"] == ["QUESTIONS_NOT_REFRESHED"]
    assert body["version"] == story["version"] + 1 and body["answers"][-1]["answer"] == "질문지를 만들었습니다."


def test_story_routes_are_501_without_repo(deps):
    deps.stories = None
    for method, path in [("POST", "/stories"), ("GET", "/stories"), ("GET", "/stories/story-1")]:
        status, error = call(deps, method, path, body={"rawExperience": RAW} if method == "POST" else None)
        assert status == 501 and error["error"]["code"] == "NOT_IMPLEMENTED"
