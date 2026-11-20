"""학습 경로 (mentoring-fit-review-learning Requirement 12~14, 개발계획서1 F-05·UT-11·UT-12·UT-13). 데이터는 모두 가상이다."""
from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from mentoring.api import rest_handler
from mentoring.config import get_config
from mentoring.learning.service import assign_targets, plan_weeks
from mentoring.store.results import MemoryExamSchedules
from support.factory import FIXED_NOW, run_pending
from support.fit import GOOD_LINKS, NCS_DATA, SUMMARY
from support.flow import QUAL, call as _call, completed_analysis, exam_rows, flow_deps


def plan(weeks):
    return {"weeks": [{"week": w, "goals": [f"{w}주차 목표"], "activities": [f"{w}주차 실습"],
                       "deliverable": f"{w}주차 산출물"} for w in range(1, weeks + 1)]}


def call(deps, *args, **kwargs):
    return _call(rest_handler, deps, *args, **kwargs)


def learning_path(deps, analysis_id, **body):
    status, created = call(deps, "POST", "/learning-paths",
                           {"analysisId": analysis_id, "weeklyStudyHours": 8, "preferredFormat": "HYBRID", **body})
    assert status == 202, created
    run_pending(deps)
    status, result = call(deps, "GET", f"/learning-paths/{created['learningPathId']}")
    assert status == 200
    return result


def codes(result):
    return [w["code"] for w in result["warnings"]]


TARGET = (FIXED_NOW.date() + timedelta(days=56)).isoformat()  # 8주


def test_posting_path_weeks_hours_certificates_and_schedule():
    deps = flow_deps([GOOD_LINKS, SUMMARY, plan(8)])
    analysis_id = completed_analysis(rest_handler, deps)
    result = learning_path(deps, analysis_id, targetDate=TARGET)
    assert result["status"] == "COMPLETED"
    # 주차·시간은 코드 계산 (Requirement 12 기준 4)
    assert result["totalWeeks"] == 8 and result["totalHours"] == 64
    assert all(w["estimatedHours"] <= 8 for w in result["weeks"])
    assert result["weeks"][0]["startDate"] == FIXED_NOW.date().isoformat() and result["weeks"][0]["goals"]
    kinds = [t["kind"] for t in result["targets"]]
    assert kinds == ["STRENGTHEN_EVIDENCE", "NCS_UNIT", "NCS_UNIT"]  # 증빙 보완(SQL) 다음 NCS 학습 목표
    assert {i for w in result["weeks"] for i in w["targetIds"]} == {t["targetId"] for t in result["targets"]}
    # 자격: 중복 제거, 자격 정보 없는 후보(X999) 제외, 공고 필수 자격으로 표시하지 않음 (UT-13)
    [cert] = result["certificates"]
    assert cert["qualificationCode"] == QUAL and cert["linkedUnitCodes"] == ["2001010501_23v2", "2001010502_23v2"]
    assert cert["requiredByPosting"] is False and "필수 자격은 아니에요" in cert["reason"]
    assert cert["officialUrl"] and cert["checkedAt"] and cert["verificationStatus"] == "VERIFIED"
    [round_] = cert["schedule"]  # 지난 회차는 빼고 앞으로의 회차만
    assert round_["dates"]["finalResultDate"] == "2026-12-23" and round_["resultAfterPostingDeadline"] is True
    # 교육과정은 미연결 (UT-12), 정책은 B 정책 지갑 링크 (M-10)
    assert result["courses"] == [] and result["sourceVerificationStatus"] == {
        "qualifications": "REFERENCE_DATA", "examSchedule": "VERIFIED", "courses": "NOT_CONNECTED"}
    assert {"ESTIMATED", "NO_LIVE_COURSES", "NCS_LINK_NOTE", "RESULT_AFTER_DEADLINE"} <= set(codes(result))
    assert result["relatedLinks"][0] == {"type": "POLICY_WALLET", "path": "/policies",
                                         "label": "부산 청년 지원 정책은 정책 지갑에서 확인해요"}
    assert "ownerUserId" not in result


def test_ut11_schedule_unverified_never_invents_dates():
    for exams in (None, MemoryExamSchedules()):  # 연결 안 됨 / 수집 자료 없음
        deps = flow_deps([GOOD_LINKS, SUMMARY, plan(8)], exams=exams)
        result = learning_path(deps, completed_analysis(rest_handler, deps))
        [cert] = result["certificates"]
        assert cert["verificationStatus"] == "SCHEDULE_UNVERIFIED" and "schedule" not in cert
        assert cert["checkedAt"] == "2026-11-20" and "SCHEDULE_UNVERIFIED" in codes(result)

    stale = MemoryExamSchedules()  # 기한이 지난 캐시
    stale.put(QUAL, FIXED_NOW.year, exam_rows(), collected_at="2026-11-01T06:00:00+09:00",
              expires_at=int((FIXED_NOW - timedelta(days=1)).timestamp()))
    deps = flow_deps([GOOD_LINKS, SUMMARY, plan(8)], exams=stale)
    assert learning_path(deps, completed_analysis(rest_handler, deps))["certificates"][0]["verificationStatus"] == \
        "SCHEDULE_UNVERIFIED"


