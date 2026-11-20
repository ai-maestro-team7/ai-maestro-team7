"""백엔드(backend/interview_api.py) 호출 순서를 backend를 import하지 않고 그대로 따라 한다 (design §12).

단계마다 결과를 DynamoDB 저장·조회처럼 바꿨다가 다음 호출에 넘긴다.
backend/common.py의 to_dynamo(실수 → Decimal)와 to_plain(정수 Decimal → int, 나머지 → float)과 같은 변환이다.
"""

import json
from decimal import Decimal

import pytest

import interview
from conftest import sample_json, sample_text
from fakes import FakeLLM, FakeS3
from interview import placeholders
from interview.models import Session

RESUME = sample_text("resume_data_analysis.txt")
PROFILE = sample_json("profile_data_analysis.json")
UPLOAD_BUCKET = "test-uploads"


def to_dynamo(value):
    return json.loads(json.dumps(value, ensure_ascii=False), parse_float=Decimal)


def to_plain(value):
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def store(value):
    """DynamoDB에 넣었다가 꺼낸 값."""
    return to_plain(to_dynamo(value))


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model")


@pytest.fixture
def fake_s3(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(placeholders, "_s3_client", lambda: s3)
    return s3


def run_interview(fake_s3, follow_up_responses, calibration_images, profile=PROFILE):
    iv_id = "6f1c2a9e-0000-4000-8000-0000000000aa"

    # task_start (244~245행): start_interview → synthesize_question
    result = interview.start_interview(iv_id, "데이터 분석", RESUME, "MIXED", True, profile,
                                       llm=FakeLLM([sample_text("llm/questions_ok.json")]))
    assert interview.synthesize_question(result["nextQuestion"]["text"]) is None  # 임시 구현: 음성 없음
    item = store({"session": result["session"], "nextQuestion": result["nextQuestion"]})

    # h_frame (421~425행): 보정 캡처
    frames = [store({"type": "CALIBRATION", **interview.analyze_face(img)}) for img in calibration_images]

    llm = FakeLLM(follow_up_responses)
    actions = []
    while True:
        nq = item["nextQuestion"]
        answer_id = nq["answerId"]
        # h_answer (386~387행): 결과 위치는 백엔드가 정한다
        transcript_key = f"uploads/interview/{iv_id}/transcripts/{answer_id}.json"
        job_name = interview.start_transcription(f"s3://{UPLOAD_BUCKET}/uploads/interview/{iv_id}/answers/{answer_id}.webm",
                                                 f"team07-{iv_id}-{answer_id}", "webm", UPLOAD_BUCKET, transcript_key)
        # h_frame: 답변 중 캡처
        frames.append(store({"type": "ANSWER", "questionId": nq["questionId"], "answerId": answer_id,
                             "accepted": True, **interview.analyze_face(b"\xff\xd8fake")}))
        # task_answer (248~277행)
        tr = interview.get_transcription_result(job_name)
        answer_result = {"answerId": answer_id, "timeLimitReached": False, "transcription": tr}
        out = interview.process_answer(item["session"], answer_result, llm=llm)
        actions.append(out["action"])
        item = store({"session": out["session"], "nextQuestion": out["nextQuestion"], "lastAnswer": out["lastAnswer"]})
        if out["action"] == "REPORT":
            break
        assert len(actions) < 10

    # make_report (280~296행): 기준값 → 리포트
    session = item["session"]
    calib = [{k: f.get(k) for k in ("valid", "reason", "gaze", "head", "eyesOpen")}
             for f in frames if f["type"] == "CALIBRATION" and f.get("valid")]
    session["baseline"] = interview.compute_baseline(calib)
    answer_frames = [{k: f.get(k) for k in ("type", "questionId", "answerId", "capturedAt", "accepted", "valid",
                                            "gaze", "head", "eyesOpen")} for f in frames if f["type"] == "ANSWER"]
    report = interview.generate_report(session, answer_frames)
    session = store(session)
    assert llm.responses == []
    return actions, session, report, answer_frames


def test_backend_flow_with_follow_up_and_baseline(fake_s3):
    responses = [sample_text("llm/follow_up_needed.json"), sample_text("llm/follow_up_sufficient.json"),
                 sample_text("llm/follow_up_sufficient.json")]
    actions, session, report, answer_frames = run_interview(fake_s3, responses, [b"\xff\xd8a", b"\xff\xd8b", b"\xff\xd8c"])

    assert actions == ["FOLLOW_UP", "NEXT_QUESTION", "NEXT_QUESTION", "REPORT"]
    assert len(fake_s3.puts) == 4
    assert [p["Key"].rsplit("/", 1)[1] for p in fake_s3.puts] == ["a-q1-1.json", "a-q1-2.json", "a-q2-1.json",
                                                                   "a-q3-1.json"]
    assert session["baseline"] == {"gaze": {"yaw": 0, "pitch": 0}, "head": {"yaw": 0, "pitch": 0}}  # 0.0 → 0
    assert session["profile"]["profileVersion"] == 2
    Session.model_validate(session)  # 저장·조회와 기준값 추가 뒤에도 Session 형식 그대로
    assert report["evaluatedBaseQuestions"] == 4 and report["frameCount"] == len(answer_frames) == 4
    assert all(f["eyesOpen"] == {"value": True, "confidence": 98.5} for f in answer_frames)


def test_backend_flow_baseline_none_with_few_calibration_frames(fake_s3):
    sufficient = sample_text("llm/follow_up_sufficient.json")
    actions, session, report, _ = run_interview(fake_s3, [sufficient] * 3, [b"\xff\xd8a", b""], profile=None)
    assert actions == ["NEXT_QUESTION", "NEXT_QUESTION", "REPORT"]
    assert session["baseline"] is None  # 유효 3장 미만 → 태도 미측정, 대체값 없음
    assert session["profile"] is None
    Session.model_validate(session)
    assert report["totalScore"] is None
