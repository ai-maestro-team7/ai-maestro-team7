"""채점 테스트용 Session·답변·C-1 결과 만들기. AWS·LLM을 부르지 않는다."""

from interview.models import ContentEvaluation, ContentItem, Session

QUESTION_TYPES = ("experience", "knowledge", "situation")
RUBRIC_KEYS = {
    "experience": ("relevance", "specificity", "structure", "outcome"),
    "knowledge": ("accuracy", "relevance", "logic", "support"),
    "situation": ("understanding", "reasoning", "process", "alternatives"),
}


def delivery(rate=300.0, per_min=0.0, answer_sec=60.0, count=0):
    """측정값. rate·per_min에 None을 주면 그 항목은 미측정(TOO_SHORT)."""
    return {
        "answerSec": answer_sec,
        "speechRate": rate, "speechRateReason": None if rate is not None else "TOO_SHORT",
        "longPauseCount": count if per_min is not None else None,
        "longPausePerMin": per_min, "longPauseReason": None if per_min is not None else "TOO_SHORT",
    }


def answer(qid, text="저는 자료를 비교하고 대응표를 만들었습니다.", follow_up=False, evaluable=True, reason=None,
           time_limit=False, metrics="default"):
    n = 2 if follow_up else 1
    base = qid
    record = {"answerId": f"a-{base}-{n}", "questionId": f"{base}-f" if follow_up else base, "isFollowUp": follow_up,
              "question": f"{base} 질문입니다.", "answerText": text if evaluable else ("" if reason == "NO_ANSWER" else None),
              "evaluable": evaluable, "reason": None if evaluable else (reason or "NO_ANSWER"),
              "timeLimitReached": time_limit}
    if evaluable and metrics is not None:
        record["delivery"] = delivery() if metrics == "default" else metrics
    if not evaluable:
        record["delivery"] = None
    return record


BASELINE = {"gaze": {"yaw": 0.0, "pitch": -10.0}, "head": {"yaw": 0.0, "pitch": 5.0}}  # 노트북 카메라 정면 (C §2.3)


def frame(answer_id="a-q1-1", gaze=(0.0, -10.0), head=(0.0, 5.0), eyes=(True, 98.0), accepted=True, valid=True,
          ftype="ANSWER"):
    """백엔드가 저장한 캡처 한 장 (make_report가 generate_report에 넘기는 키). gaze·head는 (yaw, pitch)."""
    qid = answer_id.split("-")[1] + ("-f" if answer_id.endswith("-2") else "")
    return {"type": ftype, "questionId": qid, "answerId": answer_id, "capturedAt": "2026-11-21T10:00:00+09:00",
            "accepted": accepted, "valid": valid,
            "gaze": {"yaw": gaze[0], "pitch": gaze[1]} if valid else None,
            "head": {"yaw": head[0], "pitch": head[1]} if valid else None,
            "eyesOpen": {"value": eyes[0], "confidence": eyes[1]} if valid and eyes is not None else None}


def frames(n_frontal, n_away=0, answer_id="a-q1-1"):
    """정면 n_frontal장 + 고개 돌림 n_away장."""
    return [frame(answer_id)] * n_frontal + [frame(answer_id, head=(35.0, 5.0))] * n_away


def session(answers, camera=True, baseline=None):
    questions = [{"questionId": f"q{i}", "questionType": t, "question": f"q{i} 질문입니다."}
                 for i, t in enumerate(QUESTION_TYPES, start=1)]
    return Session.model_validate({
        "sessionId": "iv-score", "job": "데이터 분석", "interviewType": "MIXED", "cameraConsent": camera,
        "resumeText": "가" * 60, "profile": None, "scoringVersion": "v1.0", "modelId": "test-model",
        "promptVersion": "A-v2/B-v1", "questions": questions, "currentIndex": 3, "followUpUsed": False,
        "currentQuestion": None, "answers": answers, "baseline": baseline,
    })


def evaluation(qid, scores=(4, 4, 4, 4)):
    qtype = QUESTION_TYPES[int(qid[1:]) - 1]
    items = tuple(ContentItem(key=k, score=s, evidence_type="missing", evidence="빠진 요소", evidence_verified=True)
                  for k, s in zip(RUBRIC_KEYS[qtype], scores))
    return ContentEvaluation(question_id=qid, question_type=qtype, items=items)


def all_evaluations(qids=("q1", "q2", "q3"), scores=(4, 4, 4, 4)):
    return {q: evaluation(q, scores) for q in qids}
