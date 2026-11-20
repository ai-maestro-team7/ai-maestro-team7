"""REST 입구 `/api/v1/opportunities/*`. 경로마다 성공 하나와 오류 형식(400, 404, 409, 422).

다른 워크트리 몫인 비즈니스 함수는 monkeypatch로 대신한다.
"""

import json
import logging
from urllib.parse import urlencode

import pytest

from opportunity.api import rest_handler
from opportunity.models import (
    AlternativesResponse,
    BasicProfile,
    CompareResponse,
    CompareSide,
    CostAdjusted,
    EligibilityResult,
    ExplanationResponse,
    FeedResponse,
    OppPrefs,
    PolicyApplicationView,
    PolicyCard,
    PolicyDetailResponse,
    PolicyJudgement,
    PolicyTotals,
    PolicyWalletResponse,
    PostingDetailResponse,
    ProfileUsed,
    Ranking,
    Sort,
    posting_not_found,
    profile_incomplete,
)
from opportunity.seeds import demo_world as w

BASE = "/api/v1/opportunities"


def http_event(method, path, *, query=None, body=None, headers=None, raw_body=None):
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": urlencode(query or {}),
        "headers": {"content-type": "application/json", **(headers or {})},
        "queryStringParameters": query or None,
        "requestContext": {"requestId": "req-test", "stage": "$default",
                           "http": {"method": method, "path": path, "protocol": "HTTP/1.1", "sourceIp": "127.0.0.1",
                                    "userAgent": "pytest"}},
        "body": raw_body if raw_body is not None else (json.dumps(body, ensure_ascii=False) if body is not None
                                                       else None),
        "isBase64Encoded": False,
    }


def call(deps, method, path, *, user_id="demo1", **kwargs):
    response = rest_handler.handle(http_event(method, BASE + path, **kwargs), deps, user_id)
    return response["statusCode"], json.loads(response["body"]) if response.get("body") else None


def assert_error(status, body, expected_status, code):
    assert status == expected_status
    assert set(body["error"]) == {"code", "message", "requestId", "retryable", "details"}
    assert body["error"]["code"] == code and body["error"]["requestId"] == "req-test"


@pytest.fixture
def demo_time(deps):
    for user in ("demo1", "demo2", "demo3"):
        deps.users.put_prefs(user, OppPrefs(demo_as_of=w.DEMO_AS_OF))
    return deps


@pytest.fixture
def seen():
    return {}


# ---------------------------------------------------------------- 공고
def test_get_postings_parses_camel_query_and_ignores_user_id(deps, monkeypatch, seen):
    def fake(deps_, user_id, **kwargs):
        seen.update(user_id=user_id, **kwargs)
        return FeedResponse(ranking=Ranking(sort=Sort.MATCH, basis="잘 맞는 순서로 보여드려요"), data_as_of=w.DATA_AS_OF)

    monkeypatch.setattr(rest_handler, "search_postings", fake)
    status, body = call(deps, "GET", "/postings", query={"region": "BUSAN", "sort": "MATCH", "jobCodes": "D0101,D0102",
                                                        "limit": "10", "userId": "demo2"})
    assert status == 200 and body["ranking"]["sort"] == "MATCH" and body["dataAsOf"] == w.DATA_AS_OF
    assert seen == {"user_id": "demo1", "region": "BUSAN", "sort": Sort.MATCH, "job_codes": ["D0101", "D0102"],
                    "limit": 10}


def test_get_postings_bad_query_is_400(deps, monkeypatch):
    monkeypatch.setattr(rest_handler, "search_postings", lambda *a, **k: pytest.fail("불리면 안 된다"))
    status, body = call(deps, "GET", "/postings", query={"sort": "LOUDEST"})
    assert_error(status, body, 400, "INVALID_INPUT")
    assert body["error"]["details"]["fields"] == ["sort"]
    status, body = call(deps, "GET", "/postings", query={"limit": "0"})
    assert_error(status, body, 400, "INVALID_INPUT")


