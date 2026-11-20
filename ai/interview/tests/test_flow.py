import json

import pytest

import interview
from conftest import sample_json, sample_text
from fakes import FakeLLM
from interview.errors import AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError
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
