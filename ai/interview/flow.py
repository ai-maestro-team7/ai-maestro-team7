"""면접 진행 규칙: start_interview, process_answer (design §5).

진행 규칙(질문 수, 꼬리질문 수, 평가 불가 처리, 다음 행동)은 이 파일의 코드가 정한다.
LLM은 질문 문장과 꼬리질문 필요 여부만 준다 (C §2.3).
받은 Session은 바꾸지 않고 새 값을 돌려준다. DB·API를 부르지 않는다.
"""

import logging
import time

from . import settings
from .config import load_scoring_config
from .delivery import measure_delivery
from .errors import INVALID_INPUT, InterviewError
from .follow_up import judge_follow_up
from .models import (AnswerRecord, AnswerResult, NextQuestion, Question, Session, StartInterviewInput, dump,
                     parse_input)
from .questions import generate_from_request
from .versions import PROMPT_VERSION, SCORING_VERSION

logger = logging.getLogger("interview")

STAGE_START = "start_interview"
STAGE_ANSWER = "process_answer"

STATE_MESSAGE = "지금은 이 답변을 처리할 수 없어요. 면접 진행 상태를 확인해 주세요."


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def base_question(question: Question) -> NextQuestion:
    """기본 질문의 답변 ID는 a-{질문 ID}-1이다 (C ★ 주요 데이터 형식)."""
    return NextQuestion(question_id=question.question_id, answer_id=f"a-{question.question_id}-1",
                        text=question.question, is_follow_up=False)


def follow_up_question(question: Question, text: str) -> NextQuestion:
    """꼬리질문은 질문 ID {기본}-f, 답변 ID a-{기본}-2다."""
    return NextQuestion(question_id=f"{question.question_id}-f", answer_id=f"a-{question.question_id}-2",
                        text=text, is_follow_up=True)


def start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None, *, llm=None):
    started = time.monotonic()
    request = parse_input(StartInterviewInput, {
        "session_id": session_id, "job": job, "resume_text": resume_text, "interview_type": interview_type,
        "camera_consent": camera_consent, "profile": profile,
    }, stage=STAGE_START)
    model_id = settings.model_id()  # 모델을 부르기 전에 설정부터 확인한다
    questions = generate_from_request(request, llm)
    first = base_question(questions[0])
    session = Session(
        session_id=request.session_id, job=request.job, interview_type=request.interview_type,
        camera_consent=request.camera_consent, resume_text=request.resume_text, profile=request.profile,
        scoring_version=SCORING_VERSION, model_id=model_id, prompt_version=PROMPT_VERSION,
        questions=questions, current_index=0, follow_up_used=False, current_question=first,
        answers=[], baseline=None,
    )
    logger.info("stage=%s durationMs=%d", STAGE_START, _ms(started))
    return {"session": dump(session), "nextQuestion": dump(first)}


def _reject(rule: str):
    logger.warning("stage=%s errorCode=%s rule=%s", STAGE_ANSWER, INVALID_INPUT, rule)
    raise InterviewError(INVALID_INPUT, STATE_MESSAGE)


def _check_state(current: Session, pending: NextQuestion | None, answer_id: str) -> Question:
    """지금 받을 수 있는 답변인지 확인하고, 그 답변이 속한 기본 질문을 돌려준다."""
    if pending is None or current.current_index >= len(current.questions):
        _reject("finished")
    base = current.questions[current.current_index]
    expected_id = f"{base.question_id}-f" if current.follow_up_used else base.question_id
    if pending.question_id != expected_id or pending.is_follow_up != current.follow_up_used:
        _reject("inconsistent_session")
    if answer_id != pending.answer_id:
        _reject("unexpected_answer_id")
    return base


def _evaluate(result: AnswerResult) -> tuple[bool, str | None, str | None]:
    """(평가 가능 여부, 평가 불가 사유, 저장할 답변 텍스트). C §4.2 무응답·변환 실패 규칙."""
    status = result.transcription.status
    if status == "IN_PROGRESS":
        _reject("transcription_in_progress")
    if status == "FAILED":
        return False, "TRANSCRIBE_FAILED", None
    text = (result.transcription.text or "").strip()  # 공백·탭·줄바꿈만 있으면 말이 없는 것으로 본다
    if not text:
        return False, "NO_ANSWER", ""
    return True, None, text


def process_answer(session, answer_result, *, llm=None):
    started = time.monotonic()
    current = parse_input(Session, session, stage=STAGE_ANSWER)
    result = parse_input(AnswerResult, answer_result, stage=STAGE_ANSWER)
    pending = current.current_question
    base = _check_state(current, pending, result.answer_id)
    evaluable, reason, text = _evaluate(result)
    # 전달력은 평가 가능한 답변만 잰다. LLM 호출 전에 한다 (순수 계산, 설정 오류만 실패)
    delivery = (measure_delivery(text, result.transcription.words, load_scoring_config().delivery)
                if evaluable else None)

    new = current.model_copy(deep=True)  # 받은 Session은 바꾸지 않는다
    new.answers.append(AnswerRecord(
        answer_id=pending.answer_id, question_id=pending.question_id, is_follow_up=pending.is_follow_up,
        question=pending.text, answer_text=text, evaluable=evaluable, reason=reason,
        time_limit_reached=result.time_limit_reached, delivery=delivery,
    ))

    action, next_question = None, None
    # 꼬리질문은 기본 질문당 최대 1개: 기본 질문이고, 평가 가능하고, 아직 꼬리질문을 쓰지 않았을 때만 판단한다
    if not pending.is_follow_up and evaluable and not new.follow_up_used:
        decision = judge_follow_up(new.job, new.resume_text, pending.text, text, llm=llm)
        if decision.need:
            next_question = follow_up_question(base, decision.question)
            new.follow_up_used = True
            new.current_question = next_question
            action = "FOLLOW_UP"

    if action is None:
        new.current_index += 1
        new.follow_up_used = False
        if new.current_index < len(new.questions):
            next_question = base_question(new.questions[new.current_index])
            new.current_question = next_question
            action = "NEXT_QUESTION"
        else:
            new.current_question = None
            action = "REPORT"

    logger.info("stage=%s action=%s evaluable=%s reason=%s speechRateReason=%s longPauseReason=%s durationMs=%d",
                STAGE_ANSWER, action, evaluable, reason,
                delivery.speech_rate_reason if delivery is not None else None,
                delivery.long_pause_reason if delivery is not None else None, _ms(started))
    return {
        "session": dump(new),
        "action": action,
        "nextQuestion": dump(next_question) if next_question is not None else None,
        "lastAnswer": {"answerId": pending.answer_id, "evaluable": evaluable, "reason": reason},
    }