def test_get_postings_profile_incomplete_is_422(deps, monkeypatch):
    def fake(*args, **kwargs):
        raise profile_incomplete(["desiredJobs"])

    monkeypatch.setattr(rest_handler, "search_postings", fake)
    status, body = call(deps, "GET", "/postings")
    assert_error(status, body, 422, "PROFILE_INCOMPLETE")
    assert body["error"]["details"] == {"missingFields": ["desiredJobs"]}


def test_get_posting_detail(deps, monkeypatch):
    snap = deps.catalog.get_snapshot(w.BUSAN_DATA, deps.catalog.get_latest(w.BUSAN_DATA).snapshot_id)
    monkeypatch.setattr(rest_handler, "get_posting", lambda d, u, pid, **k: PostingDetailResponse(
        posting=snap, is_busan=True, is_capital_area=False, eligibility=EligibilityResult(status="ELIGIBLE")))
    status, body = call(deps, "GET", f"/postings/{w.BUSAN_DATA}")
    assert status == 200 and body["posting"]["jobPostingId"] == w.BUSAN_DATA and body["isBusan"] is True


def test_get_posting_not_found_is_404(deps, monkeypatch):
    def fake(deps_, user_id, job_posting_id, **kwargs):
        raise posting_not_found(job_posting_id)

    monkeypatch.setattr(rest_handler, "get_posting", fake)
    status, body = call(deps, "GET", "/postings/wk24-NOPE")
    assert_error(status, body, 404, "POSTING_NOT_FOUND")
    assert body["error"]["details"] == {"jobPostingId": "wk24-NOPE"} and body["error"]["retryable"] is False


def test_id_with_hash_is_400(deps, monkeypatch):
    monkeypatch.setattr(rest_handler, "get_posting", lambda *a, **k: pytest.fail("불리면 안 된다"))
    status, body = call(deps, "GET", "/postings/wk24%23DEMO")
    assert_error(status, body, 400, "INVALID_INPUT")


def test_get_explanation(deps, monkeypatch):
    monkeypatch.setattr(rest_handler, "explain_posting", lambda d, u, pid, **k: ExplanationResponse(
        job_posting_id=pid, sentences=["희망 직무와 같은 직종이에요."], facts=["직종 일치"]))
    status, body = call(deps, "GET", f"/postings/{w.BUSAN_DATA}/explanation")
    assert status == 200 and body["sentences"] == ["희망 직무와 같은 직종이에요."]


def test_get_alternatives(deps, monkeypatch, seen):
    def fake(deps_, user_id, job_posting_id, **kwargs):
        seen.update(job_posting_id=job_posting_id, **kwargs)
        return AlternativesResponse(base_job_posting_id=job_posting_id, no_alternative=True)

    monkeypatch.setattr(rest_handler, "find_busan_alternatives", fake)
    status, body = call(deps, "GET", f"/postings/{w.SEOUL_GAME}/alternatives", query={"leaveReason": "SALARY"})
    assert status == 200 and body["noAlternative"] is True
    assert seen == {"job_posting_id": w.SEOUL_GAME, "leave_reason": "SALARY"}


def test_get_compare(deps, monkeypatch, seen):
    def fake(deps_, user_id, base, alt, **kwargs):
        seen.update(base=base, alt=alt, **kwargs)
        return CompareResponse(base=CompareSide(job_posting_id=base, label="서울"),
                               alt=CompareSide(job_posting_id=alt, label="부산"), rows=[],
                               cost_adjusted=CostAdjusted(available=False))

    monkeypatch.setattr(rest_handler, "compare_postings", fake)
    status, body = call(deps, "GET", "/compare", query={"baseJobPostingId": w.SEOUL_DATA,
                                                        "altJobPostingId": w.BUSAN_DATA, "familyHousing": "true"})
    assert status == 200 and body["base"]["jobPostingId"] == w.SEOUL_DATA
    assert seen == {"base": w.SEOUL_DATA, "alt": w.BUSAN_DATA, "family_housing": True}
    status, body = call(deps, "GET", "/compare", query={"baseJobPostingId": w.SEOUL_DATA})
    assert_error(status, body, 400, "INVALID_INPUT")
    assert body["error"]["details"]["fields"] == ["altJobPostingId"]


