"""데모 흐름을 대역 없이 처음부터 끝까지 돌린다 (개발계획서2 §12). REST 입구 → 실제 core·notify 함수.

설명 문장만 가짜 LLM을 쓴다. 나머지는 메모리 저장소의 데모 데이터로 계산한다.
"""

import json

import pytest

from opportunity.api import agent_handler, rest_handler
from opportunity.models import OppPrefs
from opportunity.seeds import demo_world as w
from opportunity.store.memory import ScriptedLlm

BASE = "/api/v1/opportunities"


def event(method, path, *, query=None, body=None, headers=None):
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": BASE + path,
        "rawQueryString": "&".join(f"{k}={v}" for k, v in (query or {}).items()),
        "queryStringParameters": {k: str(v) for k, v in (query or {}).items()} or None,
        "headers": {"content-type": "application/json", **(headers or {})},
        "requestContext": {"requestId": "req-flow", "stage": "$default",
                           "http": {"method": method, "path": BASE + path, "sourceIp": "127.0.0.1",
                                    "protocol": "HTTP/1.1", "userAgent": "pytest"}},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None, "isBase64Encoded": False,
    }


def call(deps, method, path, *, user="demo1", **kwargs):
    response = rest_handler.handle(event(method, path, **kwargs), deps, user)
    return response["statusCode"], json.loads(response["body"]) if response.get("body") else None


@pytest.fixture
def world(deps):
    for user in ("demo1", "demo2", "demo3"):
        deps.users.put_prefs(user, OppPrefs(demo_as_of=w.DEMO_AS_OF))
    return deps


def test_demo_scenario_persona1(world):
    deps = world
    # 1. 피드: 정렬 칩과 부산 공고
    status, feed = call(deps, "GET", "/postings")
    assert status == 200 and feed["ranking"]["sort"] == "BUSAN_FIRST" and feed["ranking"]["basis"]
    ids = [item["jobPostingId"] for item in feed["items"]]
    assert w.BUSAN_DATA in ids[:10] and w.SEOUL_DATA in ids
    assert w.BUSAN_DATA_EXPIRED not in ids and w.BUSAN_DATA_JUST_CLOSED not in ids
    assert all("matchLevel" in item for item in feed["items"])
    seoul_card = next(item for item in feed["items"] if item["jobPostingId"] == w.SEOUL_DATA)
    assert seoul_card["busanAlternativesCount"] >= 2

    # 같은 집합, 순서만 다름 (T-01)
    _, by_match = call(deps, "GET", "/postings", query={"sort": "MATCH"})
    assert sorted(ids) == sorted(item["jobPostingId"] for item in by_match["items"])

    # 2. 서울 공고 저장 → 이유 질문 한 번
    status, saved = call(deps, "POST", "/saved", body={"jobPostingId": w.SEOUL_DATA, "kind": "INTEREST"},
                         headers={"idempotency-key": "flow-1"})
    assert status == 201 and saved["askLeaveReason"] is True and saved["saved"]["isBusan"] is False
    status, prefs = call(deps, "PUT", "/me/preferences", body={"leaveReason": "SALARY"})
    assert status == 200 and prefs["leaveReason"] == "SALARY"

    # 3. 같은 일, 부산에서
    status, alts = call(deps, "GET", f"/postings/{w.SEOUL_DATA}/alternatives")
    assert status == 200 and alts["leaveReasonApplied"] == "SALARY" and not alts["noAlternative"]
    alt_ids = [a["jobPostingId"] for a in alts["alternatives"]]
    assert {w.BUSAN_DATA, w.BUSAN_DATA_PUBLIC} <= set(alt_ids) and len(alt_ids) <= 3
    assert all(a["similarity"] >= 0.70 for a in alts["alternatives"])

    # 상세: 대안 미리보기와 지원 자격
    status, detail = call(deps, "GET", f"/postings/{w.SEOUL_DATA}")
    assert status == 200 and detail["isCapitalArea"] and len(detail["alternativesPreview"]) == 2
    assert detail["eligibility"]["status"] == "ELIGIBLE"
    status, busan_detail = call(deps, "GET", f"/postings/{w.BUSAN_DATA}")
    assert status == 200 and busan_detail["relatedPolicies"]  # 부산 공고에는 관련 정책이 붙는다

    # 4. 나란히 비교: 서울이 높은 급여가 그대로 보인다
    status, compare = call(deps, "GET", "/compare", query={"baseJobPostingId": w.SEOUL_DATA,
                                                           "altJobPostingId": w.BUSAN_DATA})
    assert status == 200
    rows = {row["key"]: row for row in compare["rows"]}
    assert rows["SALARY"]["comparable"] is True and "4,000" in rows["SALARY"]["base"]
    assert "3,400" in rows["SALARY"]["alt"]
    assert "HOUSING" not in rows  # rentConversionRate가 null이라 주거비 행은 숨긴다
    assert rows["REGIONAL_POLICY"]["base"]["count"] >= 0 and rows["REGIONAL_POLICY"]["alt"]["count"] >= 1
    assert "winner" not in json.dumps(compare)

    # 5. 부산 공고를 목표로 담기 → 마감 일정
    status, target = call(deps, "POST", "/saved", headers={"idempotency-key": "flow-2"},
                          body={"jobPostingId": w.BUSAN_DATA, "kind": "TARGET", "fromAlternativeOf": w.SEOUL_DATA})
    assert status == 201 and target["askLeaveReason"] is False and target["saved"]["status"] == "PLANNED"
    assert [s["label"] for s in target["schedules"]] == ["마감 D-7", "마감 D-3"]
    status, again = call(deps, "POST", "/saved", headers={"idempotency-key": "flow-2"},
                         body={"jobPostingId": w.BUSAN_DATA, "kind": "TARGET", "fromAlternativeOf": w.SEOUL_DATA})
    assert again["saved"] == target["saved"]  # 같은 키는 한 번만 반영 (T-16)
    _, saved_list = call(deps, "GET", "/saved")
    assert {i["jobPostingId"] for i in saved_list["items"]} == {w.SEOUL_DATA, w.BUSAN_DATA}

    # 6. 정책 지갑: 기쁨두배통장은 "취업하면", 검수 전 정책은 없음
    status, wallet = call(deps, "GET", "/policies")
    assert status == 200
    after = [p["policyId"] for p in wallet["buckets"]["AFTER_EMPLOYMENT"]]
    assert w.P_JOY_DOUBLE in after
    assert w.P_UNVERIFIED not in json.dumps(wallet)
    status, alert = call(deps, "POST", f"/policies/{w.P_JOY_DOUBLE}/alerts", headers={"idempotency-key": "flow-3"})
    assert status in (200, 201) and alert["alert"]["policyId"] == w.P_JOY_DOUBLE

    # 7. 시간 앞당기기 → 시뮬레이션 알림
    status, clock = call(deps, "POST", "/admin/demo-clock", body={"asOf": "2026-12-03T09:30:00+09:00"})
    assert status == 200 and clock["simulated"] is True and clock["fired"] >= 1
    _, inbox = call(deps, "GET", "/notifications")
    assert inbox["items"] and all(n["simulated"] for n in inbox["items"])
    assert {n["type"] for n in inbox["items"]} == {"TARGET_DEADLINE"}

    # 유도 지표 이벤트
    names = deps.events.names()
    assert "SAVED" in names and "ALT_SHOWN" in names