def test_exam_source_failure_is_partial_success():
    class Broken:
        def get(self, code, year):
            raise RuntimeError("cache down")

    deps = flow_deps([GOOD_LINKS, SUMMARY, plan(8)], exams=Broken())
    result = learning_path(deps, completed_analysis(rest_handler, deps))
    assert result["status"] == "PARTIAL_SUCCESS" and "EXAM_SOURCE_FAILED" in codes(result)
    assert result["sourceVerificationStatus"]["examSchedule"] == "FAILED"
    assert any(m.get("OfficialSourceFailure") == 1 for m in deps.metrics)


def test_plan_text_failure_uses_fallback_and_partial_success():
    deps = flow_deps([GOOD_LINKS, SUMMARY, "not-json", {"weeks": []}])
    result = learning_path(deps, completed_analysis(rest_handler, deps))
    assert result["status"] == "PARTIAL_SUCCESS" and "PLAN_TEXT_FALLBACK" in codes(result)
    assert all(w["goals"] and w["activities"] and w["deliverable"] for w in result["weeks"])
    assert result["totalWeeks"] == get_config().learning.default_weeks


def test_unverified_only_creates_verification_tasks_not_lessons():
    links = {"links": []}  # NCS 기준 분석에서 연결이 하나도 없다 → 모두 미확인
    deps = flow_deps([links, SUMMARY])
    analysis_id = completed_analysis(rest_handler, deps, {"profileId": "profile-1", "targetNcsCode": NCS_DATA})
    calls = len(deps.llm.calls)
    result = learning_path(deps, analysis_id)
    assert result["targets"] == [] and result["weeks"] == [] and result["totalWeeks"] == 0
    assert [v["requirementId"] for v in result["verificationTasks"]] == ["2001010501_23v2", "2001010502_23v2"]
    assert all(v["question"] for v in result["verificationTasks"]) and "VERIFY_FIRST" in codes(result)
    assert len(deps.llm.calls) == calls  # 계획 문장을 만들 대상이 없으면 모델을 부르지 않는다


def test_no_gaps_gives_strength_deepening_plan():
    links = {"links": [{"requirementId": "2001010501_23v2", "skillIds": ["skill-1"], "evidenceIds": ["ev-1"]},
                       {"requirementId": "2001010502_23v2", "skillIds": ["skill-2"], "evidenceIds": ["ev-2"]}]}
    deps = flow_deps([links, SUMMARY, plan(8)])
    analysis_id = completed_analysis(rest_handler, deps, {"profileId": "profile-1", "targetNcsCode": NCS_DATA})
    result = learning_path(deps, analysis_id)
    assert {t["kind"] for t in result["targets"]} == {"DEEPEN_STRENGTH"} and "NO_GAPS" in codes(result)


def test_request_validation():
    deps = flow_deps([GOOD_LINKS, SUMMARY])
    analysis_id = completed_analysis(rest_handler, deps)
    base = {"analysisId": analysis_id, "weeklyStudyHours": 8}
    for bad in ({"weeklyStudyHours": 0}, {"weeklyStudyHours": 41}, {"preferredFormat": "VR"},
                {"targetDate": FIXED_NOW.date().isoformat()}, {"targetDate": "2027/01/01"},
                {"startDate": (FIXED_NOW.date() - timedelta(days=1)).isoformat()}):
        assert call(deps, "POST", "/learning-paths", {**base, **bad})[0] == 400, bad
    assert call(deps, "POST", "/learning-paths", base, user_id="user-b")[0] == 404
    assert call(deps, "POST", "/learning-paths", {**base, "analysisId": "analysis-none"})[0] == 404


def test_analysis_must_be_completed_and_ncs_must_be_chosen():
    from mentoring.models import TaskStatus

    deps = flow_deps([GOOD_LINKS, SUMMARY])
    status, created = call(deps, "POST", "/analyses", {"profileId": "profile-1", "jobPostingId": "job-demo-busan-001"})
    assert call(deps, "POST", "/learning-paths",
                {"analysisId": created["analysisId"], "weeklyStudyHours": 8})[0] == 409  # 아직 PENDING

    from support.fit import busan_posting
    deps = flow_deps([GOOD_LINKS, SUMMARY],
                     posting=busan_posting(job={"name": "데이터", "ncsCodes": [NCS_DATA, "20010106"]}))
    analysis_id = completed_analysis(rest_handler, deps)
    assert deps.analyses.get_analysis("user-a", analysis_id).status == TaskStatus.COMPLETED
    status, body = call(deps, "POST", "/learning-paths", {"analysisId": analysis_id, "weeklyStudyHours": 8})
    assert status == 400 and body["error"]["details"]["candidates"] == [NCS_DATA, "20010106"]
    status, _ = call(deps, "POST", "/learning-paths",
                     {"analysisId": analysis_id, "weeklyStudyHours": 8, "ncsCode": NCS_DATA})
    assert status == 202


@given(count=st.integers(0, 12), weeks=st.integers(0, 30))
def test_every_target_is_planned_in_priority_order(count, weeks):
    slots = assign_targets(count, weeks)
    assert len(slots) == weeks
    flat = [i for slot in slots for i in slot]
    if weeks and count:
        assert set(flat) == set(range(count))  # 빠지는 학습 대상이 없다
    assert flat == sorted(flat)  # 우선순위 순서를 지킨다


@given(days=st.integers(1, 400))
def test_weeks_are_within_config_bounds(days):
    cfg = get_config().learning
    start = date(2026, 11, 21)
    weeks = plan_weeks(start, start + timedelta(days=days), cfg)
    assert cfg.min_weeks <= weeks <= cfg.max_weeks
