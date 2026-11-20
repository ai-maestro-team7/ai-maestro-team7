import json
import logging
from decimal import Decimal

import pytest

import interview
from conftest import sample_json, sample_text
from fakes import FakeToolLLM
from interview.content import RUBRIC_KEYS
from interview.errors import AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError
from interview.models import dump
from scoring_helpers import BASELINE, answer, delivery, frame, frames, session

NORMAL_TEXT = sample_json("answers/normal_q1.json")["transcription"]["text"]
C2_OK = json.loads(sample_text("llm/c2_feedback_ok.json"))
REPORT_KEYS = {"job", "interviewType", "evaluatedBaseQuestions", "totalScore", "grade", "weightBasis", "areas",
               "notMeasuredMessages", "questions", "scoringVersion", "modelId", "promptVersion", "notice"}
QUESTION_KEYS = {"questionId", "question", "followUp", "answerText", "evaluable", "reason", "contentScore",
                 "strengths", "improvements", "direction", "metrics", "comment"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model")


def c1(qtype, score=4):
    return json.dumps({"items": [{"key": k, "score": score, "evidenceType": "missing", "evidence": "빠진 요소"}
                                 for k in RUBRIC_KEYS[qtype]]}, ensure_ascii=False)


def c2(qids=("q1", "q2", "q3")):
    return json.dumps({"questions": [q for q in C2_OK["questions"] if q["questionId"] in qids]}, ensure_ascii=False)


def fake(qtypes=("experience", "knowledge", "situation"), qids=("q1", "q2", "q3"), c1_responses=None):
    return FakeToolLLM([c2(qids)], responses=c1_responses if c1_responses is not None else [c1(t) for t in qtypes])


def full(camera=True, **kw):
    return dump(session([answer("q1", text=NORMAL_TEXT, **kw), answer("q1", follow_up=True, text="직접 했습니다."),
                         answer("q2", **kw), answer("q3", **kw)], camera=camera))


def to_plain(value):
    """backend/common.py to_dynamo → to_plain 왕복."""
    def plain(v):
        if isinstance(v, list):
            return [plain(x) for x in v]
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else float(v)
        return v
    return plain(json.loads(json.dumps(value, ensure_ascii=False), parse_float=Decimal))


def test_report_shape_and_scores():
    llm = fake()
    report = interview.generate_report(full(), [], llm=llm)
    assert set(report) == REPORT_KEYS
    assert report["evaluatedBaseQuestions"] == 3
    assert report["areas"]["content"] == {"score": 80, "notMeasuredReason": None}
    assert report["areas"]["delivery"] == {"score": 100, "notMeasuredReason": None}
    assert report["areas"]["attitude"] == {"score": None, "notMeasuredReason": "CALIBRATION_FAILED"}
    assert report["totalScore"] == 86 and report["grade"] == "양호"
    assert report["weightBasis"] == "내용 70% · 전달력 30% 기준"
    assert report["notMeasuredMessages"] == ["정면 보정이 되지 않아 태도는 제외했어요."]
    assert report["modelId"] == "test-model" and report["promptVersion"] == "C1-v1/C2-v1"
    assert report["scoringVersion"] == "v2.0" and "합격 확률이 아니에요" in report["notice"]
    assert "interviewDate" not in report  # 백엔드가 넣는다
    assert len(llm.calls) == 3 and len(llm.runs) == 1


def test_question_entries():
    report = interview.generate_report(full(), [], llm=fake())
    q1, q2, _ = report["questions"]
    assert all(set(q) == QUESTION_KEYS for q in report["questions"])
    assert q1["followUp"] == {"question": "q1 질문입니다.", "answerText": "직접 했습니다."}
    assert q1["answerText"] == NORMAL_TEXT and q1["contentScore"] == 80 and q1["evaluable"] is True
    assert q1["strengths"] == C2_OK["questions"][0]["strengths"] and q1["comment"] == C2_OK["questions"][0]["comment"]
    assert q1["metrics"] == {"speechRate": 300.0, "longPausePerMin": 0.0, "frontalRatio": None,
                             "timeLimitReached": False}
    assert q2["followUp"] is None


def test_json_and_dynamodb_round_trip():
    report = interview.generate_report(full(), [], llm=fake())
    assert json.loads(json.dumps(report, ensure_ascii=False)) == report
    again = to_plain(report)
    assert again["totalScore"] == report["totalScore"] and again["questions"][0]["metrics"]["speechRate"] == 300


def test_no_evaluable_answers_no_llm():
    s = dump(session([answer("q1", evaluable=False, reason="NO_ANSWER"),
                      answer("q2", evaluable=False, reason="TRANSCRIBE_FAILED"),
                      answer("q3", evaluable=False, reason="NO_ANSWER")]))
    llm = FakeToolLLM([])  # 부르면 실패한다
    report = interview.generate_report(s, [], llm=llm)
    assert report["totalScore"] is None and report["grade"] is None
    assert report["weightBasis"] == "평가할 수 있는 답변이 없어요"
    assert report["evaluatedBaseQuestions"] == 0
    assert all(a["score"] is None for a in report["areas"].values())
    assert [q["comment"] for q in report["questions"]] == ["답변이 없어 평가하지 않았어요.",
                                                           "음성을 변환하지 못해 평가하지 않았어요.",
                                                           "답변이 없어 평가하지 않았어요."]
    assert llm.calls == [] and llm.runs == []


def test_partial_bundles_two_of_three():
    s = dump(session([answer("q1"), answer("q2", evaluable=False, reason="NO_ANSWER"), answer("q3")]))
    llm = fake(qtypes=("experience", "situation"), qids=("q1", "q3"))
    report = interview.generate_report(s, [], llm=llm)
    assert report["evaluatedBaseQuestions"] == 2
    assert report["weightBasis"].endswith("평가 가능한 기본 질문 2/3개 기준")
    q2 = report["questions"][1]
    assert q2["contentScore"] is None and q2["strengths"] == [] and q2["direction"] is None
    assert q2["comment"] == "답변이 없어 평가하지 않았어요."
    assert len(llm.calls) == 2


def test_camera_not_used():
    # C §7 "카메라 미동의 → 음성만 진행, 태도 미측정"
    report = interview.generate_report(full(camera=False), [], llm=fake())
    assert report["areas"]["attitude"]["notMeasuredReason"] == "CAMERA_NOT_USED"


def test_delivery_unmeasured_content_only():
    short = delivery(rate=None, per_min=None)  # 세 답변 모두 15초 미만
    s = dump(session([answer("q1", metrics=short), answer("q2", metrics=short), answer("q3", metrics=short)]))
    report = interview.generate_report(s, [], llm=fake())
    assert report["areas"]["delivery"] == {"score": None, "notMeasuredReason": "NOT_ENOUGH_SPEECH"}
    assert report["weightBasis"] == "내용 100% 기준"


def with_frames():
    """기준값 + q1 묶음 10장(기본 6 정면, 꼬리 2 정면·2 눈만 내림) + q2 4장 정면. q3는 캡처 없음."""
    s = full()
    s["baseline"] = BASELINE
    items = (frames(6) + frames(2, answer_id="a-q1-2") + [frame("a-q1-2", gaze=(0.0, -20.0))] * 2
             + frames(4, answer_id="a-q2-1"))
    return s, items


def test_three_areas_and_frontal_ratio():
    # C §7 "정상 진행 → 3개 영역 점수": 정면 12/14 = 85.7% → 태도 100
    s, items = with_frames()
    report = interview.generate_report(s, items, llm=fake())
    assert report["areas"]["attitude"] == {"score": 100, "notMeasuredReason": None}
    assert report["weightBasis"] == "내용 50% · 전달력 25% · 태도 25% 기준"
    assert report["totalScore"] == 90 and report["grade"] == "우수"  # 80×0.5 + 100×0.25 + 100×0.25
    assert report["notMeasuredMessages"] == []
    assert [q["metrics"]["frontalRatio"] for q in report["questions"]] == [80, 100, None]  # q1 8/10, q2 4/4


def test_frontal_ratio_rounds_half_up():
    s = full()
    s["baseline"] = BASELINE
    items = frames(7, 1) + frames(2, 0, answer_id="a-q2-1")  # q1 7/8 = 87.5% → 88
    report = interview.generate_report(s, items, llm=fake())
    assert report["questions"][0]["metrics"]["frontalRatio"] == 88


def test_attitude_partial_ratio_score():
    s = full()
    s["baseline"] = BASELINE
    report = interview.generate_report(s, frames(6, 4), llm=fake())  # 60% → 50
    assert report["areas"]["attitude"]["score"] == 50
    assert report["questions"][0]["metrics"]["frontalRatio"] == 60


def test_calibration_failed_frames_ignored():
    # C §7 "정면 보정 실패 → 태도 미측정, 내용 70% + 전달력 30%"
    _, items = with_frames()
    report = interview.generate_report(full(), items, llm=fake())
    assert report["areas"]["attitude"]["notMeasuredReason"] == "CALIBRATION_FAILED"
    assert report["weightBasis"] == "내용 70% · 전달력 30% 기준"
    assert all(q["metrics"]["frontalRatio"] is None for q in report["questions"])


def test_camera_not_used_with_frames():
    s, items = with_frames()
    s["cameraConsent"] = False
    report = interview.generate_report(s, items, llm=fake())
    assert report["areas"]["attitude"]["notMeasuredReason"] == "CAMERA_NOT_USED"
    assert report["weightBasis"] == "내용 70% · 전달력 30% 기준"
    assert report["notMeasuredMessages"] == ["카메라를 사용하지 않아 태도는 제외했어요."]


def test_no_evaluable_answers_attitude_reason():
    s = dump(session([answer("q1", evaluable=False, reason="NO_ANSWER"), answer("q2", evaluable=False),
                      answer("q3", evaluable=False)], baseline=BASELINE))
    report = interview.generate_report(s, frames(10), llm=FakeToolLLM([]))
    assert report["areas"]["attitude"] == {"score": None, "notMeasuredReason": "NO_EVALUABLE_ANSWER"}
    assert all(q["metrics"]["frontalRatio"] is None for q in report["questions"])
    s["cameraConsent"] = False
    assert interview.generate_report(s, [], llm=FakeToolLLM([]))["areas"]["attitude"]["notMeasuredReason"] == \
        "CAMERA_NOT_USED"


@pytest.mark.parametrize("bad", [None, {"type": "ANSWER"}, "frames"])
def test_frames_must_be_a_list(bad):
    llm = fake()
    with pytest.raises(InterviewError) as exc:
        interview.generate_report(full(), bad, llm=llm)
    assert exc.value.code == INVALID_INPUT and llm.calls == []


def test_frames_round_trip_through_dynamodb():
    s, items = with_frames()
    # 백엔드는 Session·FRAME을 DynamoDB에서 꺼내 넘기고(0.0 → 0), 리포트도 저장했다가 다시 연다
    report = interview.generate_report(to_plain(s), to_plain(items), llm=fake())
    assert json.loads(json.dumps(report, ensure_ascii=False)) == report
    again = to_plain(report)
    assert again["areas"]["attitude"] == {"score": 100, "notMeasuredReason": None}
    assert [q["metrics"]["frontalRatio"] for q in again["questions"]] == [80, 100, None]


def test_content_invalid_twice_stops_before_feedback():
    llm = fake(c1_responses=['{"items": []}', '{"items": []}'])
    with pytest.raises(InterviewError) as exc:
        interview.generate_report(full(), [], llm=llm)
    assert exc.value.code == AI_OUTPUT_INVALID and llm.runs == []


def test_feedback_invalid_twice_raises():
    bad = json.dumps({"questions": []})
    llm = FakeToolLLM([bad, bad], responses=[c1("experience"), c1("knowledge"), c1("situation")])
    with pytest.raises(InterviewError) as exc:
        interview.generate_report(full(), [], llm=llm)
    assert exc.value.code == AI_OUTPUT_INVALID and len(llm.runs) == 2


def test_invalid_session_rejected():
    with pytest.raises(InterviewError) as exc:
        interview.generate_report({"job": "데이터 분석"}, [], llm=fake())
    assert exc.value.code == INVALID_INPUT


def test_missing_model_id_fails_before_llm(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    llm = fake()
    with pytest.raises(InterviewError) as exc:
        interview.generate_report(full(), [], llm=llm)
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False and llm.calls == []


def test_backend_positional_call_shape(monkeypatch):
    from interview import llm as llm_module

    monkeypatch.setattr(llm_module, "default_client", lambda: fake())
    report = interview.generate_report(full(), [])  # 백엔드 make_report와 같은 인자 2개
    assert report["totalScore"] == 86


def test_logs_have_no_raw_text(caplog):
    with caplog.at_level(logging.DEBUG):
        interview.generate_report(full(), [], llm=fake())
    assert "stage=generate_report bundles=3" in caplog.text
    for secret in ("관광지", "직접 했습니다", C2_OK["questions"][0]["comment"], "q1 질문입니다"):
        assert secret not in caplog.text
