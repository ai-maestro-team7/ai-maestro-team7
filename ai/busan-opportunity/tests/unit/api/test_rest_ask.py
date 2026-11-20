"""REST 질문 경로 3개: POST /policies/ask, /policies/{id}/ask, /postings/{id}/ask."""

import json

import pytest
from unit.api.test_rest import assert_error, call

from opportunity.api import rest_handler
from opportunity.core import copy_rules
from opportunity.models.api import AskResponse
from opportunity.seeds import demo_world as w
from opportunity.store.memory import MemoryRetriever, ScriptedLlm

RENT = "# [데모] 부산 청년 월세 지원\n\n## 신청 방법\n부산청년플랫폼에서 온라인으로 신청합니다."
ANSWER = json.dumps({"answer": "부산청년플랫폼에서 온라인으로 신청해요.",
                     "citations": [{"policyId": w.P_BUSAN_RENT, "quote": "부산청년플랫폼에서 온라인으로 신청합니다."}],
                     "notFound": False}, ensure_ascii=False)


@pytest.fixture
def rag(deps):
    deps.retriever = MemoryRetriever({w.P_BUSAN_RENT: (RENT, {"policyId": w.P_BUSAN_RENT, "regionKey": "26"})})
    deps.llm = ScriptedLlm([ANSWER])
    return deps


@pytest.fixture
def seen():
    return {}


def test_policies_ask_end_to_end(rag):
    status, body = call(rag, "POST", "/policies/ask", body={"question": "월세 신청 방법", "userId": "demo2"})
    assert status == 200 and body["answered"] is True
    assert body["sources"][0] == {"kind": "POLICY", "id": w.P_BUSAN_RENT, "title": "[데모] 부산 청년 월세 지원",
                                  "quote": "부산청년플랫폼에서 온라인으로 신청합니다.",
                                  "url": "https://example.invalid/youthcenter", "asOf": "2026-11-21"}
    assert body["relatedPolicies"][0]["policyId"] == w.P_BUSAN_RENT


def test_policies_ask_uses_token_user(rag, monkeypatch, seen):
    def fake(deps_, user_id, question, **kwargs):
        seen.update(user_id=user_id, question=question)
        return AskResponse(question=question, answered=False, notice=copy_rules.ASK_UNAVAILABLE)

    monkeypatch.setattr(rest_handler, "ask_policies", fake)
    status, body = call(rag, "POST", "/policies/ask", body={"question": "월세", "userId": "demo3"})
    assert status == 200 and seen == {"user_id": "demo1", "question": "월세"}
    assert body == {"question": "월세", "answered": False, "sources": [], "relatedPolicies": [], "manualChecks": [],
                    "notice": copy_rules.ASK_UNAVAILABLE}


def test_policy_ask_route(rag):
    status, body = call(rag, "POST", f"/policies/{w.P_BUSAN_RENT}/ask", body={"question": "월세 신청 방법"})
    assert status == 200 and body["answered"] is True and body["sources"][0]["id"] == w.P_BUSAN_RENT


def test_posting_ask_route(rag, monkeypatch, seen):
    def fake(deps_, user_id, job_posting_id, question, **kwargs):
        seen.update(user_id=user_id, job_posting_id=job_posting_id, question=question)
        return AskResponse(question=question, answered=False, notice=copy_rules.ASK_NOT_FOUND)

    monkeypatch.setattr(rest_handler, "ask_posting", fake)
    status, body = call(rag, "POST", f"/postings/{w.BUSAN_DATA}/ask", body={"question": "마감이 언제예요?"})
    assert status == 200 and body["notice"] == copy_rules.ASK_NOT_FOUND
    assert seen == {"user_id": "demo1", "job_posting_id": w.BUSAN_DATA, "question": "마감이 언제예요?"}


def test_posting_ask_end_to_end_not_found(rag):
    status, body = call(rag, "POST", "/postings/wk24-NOPE/ask", body={"question": "마감이 언제예요?"})
    assert_error(status, body, 404, "POSTING_NOT_FOUND")


@pytest.mark.parametrize("path", ["/policies/ask", f"/policies/{w.P_BUSAN_RENT}/ask", f"/postings/{w.BUSAN_DATA}/ask"])
def test_bad_bodies_are_400(rag, path):
    status, body = call(rag, "POST", path)
    assert_error(status, body, 400, "INVALID_INPUT")
    status, body = call(rag, "POST", path, body={"question": "   "})
    assert_error(status, body, 400, "INVALID_INPUT")
    status, body = call(rag, "POST", path, body={"question": "가" * (rag.config.ask.max_question_chars + 1)})
    assert_error(status, body, 400, "INVALID_INPUT")
    status, body = call(rag, "POST", path, body={"q": "월세"})
    assert_error(status, body, 400, "INVALID_INPUT")


def test_unknown_policy_and_hash_id(rag):
    status, body = call(rag, "POST", "/policies/ythc-NOPE/ask", body={"question": "월세"})
    assert_error(status, body, 404, "POLICY_NOT_FOUND")
    status, body = call(rag, "POST", "/policies/a%23b/ask", body={"question": "월세"})
    assert_error(status, body, 400, "INVALID_INPUT")


def test_question_is_not_logged(rag, caplog):
    question = "남구 사는데 월세 신청 방법"
    with caplog.at_level("INFO", logger="opportunity.api"):
        call(rag, "POST", "/policies/ask", body={"question": question})
    assert caplog.records and all(question not in r.getMessage() for r in caplog.records)
