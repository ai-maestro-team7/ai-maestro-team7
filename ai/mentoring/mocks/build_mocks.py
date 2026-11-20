"""Generate deterministic frontend fixtures through the real mentoring REST entry point.

Run from ``ai/mentoring`` with the same dependencies as the test suite:
``python mocks/build_mocks.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
sys.path.insert(0, str(PACKAGE_ROOT / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "tests"))
sys.path.insert(0, str(PACKAGE_ROOT.parent.parent / "contracts" / "src"))

from mentoring.api import rest_handler  # noqa: E402
from mentoring.llm.mock import MockLlm  # noqa: E402
from support.data import DATA_ANALYST_RESUME, good_output  # noqa: E402
from support.factory import make_deps, run_pending  # noqa: E402
from support.fit import GOOD_LINKS, SUMMARY  # noqa: E402
from support.fit import USER as FLOW_USER  # noqa: E402
from support.flow import flow_deps  # noqa: E402

BASE = "/api/v1/mentoring"
USER_ID = "mock-user"
DEMO_RESUME = "\n".join(
    line
    for line in DATA_ANALYST_RESUME.splitlines()
    if not line.startswith("가상 지원자") and not line.startswith("연락처:")
).strip()


def _event(method: str, path: str, body: dict | None = None) -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": BASE + path,
        "rawQueryString": urlencode({}),
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "requestId": "req-mock",
            "stage": "$default",
            "http": {
                "method": method,
                "path": BASE + path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "mock-builder",
            },
        },
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None,
        "isBase64Encoded": False,
    }


def _call(deps, method: str, path: str, body: dict | None = None) -> tuple[dict, dict]:
    request = {"method": method, "path": path}
    if body is not None:
        request["body"] = body
    response = rest_handler.handle(_event(method, path, body), deps, USER_ID)
    return request, {
        "status": response["statusCode"],
        "body": json.loads(response["body"]) if response.get("body") else None,
    }


def _fixture(request: dict, response: dict) -> dict:
    return {"request": request, "response": response}


def _review_output() -> dict:
    output = good_output()
    output["projects"][0]["summary"] = "정류장별 이용량을 99% 개선"
    return output


def build() -> dict[str, dict]:
    deps = make_deps()
    create_body = {"text": DEMO_RESUME, "documentType": "RESUME", "title": "가상 데이터 분석 이력서"}
    request, response = _call(deps, "POST", "/documents/text", create_body)
    document_id = response["body"]["documentId"]
    fixtures = {"POST_documents_text": _fixture(request, response)}

    request, response = _call(deps, "GET", f"/documents/{document_id}")
    fixtures["GET_documents_id_EXTRACTED"] = _fixture(request, response)

    run_pending(deps)
    request, response = _call(deps, "GET", f"/documents/{document_id}")
    fixtures["GET_documents_id_COMPLETED"] = _fixture(request, response)

    request, response = _call(deps, "GET", "/profiles/me")
    fixtures["GET_profiles_me"] = _fixture(request, response)
    profile = response["body"]
    first_skill = profile["skills"][0]["skillId"]

    confirm_body = {
        "baseVersion": profile["profileVersion"],
        "decisions": [{"skillId": first_skill, "action": "CONFIRM"}],
    }
    request, response = _call(deps, "POST", f"/profiles/{profile['profileId']}/confirm", confirm_body)
    fixtures["POST_profiles_id_confirm"] = _fixture(request, response)

    error_cases = [
        ("ERROR_400_INVALID_INPUT", "POST", "/documents/text", {"text": "짧음"}),
        ("ERROR_404_DOCUMENT_NOT_FOUND", "GET", "/documents/doc-none", None),
        (
            "ERROR_409_PRECONDITION_NOT_MET",
            "POST",
            f"/profiles/{profile['profileId']}/confirm",
            {"baseVersion": 1, "decisions": []},
        ),
        ("ERROR_501_NOT_IMPLEMENTED", "POST", "/agent/chat", {}),
    ]
    for name, method, path, body in error_cases:
        request, response = _call(deps, method, path, body)
        fixtures[name] = _fixture(request, response)

    review_deps = make_deps(responses=[_review_output()])
    request, response = _call(review_deps, "POST", "/documents/text", create_body)
    review_document_id = response["body"]["documentId"]
    run_pending(review_deps)
    request, response = _call(review_deps, "GET", f"/documents/{review_document_id}")
    fixtures["GET_documents_id_REQUIRES_USER_REVIEW"] = _fixture(request, response)

    # PDF 업로드 URL (S3 주소는 가짜 값이다)
    upload_deps = make_deps(extractor=object())
    request, response = _call(upload_deps, "POST", "/documents/upload-url",
                              {"fileName": "resume.pdf", "contentType": "application/pdf", "sizeBytes": 184000,
                               "documentType": "RESUME"})
    fixtures["POST_documents_upload_url"] = _fixture(request, response)

    fixtures.update(_story_fixtures())
    fixtures.update(_flow_fixtures())
    return fixtures


STORY_RAW = "학교 팀 프로젝트에서 고객 인터뷰를 직접 진행했습니다."
STORY_OUTPUT = {"title": "가상 고객 인터뷰 프로젝트", "situation": "학교 팀 프로젝트에서",
                "actions": ["고객 인터뷰를 직접 진행했습니다."],
                "questions": ["인터뷰 대상은 몇 명이었나요?", "본인이 맡은 역할은 무엇이었나요?",
                              "인터뷰 결과를 어디에 썼나요?"],
                "competencyCandidates": [{"name": "고객 조사", "evidenceAction": "고객 인터뷰를 직접 진행했습니다.",
                                          "strength": "EVIDENCED"}], "fieldStatus": {}}


def _story_fixtures() -> dict[str, dict]:
    deps = make_deps()
    deps.llm = MockLlm([STORY_OUTPUT], model_id="mock-llm")
    fixtures = {}
    request, response = _call(deps, "POST", "/stories", {"rawExperience": STORY_RAW, "targetRole": "데이터 분석"})
    fixtures["POST_stories"] = _fixture(request, response)
    story = response["body"]
    request, response = _call(deps, "GET", "/stories")
    fixtures["GET_stories"] = _fixture(request, response)
    request, response = _call(deps, "PATCH", f"/stories/{story['storyId']}",
                              {"baseVersion": story["version"], "confirmFields": ["situation"]})
    fixtures["PATCH_stories_id"] = _fixture(request, response)
    return fixtures


COVER_LETTER = ("데이터 분석 동아리에서 SQL 스터디를 1년 동안 운영했습니다. 스터디에서 다양한 데이터를 다뤘고 "
                "팀원들과 함께 성장했습니다. 결과가 좋았습니다.")
REVIEW_OUTPUT = {
    "questionIntent": "JOB_EXPERIENCE", "overallFeedback": "운영 경험이 직무와 이어지지만 본인이 한 일과 결과가 짧아요.",
    "strengths": ["직무와 관련된 경험을 골랐어요."],
    "issues": [
        {"originalText": "다양한 데이터를 다뤘고", "issueType": "MISSING_ACTION", "reason": "본인이 직접 한 일이 보이지 않아요.",
         "improvementAction": "직접 한 작업을 사실대로 적어 주세요.", "revisedExample": None,
         "questions": ["스터디에서 직접 맡은 일은 무엇이었나요?"]},
        {"originalText": "결과가 좋았습니다.", "issueType": "MISSING_RESULT", "reason": "결과가 구체적이지 않아요.",
         "improvementAction": "결과를 확인할 수 있게 적어 주세요.", "revisedExample": "참여율을 80%까지 올렸습니다."},
    ],
    "missingQuestions": ["스터디 결과를 어떻게 확인했나요?"],
}


def _plan(weeks: int) -> dict:
    return {"weeks": [{"week": w, "goals": [f"{w}주차 학습 목표"], "activities": [f"{w}주차 짧은 실습"],
                       "deliverable": f"{w}주차 실습 기록"} for w in range(1, weeks + 1)]}


def _flow_fixtures() -> dict[str, dict]:
    """적합도 → 첨삭 → 학습 경로. 공고·NCS·시험일정은 테스트 대역(가상)이다."""
    from datetime import timedelta

    from support.factory import FIXED_NOW

    deps = flow_deps([GOOD_LINKS, SUMMARY, REVIEW_OUTPUT, _plan(8)])

    def call(method, path, body=None):
        request = {"method": method, "path": path, **({"body": body} if body is not None else {})}
        response = rest_handler.handle(_event(method, path, body), deps, FLOW_USER)
        return request, {"status": response["statusCode"], "body": json.loads(response["body"])}

    fixtures = {}
    request, response = call("POST", "/analyses", {"profileId": "profile-1", "jobPostingId": "job-demo-busan-001"})
    fixtures["POST_analyses"] = _fixture(request, response)
    analysis_id = response["body"]["analysisId"]
    request, response = call("GET", f"/analyses/{analysis_id}")
    fixtures["GET_analyses_id_PENDING"] = _fixture(request, response)
    run_pending(deps)
    request, response = call("GET", f"/analyses/{analysis_id}")
    fixtures["GET_analyses_id_COMPLETED"] = _fixture(request, response)

    request, response = call("POST", "/reviews", {"inputText": COVER_LETTER, "analysisId": analysis_id,
                                                  "questionText": "직무 관련 경험을 설명해 주세요", "maxCharacters": 500})
    fixtures["POST_reviews"] = _fixture(request, response)
    review_id = response["body"]["reviewId"]
    run_pending(deps)
    request, response = call("GET", f"/reviews/{review_id}")
    fixtures["GET_reviews_id_COMPLETED"] = _fixture(request, response)

    body = {"analysisId": analysis_id, "weeklyStudyHours": 8, "preferredFormat": "HYBRID",
            "targetDate": (FIXED_NOW.date() + timedelta(days=56)).isoformat()}
    request, response = call("POST", "/learning-paths", body)
    fixtures["POST_learning_paths"] = _fixture(request, response)
    path_id = response["body"]["learningPathId"]
    run_pending(deps)
    request, response = call("GET", f"/learning-paths/{path_id}")
    fixtures["GET_learning_paths_id_COMPLETED"] = _fixture(request, response)
    return fixtures


def write(output_dir: Path = HERE) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = build()
    for path in output_dir.glob("*.json"):
        if path.stem not in generated:
            path.unlink()
    for name, value in generated.items():
        (output_dir / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write()
