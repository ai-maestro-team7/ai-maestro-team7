"""Action Group `BusanOpportunity` (개발계획서2 §5.9). T-20, 응답 줄이기, 스키마.

다른 워크트리 몫인 비즈니스 함수는 monkeypatch로 대신한다.
"""

import json

import pytest

from opportunity.api import agent_handler
from opportunity.models import (
    AlternativeItem,
    AlternativesResponse,
    AskResponse,
    AskSource,
    CompareResponse,
    CompareRow,
    CompareSide,
    CostAdjusted,
    FeedResponse,
    MatchLevel,
    PolicyApplicationView,
    PolicyCard,
    PolicyJudgement,
    PolicyTotals,
    PolicyWalletResponse,
    PostingCard,
    ProfileUsed,
    Ranking,
    RegionalTalentResponse,
    RegionalTalentView,
    Sort,
    posting_not_found,
)
from opportunity.seeds import demo_world as w
from opportunity.store.memory import MemoryRetriever, ScriptedLlm

PATHS = {
    "postings": "/agent/postings",
    "alternatives": "/agent/postings/{jobPostingId}/alternatives",
    "compare": "/agent/compare",
    "policies": "/agent/policies",
    "talent": "/agent/postings/{jobPostingId}/regional-talent",
    "policySearch": "/agent/policies/search",
}


def agent_event(api_path, params=None, session=None):
    return {
        "messageVersion": "1.0", "agent": {"name": "mentor", "id": "a", "alias": "x", "version": "1"},
        "inputText": "부산 데이터 공고 찾아줘", "sessionId": "sess-1", "actionGroup": "BusanOpportunity",
        "apiPath": api_path, "httpMethod": "GET",
        "parameters": [{"name": k, "type": "string", "value": v} for k, v in (params or {}).items()],
        "sessionAttributes": {"userId": "demo1"} if session is None else session, "promptSessionAttributes": {},
    }


def call(deps, api_path, params=None, session=None):
    response = agent_handler.handle(agent_event(api_path, params, session), deps)["response"]
    return response["httpStatusCode"], json.loads(response["responseBody"]["application/json"]["body"])


def card(deps, job_posting_id, **extra):
    latest = deps.catalog.get_latest(job_posting_id)
    fields = {k: getattr(latest, k) for k in ("job_posting_id", "title", "organization", "org_type", "work_region",
                                               "is_busan", "is_capital_area", "job", "closes_at", "rolling", "salary",
                                               "badges", "is_sample")}
    return PostingCard(**{**fields, "match_score": 0.81, "match_level": MatchLevel.GOOD, "rank_score": 0.87,
                          "facts": ["직종 일치: 데이터 분석가"], **extra})


@pytest.fixture
def seen():
    return {}


@pytest.fixture
def fake_feed(deps, monkeypatch, seen):
    ids = [w.BUSAN_DATA, w.BUSAN_DATA_PUBLIC, w.SEOUL_DATA, w.SEOUL_DATA_HYBRID, w.GYEONGGI_DATA_ENG,
           w.BUSAN_BACKEND, w.BUSAN_ACCOUNT, w.BUSAN_BADGE_NO_SOURCE]

    def fake(deps_, user_id, **kwargs):
        seen.update(user_id=user_id, **kwargs)
        return FeedResponse(items=[card(deps, pid) for pid in ids],
                            ranking=Ranking(sort=Sort.BUSAN_FIRST, basis="비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요"),
                            data_as_of=w.DATA_AS_OF)

    monkeypatch.setattr(agent_handler, "search_postings", fake)


# ---------------------------------------------------------------- 사용자 식별 (T-20)
def test_t20_user_id_comes_only_from_session_attributes(deps, fake_feed, seen):
    status, _ = call(deps, PATHS["postings"], {"userId": "demo2", "keyword": "데이터"})
    assert status == 200 and seen["user_id"] == "demo1" and "userId" not in seen


