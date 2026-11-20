import copy
import json

import pytest

import interview
from conftest import sample_json, sample_text
from fakes import FakeLLM
from interview.errors import AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError
from interview.models import Session

RESUME = sample_text("resume_data_analysis.txt")
PROFILE = sample_json("profile_data_analysis.json")
QUESTIONS_OK = sample_text("llm/questions_ok.json")
SESSION_ID = "6f1c2a9e-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def model_id(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model")


def start(profile=None, fake=None, **overrides):
    args = dict(session_id=SESSION_ID, job="데이터 분석", resume_text=RESUME, interview_type="MIXED",
                camera_consent=True, profile=profile)
    args.update(overrides)
    fake = fake or FakeLLM([QUESTIONS_OK])
    # 백엔드와 같은 위치 인자 6개로 부른다 (backend/interview_api.py 244행)
    return interview.start_interview(args["session_id"], args["job"], args["resume_text"], args["interview_type"],
                                     args["camera_consent"], args["profile"], llm=fake)


# ---------------------------------------------------------------- start_interview


def test_start_initial_session():
    result = start()
    assert set(result) == {"session", "nextQuestion"}
    session = result["session"]
    Session.model_validate(session)
    assert session["sessionId"] == SESSION_ID
    assert session["currentIndex"] == 0 and session["followUpUsed"] is False
    assert session["answers"] == [] and session["baseline"] is None
    assert session["scoringVersion"] == "v1.0"
    assert session["modelId"] == "test-model"
    assert session["promptVersion"] == "A-v1/B-v1"
    assert [q["questionId"] for q in session["questions"]] == ["q1", "q2", "q3"]
    assert result["nextQuestion"] == {"questionId": "q1", "answerId": "a-q1-1",
                                      "text": session["questions"][0]["question"], "isFollowUp": False}
    assert session["currentQuestion"] == result["nextQuestion"]


def test_start_matches_sample():
    expected = sample_json("session_after_start.json")
    result = start(profile=PROFILE, session_id=expected["session"]["sessionId"])
    assert result["nextQuestion"] == expected["nextQuestion"]
    assert result["session"]["questions"] == expected["session"]["questions"]
    assert result["session"]["profile"] == expected["session"]["profile"]


def test_start_without_profile():
    assert start(profile=None)["session"]["profile"] is None


def test_start_with_profile_stored_camel():
    profile = start(profile=PROFILE)["session"]["profile"]
    assert profile["needsConfirmation"] == ["실무 데이터 파이프라인 경험"]
    assert profile["profileVersion"] == 2


def test_start_profile_optional_positional():
    # profile을 넘기지 않아도 된다
    out = interview.start_interview(SESSION_ID, "데이터 분석", RESUME, "JOB", False, llm=FakeLLM([QUESTIONS_OK]))
    assert out["session"]["cameraConsent"] is False


def test_start_job_is_stripped():
    assert start(job="  데이터 분석  ")["session"]["job"] == "데이터 분석"


def test_start_result_is_json_round_trip_safe():
    result = start(profile=PROFILE)
    again = json.loads(json.dumps(result, ensure_ascii=False))
    assert again == result
    Session.model_validate(again["session"])


@pytest.mark.parametrize("overrides", [
    {"session_id": ""},
    {"job": ""},
    {"resume_text": "짧음"},
    {"interview_type": "TECH"},
    {"camera_consent": "true"},
    {"profile": {"targetJob": "데이터 분석", "strengths": ["문제 해결"], "gapsToVerify": ["x"]}},
])
def test_start_invalid_input_no_llm_call(overrides):
    fake = FakeLLM([QUESTIONS_OK])
    with pytest.raises(InterviewError) as exc:
        start(fake=fake, **overrides)
    assert exc.value.code == INVALID_INPUT and exc.value.retryable is False
    assert fake.calls == []