# ---------------------------------------------------------------- 정책
def policy_card():
    return PolicyCard(policy_id=w.P_BUSAN_INTERVIEW, title="[데모] 부산 청년 면접 지원", stage="PREPARE",
                      bucket="OPEN_NOW", eligibility=PolicyJudgement(status="ELIGIBLE"),
                      application=PolicyApplicationView(), source="YOUTHCENTER", as_of="2026-11-21")


def test_get_policies(deps, monkeypatch, seen):
    def fake(deps_, user_id, **kwargs):
        seen.update(kwargs)
        return PolicyWalletResponse(profile_used=ProfileUsed(), buckets={"OPEN_NOW": [policy_card()]},
                                    totals=PolicyTotals())

    monkeypatch.setattr(rest_handler, "match_policies", fake)
    status, body = call(deps, "GET", "/policies", query={"stage": "PREPARE"})
    assert status == 200 and body["buckets"]["OPEN_NOW"][0]["policyId"] == w.P_BUSAN_INTERVIEW
    assert seen == {"stage": "PREPARE"}
    status, body = call(deps, "GET", "/policies", query={"stage": "RETIRE"})
    assert_error(status, body, 400, "INVALID_INPUT")


def test_get_policy_detail(deps, monkeypatch):
    monkeypatch.setattr(rest_handler, "get_policy", lambda d, u, pid, **k: PolicyDetailResponse(policy=policy_card()))
    status, body = call(deps, "GET", f"/policies/{w.P_BUSAN_INTERVIEW}")
    assert status == 200 and body["policy"]["title"] == "[데모] 부산 청년 면접 지원"


def test_post_policy_alert_created_then_same_result(demo_time):
    deps = demo_time
    status, body = call(deps, "POST", f"/policies/{w.P_JOY_DOUBLE}/alerts", headers={"Idempotency-Key": "a-1"})
    assert status == 201 and body == {"alert": {"policyId": w.P_JOY_DOUBLE,
                                                "scheduledAt": "2027-08-10T09:00:00+09:00"}, "created": True}
    status, again = call(deps, "POST", f"/policies/{w.P_JOY_DOUBLE}/alerts")
    assert status == 200 and again["created"] is False and again["alert"] == body["alert"]
    status, body = call(deps, "POST", f"/policies/{w.P_UNVERIFIED}/alerts")
    assert_error(status, body, 404, "POLICY_NOT_FOUND")


# ---------------------------------------------------------------- 설정
def test_preferences_get_and_put(deps):
    status, body = call(deps, "GET", "/me/preferences")
    assert status == 200 and body == {"sort": "BUSAN_FIRST", "notifications": {"email": False, "weekly": False},
                                      "receivingPolicies": []}
    status, body = call(deps, "PUT", "/me/preferences", body={"leaveReason": "SALARY", "sort": "MATCH",
                                                              "userId": "demo2"})
    assert status == 200 and body["leaveReason"] == "SALARY" and body["sort"] == "MATCH"
    assert deps.users.get_prefs("demo2").leave_reason is None  # 본문의 userId는 쓰지 않는다
    assert "BUSAN_FIRST_OFF" in deps.events.names()


def test_preferences_bad_body_is_400(deps):
    status, body = call(deps, "PUT", "/me/preferences", body={"leaveReason": "MONEY"})
    assert_error(status, body, 400, "INVALID_INPUT")
    status, body = call(deps, "PUT", "/me/preferences", raw_body="{not json")
    assert_error(status, body, 400, "INVALID_INPUT")
    status, body = call(deps, "PUT", "/me/preferences", raw_body="[1, 2]")
    assert_error(status, body, 400, "INVALID_INPUT")