def test_t20_path_routes_ignore_user_id_param(deps, monkeypatch, seen):
    def fake(deps_, user_id, job_posting_id, **kwargs):
        seen.update(user_id=user_id, job_posting_id=job_posting_id)
        return AlternativesResponse(base_job_posting_id=job_posting_id)

    monkeypatch.setattr(agent_handler, "find_busan_alternatives", fake)
    status, _ = call(deps, PATHS["alternatives"], {"jobPostingId": w.SEOUL_DATA, "userId": "demo3"},
                     session={"userId": "demo2"})
    assert status == 200 and seen == {"user_id": "demo2", "job_posting_id": w.SEOUL_DATA}


def test_t20_missing_session_user_is_rejected(deps, fake_feed, seen):
    status, body = call(deps, PATHS["postings"], {"userId": "demo1"}, session={})
    assert status == 401 and body["error"]["code"] == "UNAUTHORIZED" and seen == {}


def test_t20_schema_has_no_user_id():
    schema = agent_handler.build_schema()
    params = [p["name"] for path in schema["paths"].values() for op in path.values() for p in op.get("parameters", [])]
    assert "userId" not in params and "userId" not in json.dumps(schema)


# ---------------------------------------------------------------- 응답 줄이기
def test_postings_are_capped_and_compact(deps, fake_feed, seen):
    status, body = call(deps, PATHS["postings"], {"limit": "20", "region": "BUSAN"})
    assert status == 200
    assert seen["limit"] == deps.config.agent.max_postings and seen["region"] == "BUSAN"
    assert len(body["items"]) == deps.config.agent.max_postings
    first = body["items"][0]
    assert first["jobPostingId"] == w.BUSAN_DATA and first["matchLevel"] == "잘 맞아요"
    assert first["salary"] == "연 3,400~3,800만 원" and first["workRegion"] == "부산 해운대구"
    assert first["badges"] == ["청끌기업 · 급여 (부산광역시 (데모), 2026-06-30)"]
    assert first["facts"] == ["직종 일치: 데이터 분석가"] and first["isSample"] is True
    assert body["notice"] == "적합도는 실제 합격 확률이 아닙니다"
    text = json.dumps(body, ensure_ascii=False)
    assert "matchScore" not in text and "rankScore" not in text and "jobDescription" not in text


def test_badge_without_source_is_dropped(deps, monkeypatch):
    monkeypatch.setattr(agent_handler, "search_postings", lambda d, u, **k: FeedResponse(
        items=[card(deps, w.BUSAN_BADGE_NO_SOURCE)], ranking=Ranking(sort=Sort.MATCH, basis="잘 맞는 순서로 보여드려요")))
    _, body = call(deps, PATHS["postings"])
    assert body["items"][0]["badges"] == []


def test_postings_bad_region_is_400(deps, fake_feed, seen):
    status, body = call(deps, PATHS["postings"], {"region": "SEOUL"})
    assert status == 400 and body["error"]["code"] == "INVALID_INPUT" and seen == {}


def test_alternatives_compact(deps, monkeypatch):
    item = AlternativeItem(job_posting_id=w.BUSAN_DATA, title="데이터 분석 신입", organization="(주)가상데이터",
                           work_region=deps.catalog.get_latest(w.BUSAN_DATA).work_region, closes_at="2026-12-05",
                           similarity=0.86, match_score=0.8, match_level=MatchLevel.GOOD, alt_score=0.8,
                           why_shown="보고 있는 공고와 하는 일이 비슷해요")
    monkeypatch.setattr(agent_handler, "find_busan_alternatives", lambda d, u, pid, **k: AlternativesResponse(
        base_job_posting_id=pid, alternatives=[item] * 3, suggest_compare=False))
    status, body = call(deps, PATHS["alternatives"], {"jobPostingId": w.SEOUL_DATA})
    assert status == 200 and body["baseJobPostingId"] == w.SEOUL_DATA and body["suggestCompare"] is False
    assert body["items"][0]["matchLevel"] == "잘 맞아요" and "similarity" not in body["items"][0]


