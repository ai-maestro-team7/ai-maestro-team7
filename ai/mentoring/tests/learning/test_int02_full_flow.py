"""INT-02: 텍스트 이력서 → 역량 프로필 → 직무 적합도 → 자기소개서 첨삭 → 학습 경로 (개발계획서1 §13, D-37 데이터 분석).
같은 프로필 버전과 공고 스냅샷을 끝까지 이어서 쓰는지 본다. 외부 서비스는 부르지 않고, 데이터는 모두 가상이다."""
from datetime import timedelta

from mentoring.api import rest_handler
from mentoring.fit.store import MemoryAnalysisStore, MemoryCatalog
from mentoring.llm.mock import MockLlm
from mentoring.store.results import MemoryExamSchedules, MemoryResultStore
from support.data import DATA_ANALYST_RESUME, QUOTE_SQL, good_output
from support.factory import FIXED_NOW, make_deps, run_pending
from support.fit import SUMMARY, FakeKnowledge, busan_posting, fake_eligibility
from support.flow import QUAL, FakeNcsWithQualifications, call as _call, exam_rows

USER = "user-int02"
COVER_LETTER = ("데이터 분석 동아리에서 SQL 스터디를 1년 동안 운영했습니다. 스터디에서 다양한 데이터를 다뤘고 "
                "팀원들과 함께 성장했습니다. 이 경험을 살려 데이터 분석 직무에서 일하고 싶습니다.")


def call(deps, method, path, body=None):
    return _call(rest_handler, deps, method, path, body, user_id=USER)


def test_resume_to_fit_to_review_to_learning_path():
    links = {"links": [{"requirementId": "req-1", "skillIds": ["skill-3"]},
                       {"requirementId": "req-2", "skillIds": ["skill-1"]},
                       {"requirementId": "req-3", "skillIds": ["skill-2"]}]}
    review = {"questionIntent": "JOB_EXPERIENCE", "overallFeedback": "운영 경험이 직무와 이어져요.",
              "strengths": ["직무와 관련된 경험을 골랐어요."],
              "issues": [{"originalText": "다양한 데이터를 다뤘고", "issueType": "MISSING_ACTION",
                          "reason": "본인이 직접 한 일이 보이지 않아요.", "improvementAction": "직접 한 작업을 적어 주세요.",
                          "revisedExample": None, "questions": ["스터디에서 직접 맡은 일은 무엇이었나요?"]}],
              "missingQuestions": []}
    plan = {"weeks": [{"week": w, "goals": ["목표"], "activities": ["실습"], "deliverable": "산출물"}
                      for w in range(1, 9)]}

    deps = make_deps()
    deps.llm = MockLlm([good_output(), links, SUMMARY, review, plan], model_id="mock-int02")
    deps.analyses, deps.catalog, deps.ncs = MemoryAnalysisStore(), MemoryCatalog(), FakeNcsWithQualifications()
    deps.knowledge, deps.eligibility, deps.results = FakeKnowledge(), fake_eligibility, MemoryResultStore()
    deps.exams = MemoryExamSchedules()
    deps.exams.put(QUAL, FIXED_NOW.year, exam_rows(), collected_at="2026-11-21T06:00:00+09:00",
                   expires_at=int((FIXED_NOW + timedelta(days=1)).timestamp()))
    deps.catalog.put_posting(busan_posting())
    deps.analyses.put_basic_profile(USER, {"educationLevel": "BACHELOR", "major": "통계학"})

    # 1. 이력서 → 역량 프로필
    assert call(deps, "POST", "/documents/text", {"text": DATA_ANALYST_RESUME})[0] == 202
    run_pending(deps)
    status, profile = call(deps, "GET", "/profiles/me")
    assert status == 200 and profile["skills"]

    # 2. 직무 적합도 (공고)
    status, created = call(deps, "POST", "/analyses", {"profileId": profile["profileId"],
                                                       "jobPostingId": "job-demo-busan-001",
                                                       "workspaceId": "ws-job-demo-busan-001"})
    run_pending(deps)
    _, analysis = call(deps, "GET", f"/analyses/{created['analysisId']}")
    assert analysis["status"] == "COMPLETED" and analysis["fitScore"] is not None
    assert analysis["profileVersion"] == profile["profileVersion"]

    # 3. 자기소개서 첨삭 (같은 분석의 공고 스냅샷 기준)
    status, created = call(deps, "POST", "/reviews", {"inputText": COVER_LETTER, "analysisId": analysis["analysisId"],
                                                      "workspaceId": "ws-job-demo-busan-001"})
    run_pending(deps)
    _, reviewed = call(deps, "GET", f"/reviews/{created['reviewId']}")
    assert reviewed["status"] == "COMPLETED"
    assert reviewed["sourceJobSnapshotId"] == analysis["posting"]["snapshotId"]
    assert reviewed["issues"][0]["needsUserConfirmation"] is True

    # 4. 학습 경로 (같은 분석의 격차 기준)
    status, created = call(deps, "POST", "/learning-paths", {
        "analysisId": analysis["analysisId"], "weeklyStudyHours": 6, "workspaceId": "ws-job-demo-busan-001",
        "targetDate": (FIXED_NOW.date() + timedelta(days=56)).isoformat()})
    run_pending(deps)
    _, path = call(deps, "GET", f"/learning-paths/{created['learningPathId']}")
    assert path["status"] == "COMPLETED" and path["analysisId"] == analysis["analysisId"]
    assert path["totalWeeks"] == 8 and path["totalHours"] == 48
    assert path["certificates"][0]["verificationStatus"] == "VERIFIED"

    # 같은 워크스페이스에 세 결과가 모두 붙는다 (docs/api.md §6.0)
    gsi = f"USER#{USER}#WS#ws-job-demo-busan-001"
    linked = [i["GSI1SK"].split("#")[0] for store in (deps.analyses, deps.results)
              for i in store.items.values() if i.get("GSI1PK") == gsi]
    assert sorted(linked) == ["ANALYSIS", "PATH", "REVIEW"]
    # 근거 인용은 모두 이력서 원문에 있다
    quotes = [e["quotedText"] for s in analysis["strengths"] + analysis["partialEvidence"] for e in s["evidence"]]
    assert QUOTE_SQL in quotes and all(q in DATA_ANALYST_RESUME for q in quotes)
