"""결과 리포트 generate_report (report design §7, Requirement 5, C §2.2-5·§5.4).

순서: Session 검사 → 묶음 → 내용 평가(C-1, 묶음마다) → 점수 계산(코드) → 피드백 에이전트(C-2) → 조립.
- 점수는 코드가 확정하고, LLM은 항목 점수(C-1)와 피드백 문장(C-2)만 만든다
- 태도는 4차(#108)부터 frames의 정면 응시 비율로 계산하고, 문항별 비율을 metrics.frontalRatio에 넣는다
- 평가 가능한 답변이 없으면 LLM을 부르지 않고 점수 없는 리포트를 만든다
- interviewDate는 백엔드 make_report가 넣는다
"""

import logging
import time

from . import llm as llm_module
from . import settings
from .bundles import Bundle, make_bundles
from .config import load_scoring_config
from .content import evaluate_content
from .errors import INVALID_INPUT, InterviewError
from .feedback import FeedbackItem, build_feedback_context, write_feedback
from .models import INVALID_INPUT_MESSAGE, Session, parse_input
from .scoring import calculate_interview_scores, round_half_up
from .versions import REPORT_PROMPT_VERSION

logger = logging.getLogger("interview")

STAGE = "generate_report"

NOTICE = "면접 점수는 실제 합격 확률이 아니에요. 연습용 참고 지표예요."
NO_EVALUABLE_MESSAGE = "평가할 수 있는 답변이 없어요"
UNEVALUABLE_COMMENTS = {
    "NO_ANSWER": "답변이 없어 평가하지 않았어요.",
    "TRANSCRIBE_FAILED": "음성을 변환하지 못해 평가하지 않았어요.",
    None: "답변하지 않은 질문이라 평가하지 않았어요.",
}


def _metrics(bundle: Bundle, frontal: float | None) -> dict:
    base = bundle.base
    delivery = base.delivery if base is not None else None
    return {
        "speechRate": delivery.speech_rate if delivery is not None else None,
        "longPausePerMin": delivery.long_pause_per_min if delivery is not None else None,
        "frontalRatio": round_half_up(frontal) if frontal is not None else None,  # 기본+꼬리 묶음의 정면 비율(%)
        "timeLimitReached": base.time_limit_reached if base is not None else False,
    }


def _question_entry(bundle: Bundle, content_score: int | None, fb: FeedbackItem | None,
                    frontal: float | None = None) -> dict:
    base, follow_up = bundle.base, bundle.follow_up
    entry = {
        "questionId": bundle.question_id,
        "question": bundle.question.question,
        "followUp": ({"question": follow_up.question, "answerText": follow_up.answer_text}
                     if follow_up is not None else None),
        "answerText": base.answer_text if base is not None else None,
        "evaluable": bundle.evaluable,
        "reason": base.reason if base is not None else None,
        "contentScore": content_score,
        "strengths": list(fb.strengths) if fb else [],
        "improvements": list(fb.improvements) if fb else [],
        "direction": fb.direction if fb else None,
        "metrics": _metrics(bundle, frontal),
        "comment": fb.comment if fb else UNEVALUABLE_COMMENTS[base.reason if base is not None else None],
    }
    return entry


def generate_report(session, frames, *, llm=None):
    started = time.monotonic()
    current = parse_input(Session, session, stage=STAGE)
    if not isinstance(frames, list):
        # 캡처 하나의 형식 오류는 그 캡처만 빼지만(camera 결정 5), 목록 자체가 아니면 호출 형식이 틀렸다
        logger.warning("stage=%s errorCode=%s fields=frames", STAGE, INVALID_INPUT)
        raise InterviewError(INVALID_INPUT, INVALID_INPUT_MESSAGE)
    config = load_scoring_config()
    model_id = settings.model_id()  # 모델을 부르기 전에 설정부터 확인한다
    bundles = make_bundles(current)
    evaluable = [b for b in bundles if b.evaluable]
    report = {
        "job": current.job,
        "interviewType": current.interview_type,
        "evaluatedBaseQuestions": len(evaluable),
        "scoringVersion": config.scoring_version,
        "modelId": model_id,
        "promptVersion": REPORT_PROMPT_VERSION,
        "notice": NOTICE,
    }

    if not evaluable:
        # 점수 함수와 LLM을 부르지 않는다 (노션 6-④)
        reason = {"score": None, "notMeasuredReason": "NO_EVALUABLE_ANSWER"}
        report.update({
            "totalScore": None, "grade": None, "weightBasis": NO_EVALUABLE_MESSAGE,
            "areas": {"content": dict(reason), "delivery": dict(reason),
                      "attitude": {"score": None, "notMeasuredReason": (
                          "NO_EVALUABLE_ANSWER" if current.camera_consent else "CAMERA_NOT_USED")}},
            "notMeasuredMessages": [],
            "questions": [_question_entry(b, None, None) for b in bundles],
        })
        logger.info("stage=%s bundles=0 durationMs=%d", STAGE, int((time.monotonic() - started) * 1000))
        return report

    client = llm if llm is not None else llm_module.default_client()
    content = {b.question_id: evaluate_content(current.job, current.resume_text, b, llm=client) for b in evaluable}
    score = calculate_interview_scores(current, frames, config, content)
    feedback = write_feedback(build_feedback_context(evaluable, content, score, current.resume_text),
                              llm=client).by_question()
    content_scores = {b.question_id: b.content_score for b in score.bundles}
    frontal = {f.question_id: f.frontal_ratio for f in score.frontal_ratios}

    report.update({
        "totalScore": score.total_score,
        "grade": score.grade,
        "weightBasis": score.weight_basis,
        "areas": score.areas.model_dump(by_alias=True, mode="json"),
        "notMeasuredMessages": list(score.not_measured_messages),
        "questions": [_question_entry(b, content_scores.get(b.question_id), feedback.get(b.question_id),
                                      frontal.get(b.question_id)) for b in bundles],
    })
    logger.info("stage=%s bundles=%d durationMs=%d", STAGE, len(evaluable), int((time.monotonic() - started) * 1000))
    return report