def test_alternatives_not_found_uses_team_error_format(deps, monkeypatch):
    def fake(deps_, user_id, job_posting_id, **kwargs):
        raise posting_not_found(job_posting_id)

    monkeypatch.setattr(agent_handler, "find_busan_alternatives", fake)
    status, body = call(deps, PATHS["alternatives"], {"jobPostingId": "wk24-NOPE"})
    assert status == 404
    assert set(body["error"]) == {"code", "message", "requestId", "retryable", "details"}
    assert body["error"]["code"] == "POSTING_NOT_FOUND" and body["error"]["retryable"] is False


def test_compare_passes_ids(deps, monkeypatch, seen):
    def fake(deps_, user_id, base, alt, **kwargs):
        seen.update(base=base, alt=alt)
        return CompareResponse(base=CompareSide(job_posting_id=base, label="서울 · (주)가상테크"),
                               alt=CompareSide(job_posting_id=alt, label="부산 · (주)가상데이터"),
                               rows=[CompareRow(key="SALARY", label="급여", base="연 4,000~4,400만 원",
                                                alt="연 3,400~3,800만 원", source="공고", as_of="2026-11-21")],
                               cost_adjusted=CostAdjusted(available=False, reason="HOUSING_UNAVAILABLE"))

    monkeypatch.setattr(agent_handler, "compare_postings", fake)
    status, body = call(deps, PATHS["compare"], {"baseJobPostingId": w.SEOUL_DATA, "altJobPostingId": w.BUSAN_DATA})
    assert status == 200 and seen == {"base": w.SEOUL_DATA, "alt": w.BUSAN_DATA}
    assert body["base"] == "서울 · (주)가상테크" and body["rows"][0]["base"] == "연 4,000~4,400만 원"
    status, body = call(deps, PATHS["compare"], {"baseJobPostingId": w.SEOUL_DATA})
    assert status == 400 and body["error"]["code"] == "INVALID_INPUT"


def test_policies_flatten_buckets(deps, monkeypatch, seen):
    def policy_card(pid, bucket):
        return PolicyCard(policy_id=pid, title=pid, stage="PREPARE", bucket=bucket,
                          eligibility=PolicyJudgement(status="ELIGIBLE", reasons=["나이 충족"]),
                          application=PolicyApplicationView(selection="AUTOMATIC"), source="YOUTHCENTER",
                          as_of="2026-11-21", checklist=["신청서"])

    def fake(deps_, user_id, **kwargs):
        seen.update(kwargs)
        return PolicyWalletResponse(profile_used=ProfileUsed(), totals=PolicyTotals(guaranteed_if_eligible=10),
                                    buckets={"OPEN_NOW": [policy_card(w.P_BUSAN_INTERVIEW, "OPEN_NOW")],
                                             "NEXT_CYCLE": [policy_card(w.P_DIDIMDOL, "NEXT_CYCLE")]})

    monkeypatch.setattr(agent_handler, "match_policies", fake)
    status, body = call(deps, PATHS["policies"], {"stage": "PREPARE"})
    assert status == 200 and seen == {"stage": "PREPARE"}
    assert [(p["policyId"], p["bucket"]) for p in body["items"]] == [(w.P_BUSAN_INTERVIEW, "OPEN_NOW"),
                                                                     (w.P_DIDIMDOL, "NEXT_CYCLE")]
    assert body["items"][0]["reasons"] == ["나이 충족"] and "checklist" not in body["items"][0]
    assert body["totals"]["guaranteedIfEligible"] == 10


def test_regional_talent(deps, monkeypatch):
    monkeypatch.setattr(agent_handler, "get_regional_talent", lambda d, u, pid, **k: RegionalTalentResponse(
        job_posting_id=pid, organization="가상금융공사", regional_talent=RegionalTalentView(
            status="LIKELY", message="부산 소재 학교 졸업 예정이라 지역인재 전형 대상일 수 있어요 · 공고문 확인")))
    status, body = call(deps, PATHS["talent"], {"jobPostingId": w.BUSAN_DATA_PUBLIC})
    assert status == 200 and body["regionalTalent"]["status"] == "LIKELY"
    assert "대상일 수 있어요" in body["regionalTalent"]["message"]