def test_explanation_uses_real_facts(world):
    world.llm = ScriptedLlm(['{"sentences": ["희망 직무와 같은 직종의 공고예요.", "필수 조건을 모두 충족해요."]}'])
    status, body = call(world, "GET", f"/postings/{w.BUSAN_DATA}/explanation")
    assert status == 200 and len(body["sentences"]) == 2 and body["facts"]
    system, user = world.llm.calls[0]
    assert all(fact in user for fact in body["facts"])


def test_persona3_regional_talent_and_schedules(world):
    status, detail = call(world, "GET", f"/postings/{w.BUSAN_FINANCE_PUBLIC}", user="demo3")
    assert status == 200 and detail["regionalTalent"]["status"] == "LIKELY"
    assert "대상일 수 있어요" in detail["regionalTalent"]["message"]
    status, saved = call(world, "POST", "/saved", user="demo3", headers={"idempotency-key": "p3"},
                         body={"jobPostingId": w.BUSAN_FINANCE_PUBLIC, "kind": "TARGET"})
    assert status == 201 and len(saved["schedules"]) == 2 and saved["askLeaveReason"] is False


def test_persona2_badges_and_policies(world):
    _, feed = call(world, "GET", "/postings", user="demo2")
    badges = {b["type"] for item in feed["items"] for b in item["badges"]}
    assert {"CHEONGKKEUL", "GANGSO"} <= badges
    assert all(b.get("source") and b.get("asOf") for item in feed["items"] for b in item["badges"])  # T-08
    _, wallet = call(world, "GET", "/policies", user="demo2")
    prepare = [p["policyId"] for key in ("OPEN_NOW", "NEXT_CYCLE") for p in wallet["buckets"][key]]
    assert w.P_DIDIMDOL in prepare


def test_no_alternative_and_errors(world):
    status, alts = call(world, "GET", f"/postings/{w.SEOUL_GAME}/alternatives")
    assert status == 200 and alts["noAlternative"] is True and alts["alternatives"] == []
    assert "NO_ALTERNATIVE" in world.events.names()
    status, body = call(world, "GET", "/postings/wk24-NOPE")
    assert status == 404 and body["error"]["code"] == "POSTING_NOT_FOUND"
    status, body = call(world, "GET", "/postings", user="nobody")
    assert status == 422 and body["error"]["code"] == "PROFILE_INCOMPLETE"


def test_agent_tools_return_same_alternatives(world):
    """통합 Agent 입구가 REST와 같은 함수를 부른다. userId는 sessionAttributes에서만 읽는다 (T-20)."""
    agent_event = {
        "messageVersion": "1.0", "agent": {"name": "CareerMentoringAgent", "id": "A", "alias": "a", "version": "1"},
        "inputText": "부산에도 비슷한 데 있어?", "sessionId": "s-1", "actionGroup": "BusanOpportunity",
        "apiPath": f"/agent/postings/{w.SEOUL_DATA}/alternatives", "httpMethod": "GET",
        "parameters": [{"name": "jobPostingId", "type": "string", "value": w.SEOUL_DATA},
                       {"name": "userId", "type": "string", "value": "demo2"}],
        "sessionAttributes": {"userId": "demo1"}, "promptSessionAttributes": {},
    }
    response = agent_handler.handle(agent_event, world)
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    _, rest = call(world, "GET", f"/postings/{w.SEOUL_DATA}/alternatives")
    assert [a["jobPostingId"] for a in body["items"]] == [a["jobPostingId"] for a in rest["alternatives"]]
    assert "demo2" not in json.dumps(body)
