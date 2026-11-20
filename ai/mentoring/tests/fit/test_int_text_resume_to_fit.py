"""통합: 텍스트 이력서 → 역량 프로필 → 직무 적합도 (A §13 INT-02 앞부분, D-37 데이터 분석). 데이터는 모두 가상이다."""
import json

from mentoring.api import rest_handler
from mentoring.fit.store import MemoryAnalysisStore, MemoryCatalog
from mentoring.llm.mock import MockLlm
from support.data import DATA_ANALYST_RESUME, good_output
from support.factory import make_deps, run_pending
from support.fit import SUMMARY, FakeKnowledge, FakeNcs, busan_posting, fake_eligibility

BASE = "/api/v1/mentoring"


def call(deps, method, path, body=None):
    event = {
        "version": "2.0", "routeKey": "$default", "rawPath": BASE + path, "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {"requestId": "req-int", "stage": "$default",
                           "http": {"method": method, "path": BASE + path, "protocol": "HTTP/1.1",
                                    "sourceIp": "127.0.0.1", "userAgent": "pytest"}},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None, "isBase64Encoded": False,
    }
    response = rest_handler.handle(event, deps, "user-int")
    return response["statusCode"], json.loads(response["body"])


def test_text_resume_to_confirmed_profile_to_job_fit():
    links = {"links": [  # 역량 추출이 만든 skill ID를 고른다. 근거 ID는 비워도 코드가 그 역량의 근거로 채운다
        {"requirementId": "req-1", "skillIds": ["skill-3"]},
        {"requirementId": "req-2", "skillIds": ["skill-1"]},
        {"requirementId": "req-3", "skillIds": ["skill-2"]},
    ]}
    deps = make_deps()
    deps.llm = MockLlm([good_output(), links, SUMMARY], model_id="mock-int")
    deps.analyses, deps.catalog, deps.ncs = MemoryAnalysisStore(), MemoryCatalog(), FakeNcs()
    deps.knowledge, deps.eligibility = FakeKnowledge(), fake_eligibility
    deps.catalog.put_posting(busan_posting())
    deps.analyses.put_basic_profile("user-int", {"educationLevel": "BACHELOR", "major": "통계학"})

    status, _ = call(deps, "POST", "/documents/text", {"text": DATA_ANALYST_RESUME, "documentType": "RESUME"})
    assert status == 202
    run_pending(deps)
    status, profile = call(deps, "GET", "/profiles/me")
    assert status == 200
    status, confirmed = call(deps, "POST", f"/profiles/{profile['profileId']}/confirm", {
        "baseVersion": profile["profileVersion"], "decisions": [{"skillId": "skill-1", "action": "CONFIRM"}]})
    assert status == 201, confirmed

    status, created = call(deps, "POST", "/analyses",
                           {"profileId": confirmed["profileId"], "jobPostingId": "job-demo-busan-001"})
    assert status == 202
    run_pending(deps)
    status, result = call(deps, "GET", f"/analyses/{created['analysisId']}")
    assert status == 200 and result["status"] == "COMPLETED"
    assert result["profileVersion"] == confirmed["profileVersion"]
    assert (result["fitScore"], result["potentialUpperBound"]) == (81, 81)
    assert result["eligibility"]["status"] == "ELIGIBLE"  # 이력서 원문에 인용이 있는 ADsP
    quotes = [e["quotedText"] for s in result["strengths"] + result["partialEvidence"] for e in s["evidence"]]
    assert quotes and all(q in DATA_ANALYST_RESUME for q in quotes)  # 근거는 모두 원문에 있다