# ---------------------------------------------------------------- 저장
def test_post_saved_201_and_list(demo_time):
    deps = demo_time
    status, body = call(deps, "POST", "/saved", user_id="demo3", headers={"Idempotency-Key": "s-1"},
                        body={"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "kind": "TARGET", "userId": "demo1"})
    assert status == 201 and body["created"] is True
    assert body["saved"]["status"] == "PLANNED" and [s["label"] for s in body["schedules"]] == ["마감 D-7", "마감 D-3"]
    assert deps.users.get_saved("demo1", w.BUSAN_FINANCE_PUBLIC) is None
    status, replay = call(deps, "POST", "/saved", user_id="demo3", headers={"idempotency-key": "s-1"},
                          body={"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "kind": "TARGET"})
    assert status == 201 and replay == body  # T-16: 같은 키는 같은 결과
    status, listed = call(deps, "GET", "/saved", user_id="demo3")
    assert status == 200 and [i["jobPostingId"] for i in listed["items"]] == [w.BUSAN_FINANCE_PUBLIC]


def test_post_saved_conflict_is_409(demo_time):
    deps = demo_time
    call(deps, "POST", "/saved", headers={"Idempotency-Key": "s-1"}, body={"jobPostingId": w.BUSAN_DATA})
    status, body = call(deps, "POST", "/saved", headers={"Idempotency-Key": "s-1"},
                        body={"jobPostingId": w.BUSAN_DATA, "kind": "TARGET"})
    assert_error(status, body, 409, "PRECONDITION_NOT_MET")


def test_post_saved_existing_is_200(demo_time):
    deps = demo_time
    assert call(deps, "POST", "/saved", body={"jobPostingId": w.SEOUL_DATA})[1]["askLeaveReason"] is True
    status, body = call(deps, "POST", "/saved", body={"jobPostingId": w.SEOUL_DATA})
    assert status == 200 and body["created"] is False and body["askLeaveReason"] is False


def test_post_saved_errors(demo_time):
    deps = demo_time
    assert_error(*call(deps, "POST", "/saved", body={"jobPostingId": "wk24-NOPE"}), 404, "POSTING_NOT_FOUND")
    assert_error(*call(deps, "POST", "/saved", body={"kind": "TARGET"}), 400, "INVALID_INPUT")
    assert_error(*call(deps, "POST", "/saved", body={"jobPostingId": w.BUSAN_DATA, "kind": "LOVE"}), 400,
                 "INVALID_INPUT")
    assert_error(*call(deps, "POST", "/saved"), 400, "INVALID_INPUT")


def test_delete_saved(demo_time):
    deps = demo_time
    call(deps, "POST", "/saved", user_id="demo3", body={"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "kind": "TARGET"})
    assert len(deps.scheduler.schedules) == 2
    status, body = call(deps, "DELETE", f"/saved/{w.BUSAN_FINANCE_PUBLIC}", user_id="demo3")
    assert status == 200 and body == {"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "deleted": True}
    assert deps.scheduler.schedules == {} and call(deps, "GET", "/saved", user_id="demo3")[1]["items"] == []
    status, body = call(deps, "DELETE", f"/saved/{w.BUSAN_FINANCE_PUBLIC}", user_id="demo3")
    assert status == 200 and body["deleted"] is False
    assert_error(*call(deps, "DELETE", "/saved/wk24%231"), 400, "INVALID_INPUT")


# ---------------------------------------------------------------- 알림
def test_notifications_and_read(demo_time):
    deps = demo_time
    call(deps, "POST", "/saved", user_id="demo3", body={"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "kind": "TARGET"})
    status, clock_body = call(deps, "POST", "/admin/demo-clock", user_id="demo3",
                              body={"asOf": "2026-12-05T09:00:00+09:00"})
    assert status == 200 and clock_body == {"asOf": "2026-12-05T09:00:00+09:00", "fired": 2, "simulated": True}
    status, body = call(deps, "GET", "/notifications", user_id="demo3", query={"limit": "1"})
    assert status == 200 and len(body["items"]) == 1 and body["nextCursor"]
    first = body["items"][0]
    assert first["simulated"] is True and first["read"] is False
    status, body = call(deps, "POST", f"/notifications/{first['notificationId']}/read", user_id="demo3")
    assert status == 200 and body == {"notificationId": first["notificationId"], "read": True}
    status, body = call(deps, "POST", "/notifications/20261201T090000-00000000/read", user_id="demo3")
    assert_error(status, body, 404, "NOTIFICATION_NOT_FOUND")


def test_demo_clock_only_for_demo_accounts(deps):
    deps.users.profiles["real-user"] = BasicProfile(is_demo=False)
    for user in ("real-user", "nobody"):
        status, body = call(deps, "POST", "/admin/demo-clock", user_id=user, body={"asOf": "2026-12-05"})
        assert_error(status, body, 404, "NOT_FOUND")
    assert deps.users.get_prefs("real-user").demo_as_of is None


def test_demo_clock_bad_date_is_400(deps):
    status, body = call(deps, "POST", "/admin/demo-clock", user_id="demo1", body={"asOf": "next week"})
    assert_error(status, body, 400, "INVALID_INPUT")


# ---------------------------------------------------------------- 화면 이벤트
def test_track_records_event_without_user_id(deps):
    status, body = call(deps, "POST", "/track", body={"event": "ALT_CLICKED", "jobPostingId": w.BUSAN_DATA,
                                                      "userId": "demo1"})
    assert status == 200 and body == {"recorded": True}
    assert deps.events.events == [("ALT_CLICKED", {"jobPostingId": w.BUSAN_DATA})]


def test_track_rejects_server_events(deps):
    for event in ("SAVED", "ALT_SHOWN", "NOPE"):
        assert_error(*call(deps, "POST", "/track", body={"event": event}), 400, "INVALID_INPUT")
    assert deps.events.events == []


# ---------------------------------------------------------------- 그 밖의 오류
def test_unknown_route_is_404(deps):
    assert_error(*call(deps, "GET", "/nothing-here"), 404, "NOT_FOUND")


def test_unexpected_error_is_500_without_details(deps, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("이력서 원문")

    monkeypatch.setattr(rest_handler, "search_postings", broken)
    status, body = call(deps, "GET", "/postings")
    assert_error(status, body, 500, "INTERNAL_ERROR")
    assert body["error"]["retryable"] is True and "이력서" not in json.dumps(body, ensure_ascii=False)


def test_not_implemented_is_501(deps, monkeypatch):
    def not_yet(*args, **kwargs):
        raise NotImplementedError("core-policy")

    monkeypatch.setattr(rest_handler, "compare_postings", not_yet)
    status, body = call(deps, "GET", "/compare", query={"baseJobPostingId": "a", "altJobPostingId": "b"})
    assert_error(status, body, 501, "NOT_IMPLEMENTED")


def test_log_line_has_only_allowed_fields(deps, caplog):
    with caplog.at_level(logging.INFO, logger="opportunity.api"):
        call(deps, "PUT", "/me/preferences", body={"receivingPolicies": ["청년내일저축계좌"]})
    [record] = [r for r in caplog.records if r.name == "opportunity.api"]
    line = json.loads(record.getMessage())
    assert set(line) == {"requestId", "method", "path", "status", "durationMs", "errorCode"}
    assert line["requestId"] == "req-test" and line["status"] == 200 and line["errorCode"] is None
    assert "demo1" not in record.getMessage() and "청년내일저축계좌" not in record.getMessage()