def test_not_implemented_dependency_is_501(deps, monkeypatch):
    """비즈니스 함수가 아직 없으면 501 NOT_IMPLEMENTED, 그 밖의 예외는 500 INTERNAL_ERROR."""
    def not_yet(*args, **kwargs):
        raise NotImplementedError("core-match")

    monkeypatch.setattr(agent_handler, "search_postings", not_yet)
    status, body = call(deps, PATHS["postings"])
    assert status == 501 and body["error"]["code"] == "NOT_IMPLEMENTED"

    def broken(*args, **kwargs):
        raise KeyError("secret-detail")

    monkeypatch.setattr(agent_handler, "search_postings", broken)
    status, body = call(deps, PATHS["postings"])
    assert status == 500 and body["error"]["code"] == "INTERNAL_ERROR" and body["error"]["retryable"] is True
    assert "secret-detail" not in json.dumps(body)


def test_policy_search_passes_question_and_session_user(deps, monkeypatch, seen):
    def fake(deps_, user_id, question, **kwargs):
        seen.update(user_id=user_id, question=question)
        return AskResponse(question=question, answered=True, answer="부산청년플랫폼에서 온라인으로 신청해요.",
                           sources=[AskSource(kind="POLICY", id=w.P_BUSAN_RENT, title="[데모] 부산 청년 월세 지원",
                                              quote="부산청년플랫폼에서 온라인으로 신청합니다.", as_of="2026-11-21")])

    monkeypatch.setattr(agent_handler, "ask_policies", fake)
    status, body = call(deps, PATHS["policySearch"], {"question": "월세 신청 방법", "userId": "demo3"})
    assert status == 200 and seen == {"user_id": "demo1", "question": "월세 신청 방법"}
    assert body["answered"] is True and body["sources"][0]["quote"] == "부산청년플랫폼에서 온라인으로 신청합니다."


def test_policy_search_end_to_end(deps):
    deps.retriever = MemoryRetriever({w.P_BUSAN_RENT: (
        "# [데모] 부산 청년 월세 지원\n부산청년플랫폼에서 온라인으로 신청합니다.", {"policyId": w.P_BUSAN_RENT})})
    deps.llm = ScriptedLlm([json.dumps({"answer": "부산청년플랫폼에서 온라인으로 신청해요.", "citations": [
        {"policyId": w.P_BUSAN_RENT, "quote": "부산청년플랫폼에서 온라인으로 신청합니다."}], "notFound": False},
        ensure_ascii=False)])
    status, body = call(deps, PATHS["policySearch"], {"question": "월세 신청"})
    assert status == 200 and body["answered"] is True and body["relatedPolicies"][0]["policyId"] == w.P_BUSAN_RENT
    assert deps.events.events[-1] == ("ASK", {"kind": "POLICIES", "answered": True})


def test_policy_search_needs_question(deps):
    status, body = call(deps, PATHS["policySearch"])
    assert status == 400 and body["error"]["code"] == "INVALID_INPUT"
    status, body = call(deps, PATHS["policySearch"], {"question": "  "})
    assert status == 400 and body["error"]["code"] == "INVALID_INPUT"


def test_policy_search_description():
    op = agent_handler.build_schema()["paths"][PATHS["policySearch"]]["get"]
    assert "청년정책의 내용·자격·신청 방법을 묻는 질문에 쓴다. 원문 근거와 함께 답한다" in op["description"]
    assert [p["name"] for p in op["parameters"]] == ["question"]


# ---------------------------------------------------------------- 스키마
def test_schema_file_is_up_to_date():
    on_disk = json.loads(agent_handler.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert on_disk == agent_handler.build_schema(), "python -m opportunity.api.agent_handler로 다시 만든다"
    assert on_disk["openapi"].startswith("3.0")
    assert set(on_disk["paths"]) == set(PATHS.values())
    assert all(op.get("description") for path in on_disk["paths"].values() for op in path.values())
    assert "/agent/saved" not in on_disk["paths"]  # P1