def test_start_without_model_id_fails_before_llm(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    fake = FakeLLM([QUESTIONS_OK])
    with pytest.raises(InterviewError) as exc:
        start(fake=fake)
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False
    assert fake.calls == []


# ---------------------------------------------------------------- process_answer

NEEDED = sample_text("llm/follow_up_needed.json")
MULTIPLE = sample_text("llm/follow_up_multiple.json")
SUFFICIENT = sample_text("llm/follow_up_sufficient.json")
NORMAL_TEXT = sample_json("answers/normal_q1.json")["transcription"]["text"]
ABSTRACT_TEXT = sample_json("answers/abstract_q1.json")["transcription"]["text"]


def initial_session():
    return start()["session"]


def answer(answer_id, text=NORMAL_TEXT, status="COMPLETED", time_limit=False):
    transcription = {"status": status} if status != "COMPLETED" else {"status": status, "text": text, "words": []}
    return {"answerId": answer_id, "timeLimitReached": time_limit, "transcription": transcription}


def step(session, answer_result, responses=()):
    """백엔드처럼 결과를 JSON으로 저장했다가 다시 넘긴다. 쓰지 않은 LLM 응답이 남으면 실패."""
    fake = FakeLLM(list(responses))
    out = interview.process_answer(json.loads(json.dumps(session)), answer_result, llm=fake)
    assert fake.responses == [], "준비한 LLM 응답을 다 쓰지 않았다"
    return json.loads(json.dumps(out, ensure_ascii=False)), fake


def test_full_round_with_one_follow_up():
    session = initial_session()

    out, fake = step(session, answer("a-q1-1", ABSTRACT_TEXT), [NEEDED])
    assert out["action"] == "FOLLOW_UP"
    assert out["nextQuestion"] == {"questionId": "q1-f", "answerId": "a-q1-2", "isFollowUp": True,
                                   "text": "자료를 정리할 때 본인이 직접 한 작업을 하나만 구체적으로 설명해 주세요."}
    assert out["lastAnswer"] == {"answerId": "a-q1-1", "evaluable": True, "reason": None}
    assert out["session"]["followUpUsed"] is True and out["session"]["currentIndex"] == 0
    assert out["session"]["currentQuestion"] == out["nextQuestion"]
    assert len(fake.calls) == 1

    out, fake = step(out["session"], answer("a-q1-2"))  # 꼬리질문 답변 뒤에는 판단하지 않는다
    assert out["action"] == "NEXT_QUESTION" and fake.calls == []
    assert out["nextQuestion"]["questionId"] == "q2" and out["nextQuestion"]["answerId"] == "a-q2-1"
    assert out["session"]["followUpUsed"] is False and out["session"]["currentIndex"] == 1

    out, _ = step(out["session"], answer("a-q2-1"), [SUFFICIENT])
    assert out["action"] == "NEXT_QUESTION" and out["nextQuestion"]["answerId"] == "a-q3-1"

    out, _ = step(out["session"], answer("a-q3-1"), [SUFFICIENT])
    assert out["action"] == "REPORT" and out["nextQuestion"] is None
    final = out["session"]
    assert final["currentQuestion"] is None and final["currentIndex"] == 3
    assert [a["answerId"] for a in final["answers"]] == ["a-q1-1", "a-q1-2", "a-q2-1", "a-q3-1"]
    assert [a["isFollowUp"] for a in final["answers"]] == [False, True, False, False]
    Session.model_validate(final)


def test_answer_record_fields():
    out, _ = step(initial_session(), answer("a-q1-1", time_limit=True), [SUFFICIENT])
    record = out["session"]["answers"][0]
    assert record == {"answerId": "a-q1-1", "questionId": "q1", "isFollowUp": False,
                      "question": initial_session()["questions"][0]["question"], "answerText": NORMAL_TEXT,
                      "evaluable": True, "reason": None, "timeLimitReached": True}
    assert "words" not in json.dumps(out["session"])  # 단어별 시간은 1차에서 Session에 넣지 않는다


def test_no_answer_moves_to_next_base_question():
    out, fake = step(initial_session(), answer("a-q1-1", ""))
    assert out["action"] == "NEXT_QUESTION" and out["nextQuestion"]["questionId"] == "q2"
    assert out["lastAnswer"] == {"answerId": "a-q1-1", "evaluable": False, "reason": "NO_ANSWER"}
    assert out["session"]["answers"][0]["answerText"] == ""
    assert fake.calls == []


@pytest.mark.parametrize("blank", [" ", "   ", "\n", "\t", " \n\t \r\n ", "\u3000", "\u00a0 \u3000"])
def test_whitespace_only_answer_is_no_answer(blank):
    # 공백·탭·줄바꿈·전각 공백·줄바꿈 없는 공백만 있는 답변도 말이 없는 것으로 본다
    out, fake = step(initial_session(), answer("a-q1-1", blank))
    assert out["lastAnswer"]["reason"] == "NO_ANSWER" and out["lastAnswer"]["evaluable"] is False
    assert out["session"]["answers"][0]["answerText"] == ""
    assert out["action"] == "NEXT_QUESTION" and fake.calls == []


def test_missing_text_is_no_answer():
    result = {"answerId": "a-q1-1", "timeLimitReached": False, "transcription": {"status": "COMPLETED"}}
    out, _ = step(initial_session(), result)
    assert out["lastAnswer"]["reason"] == "NO_ANSWER"


def test_transcribe_failed_continues():
    failed = sample_json("answers/transcribe_failed.json")
    out, fake = step(initial_session(), failed)
    assert out["action"] == "NEXT_QUESTION"
    assert out["lastAnswer"] == {"answerId": "a-q1-1", "evaluable": False, "reason": "TRANSCRIBE_FAILED"}
    record = out["session"]["answers"][0]
    assert record["answerText"] is None and record["timeLimitReached"] is True
    assert fake.calls == []


def test_multiple_follow_ups_limited_to_one():
    out, _ = step(initial_session(), answer("a-q1-1", ABSTRACT_TEXT), [MULTIPLE])
    assert out["action"] == "FOLLOW_UP"
    assert out["nextQuestion"]["text"] == "자료를 정리할 때 본인이 직접 한 작업을 하나만 구체적으로 설명해 주세요."
    # 꼬리질문에 다시 추상적으로 답해도 두 번째 꼬리질문은 없다
    out, fake = step(out["session"], answer("a-q1-2", ABSTRACT_TEXT))
    assert out["action"] == "NEXT_QUESTION" and fake.calls == []


def test_unevaluable_follow_up_answer_moves_on():
    out, _ = step(initial_session(), answer("a-q1-1", ABSTRACT_TEXT), [NEEDED])
    out, fake = step(out["session"], answer("a-q1-2", ""))
    assert out["action"] == "NEXT_QUESTION" and out["lastAnswer"]["reason"] == "NO_ANSWER"
    assert fake.calls == []


def test_follow_up_on_last_question_then_report():
    session = initial_session()
    out, _ = step(session, answer("a-q1-1"), [SUFFICIENT])
    out, _ = step(out["session"], answer("a-q2-1"), [SUFFICIENT])
    out, _ = step(out["session"], answer("a-q3-1", ABSTRACT_TEXT), [NEEDED])
    assert out["action"] == "FOLLOW_UP" and out["nextQuestion"]["answerId"] == "a-q3-2"
    out, _ = step(out["session"], answer("a-q3-2"))
    assert out["action"] == "REPORT" and out["session"]["currentQuestion"] is None


def test_all_unevaluable_reaches_report_without_llm():
    session = initial_session()
    out, _ = step(session, answer("a-q1-1", ""))
    out, _ = step(out["session"], answer("a-q2-1", status="FAILED"))
    out, fake = step(out["session"], answer("a-q3-1", "  "))
    assert out["action"] == "REPORT" and fake.calls == []
    assert all(a["evaluable"] is False for a in out["session"]["answers"])


def _finished_session():
    session = initial_session()
    for aid in ("a-q1-1", "a-q2-1", "a-q3-1"):
        session = step(session, answer(aid, ""))[0]["session"]
    return session


@pytest.mark.parametrize("make_session, answer_result", [
    (_finished_session, answer("a-q3-1")),                     # 이미 끝난 면접
    (initial_session, answer("a-q2-1")),                       # 지금 받을 답변이 아님
    (initial_session, answer("a-q1-2")),                       # 꼬리질문이 없는데 꼬리질문 답변
    (initial_session, answer("a-q1-1", status="IN_PROGRESS")),  # 변환이 끝나지 않음
])
def test_invalid_state_rejected(make_session, answer_result):
    fake = FakeLLM([SUFFICIENT])
    with pytest.raises(InterviewError) as exc:
        interview.process_answer(make_session(), answer_result, llm=fake)
    assert exc.value.code == INVALID_INPUT
    assert fake.calls == []


def test_replayed_answer_rejected():
    session = initial_session()
    out, _ = step(session, answer("a-q1-1"), [SUFFICIENT])
    with pytest.raises(InterviewError) as exc:
        interview.process_answer(out["session"], answer("a-q1-1"), llm=FakeLLM([]))
    assert exc.value.code == INVALID_INPUT


def test_inconsistent_session_rejected():
    session = initial_session()
    session["currentQuestion"] = {"questionId": "q2", "answerId": "a-q2-1", "text": "x", "isFollowUp": False}
    with pytest.raises(InterviewError) as exc:
        interview.process_answer(session, answer("a-q2-1"), llm=FakeLLM([SUFFICIENT]))
    assert exc.value.code == INVALID_INPUT


@pytest.mark.parametrize("bad", [None, {}, {"sessionId": "x"}])
def test_bad_session_shape_rejected(bad):
    with pytest.raises(InterviewError) as exc:
        interview.process_answer(bad, answer("a-q1-1"), llm=FakeLLM([]))
    assert exc.value.code == INVALID_INPUT


def test_follow_up_invalid_output_raises_and_session_unchanged():
    session = initial_session()
    before = copy.deepcopy(session)
    not_json = sample_text("llm/not_json.txt")
    fake = FakeLLM([not_json, not_json])
    with pytest.raises(InterviewError) as exc:
        interview.process_answer(session, answer("a-q1-1"), llm=fake)
    assert exc.value.code == AI_OUTPUT_INVALID and exc.value.retryable is True
    assert len(fake.calls) == 2
    assert session == before


def test_input_session_not_mutated():
    session = initial_session()
    result = answer("a-q1-1", ABSTRACT_TEXT)
    before_session, before_result = copy.deepcopy(session), copy.deepcopy(result)
    interview.process_answer(session, result, llm=FakeLLM([NEEDED]))
    assert session == before_session and result == before_result


def test_follow_up_prompt_uses_question_and_answer():
    session = initial_session()
    fake = FakeLLM([SUFFICIENT])
    interview.process_answer(session, answer("a-q1-1", ABSTRACT_TEXT), llm=fake)
    user = fake.calls[0]["user"]
    assert "<question>\n" + session["questions"][0]["question"] + "\n</question>" in user
    assert "<answer>\n" + ABSTRACT_TEXT + "\n</answer>" in user
    assert "<job>\n데이터 분석\n</job>" in user


def test_backend_positional_call_and_placeholder_transcript():
    # 백엔드는 process_answer(item["session"], answer_result)로 부르고, 임시 get_transcription_result 결과를 넘긴다
    session = initial_session()
    result = {"answerId": "a-q1-1", "timeLimitReached": False,
              "transcription": interview.get_transcription_result("job-1")}
    out = interview.process_answer(session, result, llm=FakeLLM([SUFFICIENT]))
    assert out["action"] == "NEXT_QUESTION"
    assert set(out) == {"session", "action", "nextQuestion", "lastAnswer"}
