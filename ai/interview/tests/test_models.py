import json
import logging

import pytest
from pydantic import ValidationError

from conftest import REPO_ROOT
from interview.errors import INVALID_INPUT, InterviewError
from interview.models import (AnswerRecord, AnswerResult, FollowUpOutput, QuestionRequest, QuestionsOutput, Session,
                              StartInterviewInput, dump, parse_input)

RESUME_50 = "가" * 50


def contract_profile(name="data-analysis-demo"):
    path = REPO_ROOT / "contracts" / "fixtures" / "valid" / "CareerProfileSummary.json"
    examples = json.loads(path.read_text(encoding="utf-8"))["examples"]
    return next(e["data"] for e in examples if e["name"] == name)


def start_input(**overrides):
    data = {"session_id": "6f1c2a9e-0000-4000-8000-000000000000", "job": "데이터 분석", "resume_text": RESUME_50,
            "interview_type": "MIXED", "camera_consent": True, "profile": None}
    data.update(overrides)
    return data


def session_dict(**overrides):
    questions = [{"questionId": f"q{i}", "questionType": t, "question": f"질문 {i}번입니다."}
                 for i, t in enumerate(["experience", "knowledge", "situation"], start=1)]
    data = {
        "sessionId": "6f1c2a9e-0000-4000-8000-000000000000", "job": "데이터 분석", "interviewType": "MIXED",
        "cameraConsent": True, "resumeText": RESUME_50, "profile": contract_profile(), "scoringVersion": "v1.0",
        "modelId": "test-model", "promptVersion": "A-v1/B-v1", "questions": questions, "currentIndex": 0,
        "followUpUsed": False,
        "currentQuestion": {"questionId": "q1", "answerId": "a-q1-1", "text": "질문 1번입니다.", "isFollowUp": False},
        "answers": [], "baseline": None,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------- 입력


@pytest.mark.parametrize("job, ok", [("", False), ("   ", False), ("a", True), ("가" * 50, True), ("가" * 51, False)])
def test_job_length(job, ok):
    if ok:
        assert StartInterviewInput.model_validate(start_input(job=job)).job == job
    else:
        with pytest.raises(ValidationError):
            StartInterviewInput.model_validate(start_input(job=job))


def test_job_is_stripped():
    assert StartInterviewInput.model_validate(start_input(job="  데이터 분석  ")).job == "데이터 분석"


@pytest.mark.parametrize("length, ok", [(49, False), (50, True), (5000, True), (5001, False)])
def test_resume_length(length, ok):
    data = start_input(resume_text="가" * length)
    if ok:
        StartInterviewInput.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            StartInterviewInput.model_validate(data)


@pytest.mark.parametrize("value", ["true", 1, None])
def test_camera_consent_strict_bool(value):
    with pytest.raises(ValidationError):
        StartInterviewInput.model_validate(start_input(camera_consent=value))


@pytest.mark.parametrize("field, value", [("interview_type", "TECH"), ("session_id", " "), ("job", 123)])
def test_other_invalid_inputs(field, value):
    with pytest.raises(ValidationError):
        StartInterviewInput.model_validate(start_input(**{field: value}))


def test_question_request_has_no_session_fields():
    req = QuestionRequest.model_validate({"job": "데이터 분석", "resume_text": RESUME_50, "interview_type": "JOB"})
    assert req.profile is None
    with pytest.raises(ValidationError):
        QuestionRequest.model_validate({"job": "데이터 분석", "resume_text": RESUME_50, "interview_type": "JOB",
                                        "session_id": "x"})


# ---------------------------------------------------------------- profile (계약 CareerProfileSummary)


def test_profile_contract_example_accepted():
    parsed = StartInterviewInput.model_validate(start_input(profile=contract_profile()))
    assert parsed.profile.skills == ["Python", "SQL", "데이터 시각화"]


def test_profile_without_optional_ids_accepted():
    StartInterviewInput.model_validate(start_input(profile=contract_profile("empty-lists")))


def test_profile_old_spec_format_rejected():
    # C §5.2 이전 예시 형식 (targetJob, strengths, gapsToVerify)
    old = {"targetJob": "데이터 분석", "projects": ["p"], "skills": ["Python"], "strengths": ["문제 해결"],
           "gapsToVerify": ["대용량 트래픽 경험"]}
    with pytest.raises(ValidationError):
        StartInterviewInput.model_validate(start_input(profile=old))


def test_profile_too_many_items_rejected():
    profile = dict(contract_profile(), projects=[f"프로젝트 {i}" for i in range(11)])
    with pytest.raises(ValidationError):
        StartInterviewInput.model_validate(start_input(profile=profile))


def test_profile_snake_case_keys_rejected():
    profile = {"projects": [], "skills": [], "needs_confirmation": []}
    with pytest.raises(ValidationError):
        StartInterviewInput.model_validate(start_input(profile=profile))


# ---------------------------------------------------------------- Session


def test_session_round_trip_camel_keys():
    session = Session.model_validate(session_dict())
    out = dump(session)
    assert set(out) == {"sessionId", "job", "interviewType", "cameraConsent", "resumeText", "profile",
                        "scoringVersion", "modelId", "promptVersion", "questions", "currentIndex", "followUpUsed",
                        "currentQuestion", "answers", "baseline"}
    assert out["profile"]["needsConfirmation"] == ["실무 데이터 파이프라인 경험"]
    assert out["currentQuestion"]["isFollowUp"] is False
    # JSON으로 저장했다가 다시 읽어도 같다 (백엔드 저장 흉내)
    assert dump(Session.model_validate(json.loads(json.dumps(out)))) == out


def test_session_unknown_key_rejected():
    with pytest.raises(ValidationError):
        Session.model_validate(session_dict(extraField=1))


def test_session_question_count_fixed():
    data = session_dict()
    data["questions"] = data["questions"][:2]
    with pytest.raises(ValidationError):
        Session.model_validate(data)


def test_session_accepts_backend_baseline():
    # 백엔드가 compute_baseline 결과를 넣고, DynamoDB를 거치며 0.0이 0이 되어도 받는다
    Session.model_validate(session_dict(baseline={"gaze": {"yaw": 0, "pitch": 0}, "head": {"yaw": 0, "pitch": 0}}))


def test_answer_record_consistency():
    base = {"answerId": "a-q1-1", "questionId": "q1", "isFollowUp": False, "question": "질문",
            "timeLimitReached": False}
    AnswerRecord.model_validate(dict(base, answerText="답변", evaluable=True, reason=None))
    AnswerRecord.model_validate(dict(base, answerText="", evaluable=False, reason="NO_ANSWER"))
    AnswerRecord.model_validate(dict(base, answerText=None, evaluable=False, reason="TRANSCRIBE_FAILED"))
    with pytest.raises(ValidationError):
        AnswerRecord.model_validate(dict(base, answerText="답변", evaluable=True, reason="NO_ANSWER"))
    with pytest.raises(ValidationError):
        AnswerRecord.model_validate(dict(base, answerText="", evaluable=False, reason=None))


# ---------------------------------------------------------------- Answer_Result


def test_answer_result_backend_shapes():
    # 정상 (대역 get_transcription_result 형태), 시간 초과로 백엔드가 넣는 FAILED
    ok = AnswerResult.model_validate({"answerId": "a-q1-1", "timeLimitReached": False, "transcription": {
        "status": "COMPLETED", "text": "저는", "words": [{"word": "저는", "start": 0.4, "end": 0.7}]}})
    assert ok.transcription.words[0].end == 0.7
    failed = AnswerResult.model_validate({"answerId": "a-q1-1", "timeLimitReached": True,
                                          "transcription": {"status": "FAILED"}})
    assert failed.transcription.text is None


def test_answer_result_rejects_unknown_status_and_keys():
    with pytest.raises(ValidationError):
        AnswerResult.model_validate({"answerId": "a-q1-1", "transcription": {"status": "DONE"}})
    with pytest.raises(ValidationError):
        AnswerResult.model_validate({"answerId": "a-q1-1", "transcription": {"status": "FAILED"}, "extra": 1})


# ---------------------------------------------------------------- LLM 출력


def questions_payload(n=3, texts=None):
    texts = texts or [f"질문 문장 {i}번입니다." for i in range(n)]
    types = ["experience", "knowledge", "situation", "experience"]
    return {"questions": [{"questionType": types[i], "question": t} for i, t in enumerate(texts)]}


def test_questions_output_ok_and_ignores_extra_keys():
    payload = questions_payload()
    payload["questions"][0]["questionId"] = "x9"
    out = QuestionsOutput.model_validate(payload)
    assert len(out.questions) == 3


@pytest.mark.parametrize("n", [2, 4])
def test_questions_output_count(n):
    with pytest.raises(ValidationError):
        QuestionsOutput.model_validate(questions_payload(n=n))


def test_questions_output_duplicate_after_whitespace_normalize():
    with pytest.raises(ValidationError):
        QuestionsOutput.model_validate(questions_payload(texts=["같은 질문입니다.", "같은  질문입니다. ", "다른 질문입니다."]))


def test_questions_output_bad_type_or_short_text():
    bad_type = questions_payload()
    bad_type["questions"][0]["questionType"] = "personality"
    with pytest.raises(ValidationError):
        QuestionsOutput.model_validate(bad_type)
    with pytest.raises(ValidationError):
        QuestionsOutput.model_validate(questions_payload(texts=["짧음", "질문 문장 1번입니다.", "질문 문장 2번입니다."]))


def test_follow_up_output_rules():
    many = FollowUpOutput.model_validate({"needFollowUp": True, "reason": "ABSTRACT",
                                          "followUpQuestions": ["첫 번째 꼬리질문?", "  ", "두 번째 꼬리질문?"]})
    assert many.follow_up_questions == ["첫 번째 꼬리질문?", "두 번째 꼬리질문?"]
    none_needed = FollowUpOutput.model_validate({"needFollowUp": False, "reason": "SUFFICIENT",
                                                 "followUpQuestions": ["필요 없는 질문입니다?"]})
    assert none_needed.follow_up_questions == []
    with pytest.raises(ValidationError):
        FollowUpOutput.model_validate({"needFollowUp": True, "reason": "ABSTRACT", "followUpQuestions": []})
    with pytest.raises(ValidationError):
        FollowUpOutput.model_validate({"needFollowUp": True, "reason": "MAYBE", "followUpQuestions": ["질문입니다?"]})


# ---------------------------------------------------------------- parse_input


def test_parse_input_raises_invalid_input_without_input_values(caplog):
    secret = "비밀 자소서 문장" * 10
    with caplog.at_level(logging.WARNING, logger="interview"):
        with pytest.raises(InterviewError) as exc:
            parse_input(StartInterviewInput, start_input(resume_text=secret, job=""), stage="test")
    err = exc.value
    assert err.code == INVALID_INPUT and err.retryable is False
    assert err.__cause__ is None and err.__suppress_context__ is True
    assert "비밀" not in str(err)
    assert "job" in caplog.text
    assert "비밀" not in caplog.text


def test_parse_input_non_dict():
    with pytest.raises(InterviewError):
        parse_input(Session, None, stage="test")
