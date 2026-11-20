"""면접 진행 규칙: start_interview, process_answer (design §5).

진행 규칙(질문 수, 꼬리질문 수, 평가 불가 처리, 다음 행동)은 이 파일의 코드가 정한다.
LLM은 질문 문장과 꼬리질문 필요 여부만 준다 (C §2.3).
받은 Session은 바꾸지 않고 새 값을 돌려준다. DB·API를 부르지 않는다.
"""

import logging
import time

from . import settings
from .models import NextQuestion, Question, Session, StartInterviewInput, dump, parse_input
from .questions import generate_from_request
from .versions import PROMPT_VERSION, SCORING_VERSION

logger = logging.getLogger("interview")

STAGE_START = "start_interview"
STAGE_ANSWER = "process_answer"


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


def process_answer(session, answer_result, *, llm=None):
    raise NotImplementedError
