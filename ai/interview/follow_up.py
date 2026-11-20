"""꼬리질문 판단 (Prompt_B, C F-07, follow-up design §4, #109).

읽기 전용 툴 3개를 쓰는 Strands 에이전트가 판단한다. 툴은 이 판단 하나의 데이터(FollowUpContext)에 묶여 만들어진다.
- find_resume_passages(keyword): 자소서에서 키워드가 든 문장 (피드백 툴과 같은 tools.search_resume)
- get_previous_answers(): 이번 답변 전의 평가 가능한 답변 (최대 5개, 답변당 500자)
- get_remaining_questions(): 이번 기본 질문 뒤의 기본 질문
툴은 복사본만 돌려주고 아무것도 바꾸지 않는다. 사용자·세션 ID를 인자로 받지 않는다.
자소서 전문은 프롬프트에도 그대로 넣는다 (follow-up 결정 2).

LLM이 꼬리질문을 여러 개 주면 첫 번째 하나만 쓴다 (C §7 "꼬리질문 2개 이상 요청").
꼬리질문을 몇 개 낼지는 process_answer가 정한다. 이 함수는 필요 여부와 문장만 돌려준다.

판단 출력이 실패하면(AI_OUTPUT_INVALID: 형식 2번 실패, 턴·토큰·툴 호출 상한, 출력 잘림) 예외 대신
꼬리질문 없음(JUDGE_FAILED)을 돌려준다. 꼬리질문 판단 한 번 실패로 면접이 끊기지 않게 한다 (follow-up 결정 5).
Bedrock 호출 실패(AWS_SERVICE_ERROR)와 설정 오류는 그대로 던진다.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from . import llm as llm_module
from . import prompting, settings
from .errors import AI_OUTPUT_INVALID, InterviewError
from .models import FollowUpOutput, Question, QuestionType, Session
from .tools import ToolUsage, search_resume

logger = logging.getLogger("interview")

STAGE = "judge_follow_up"

JUDGE_FAILED = "JUDGE_FAILED"


@dataclass(frozen=True)
class FollowUpDecision:
    need: bool
    reason: str  # ABSTRACT / INCONSISTENT / SUFFICIENT / JUDGE_FAILED → 답변 기록의 followUpCheck
    question: str | None


# ---------------------------------------------------------------- 툴이 보는 데이터 (고정)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PreviousAnswer(_Frozen):
    question_id: str
    is_follow_up: bool
    question: str
    answer_text: str


class RemainingQuestion(_Frozen):
    question_id: str
    question_type: QuestionType
    question: str


class FollowUpContext(_Frozen):
    job: str
    resume_text: str
    question_type: QuestionType
    question: str
    answer_text: str
    previous: tuple[PreviousAnswer, ...]
    remaining: tuple[RemainingQuestion, ...]


def build_follow_up_context(session: Session, base: Question, question_text: str, answer_text: str) -> FollowUpContext:
    """이번 답변을 기록하기 **전** Session으로 만든다. 그래서 이번 답변과 그 이후 데이터는 들어갈 수 없다.

    이전 답변은 평가 가능한 것만 앞에서부터 FOLLOW_UP_PREVIOUS_MAX개, 답변당 FOLLOW_UP_ANSWER_MAX_CHARS자까지.
    남은 기본 질문은 session.questions에서 이번 기본 질문 뒤의 것 전부.
    """
    previous = tuple(
        PreviousAnswer(question_id=a.question_id, is_follow_up=a.is_follow_up, question=a.question,
                       answer_text=(a.answer_text or "")[:settings.FOLLOW_UP_ANSWER_MAX_CHARS])
        for a in session.answers if a.evaluable
    )[:settings.FOLLOW_UP_PREVIOUS_MAX]
    ids = [q.question_id for q in session.questions]
    after = session.questions[ids.index(base.question_id) + 1:]
    remaining = tuple(RemainingQuestion(question_id=q.question_id, question_type=q.question_type,
                                        question=q.question) for q in after)
    return FollowUpContext(job=session.job, resume_text=session.resume_text, question_type=base.question_type,
                           question=question_text, answer_text=answer_text, previous=previous, remaining=remaining)


# ---------------------------------------------------------------- 툴 (조회만)


def make_follow_up_tools(context: FollowUpContext, usage: ToolUsage) -> list[Callable[..., Any]]:
    """context에 묶인 읽기 전용 툴 3개. 반환 값은 모두 새로 만든 dict(복사본)이다."""

    def find_resume_passages(keyword: str) -> dict:
        """자소서에서 키워드가 들어 있는 문장을 최대 3개 찾는다. 답변을 자소서 내용과 맞춰 볼 때 쓴다.

        Args:
            keyword: 찾을 단어 (1~30자)
        """
        if (limited := usage.take("find_resume_passages")) is not None:
            return limited
        return search_resume(context.resume_text, keyword)

    def get_previous_answers() -> dict:
        """이번 면접에서 지금 답변 전까지의 질문과 답변(평가 가능한 것만)을 조회한다. 앞 답변과 모순되거나 겹치는지 볼 때 쓴다."""
        if (limited := usage.take("get_previous_answers")) is not None:
            return limited
        answers = [{"questionId": p.question_id, "isFollowUp": p.is_follow_up, "question": p.question,
                    "answerText": p.answer_text} for p in context.previous]
        return {"answers": answers, "count": len(answers)}

    def get_remaining_questions() -> dict:
        """이번 질문 뒤에 나올 기본 질문을 조회한다. 꼬리질문이 앞으로 나올 질문과 겹치지 않게 할 때 쓴다. 마지막 질문이면 빈 목록이다."""
        if (limited := usage.take("get_remaining_questions")) is not None:
            return limited
        questions = [{"questionId": q.question_id, "questionType": q.question_type, "question": q.question}
                     for q in context.remaining]
        return {"questions": questions, "count": len(questions)}

    return [find_resume_passages, get_previous_answers, get_remaining_questions]


# ---------------------------------------------------------------- 공개 함수


def judge_follow_up(context: FollowUpContext, *, llm=None) -> FollowUpDecision:
    started = time.monotonic()
    client = llm if llm is not None else llm_module.default_client()
    usage = ToolUsage(settings.FOLLOW_UP_MAX_TOOL_CALLS)
    try:
        output = llm_module.call_json_with_tools(
            client,
            system_prompt=prompting.system_prompt(),
            user_prompt=prompting.follow_up_prompt(context.job, context.resume_text, context.question_type,
                                                   context.question, context.answer_text),
            tools=make_follow_up_tools(context, usage),
            limits={"turns": settings.FOLLOW_UP_MAX_TURNS, "total_tokens": settings.FOLLOW_UP_MAX_TOTAL_TOKENS},
            max_tokens=settings.follow_up_max_tokens(),
            schema=FollowUpOutput, stage=STAGE, before_attempt=usage.start_attempt,
        )
    except InterviewError as exc:
        if exc.code != AI_OUTPUT_INVALID:
            raise
        logger.warning("stage=%s fallback=NO_FOLLOW_UP errorCode=%s attempts=%d toolCalls=%s durationMs=%d", STAGE,
                       exc.code, usage.attempts, usage.summary(), int((time.monotonic() - started) * 1000))
        return FollowUpDecision(need=False, reason=JUDGE_FAILED, question=None)
    chosen = output.follow_up_questions[0] if output.need_follow_up else None
    # 툴 이름과 횟수, 코드만 남긴다. 툴 입력·결과(자소서·답변)와 꼬리질문 문장은 남기지 않는다
    logger.info("stage=%s reason=%s candidates=%d dropped=%d attempts=%d toolCalls=%s durationMs=%d", STAGE,
                output.reason, len(output.follow_up_questions), output.dropped_candidates, usage.attempts,
                usage.summary(), int((time.monotonic() - started) * 1000))
    return FollowUpDecision(need=output.need_follow_up, reason=output.reason, question=chosen)
