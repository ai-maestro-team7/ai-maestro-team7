"""꼬리질문 판단 (Prompt_B, design §7.3, C F-07, follow-up design §4).

LLM이 꼬리질문을 여러 개 주면 첫 번째 하나만 쓴다 (C §7 "꼬리질문 2개 이상 요청").
꼬리질문을 몇 개 낼지는 process_answer가 정한다. 이 함수는 필요 여부와 문장만 돌려준다.

판단 출력이 실패하면(AI_OUTPUT_INVALID: 형식 2번 실패, 출력 잘림) 예외 대신 꼬리질문 없음(JUDGE_FAILED)을
돌려준다. 꼬리질문 판단 한 번 실패로 면접이 끊기지 않게 한다 (#109, follow-up 결정 5).
Bedrock 호출 실패(AWS_SERVICE_ERROR)와 설정 오류는 그대로 던진다.
"""

import logging
from dataclasses import dataclass

from . import llm as llm_module
from . import prompting
from .errors import AI_OUTPUT_INVALID, InterviewError
from .models import FollowUpOutput

logger = logging.getLogger("interview")

STAGE = "judge_follow_up"

JUDGE_FAILED = "JUDGE_FAILED"


@dataclass(frozen=True)
class FollowUpDecision:
    need: bool
    reason: str  # ABSTRACT / INCONSISTENT / SUFFICIENT / JUDGE_FAILED → 답변 기록의 followUpCheck
    question: str | None


def judge_follow_up(job: str, resume_text: str, question: str, answer_text: str, *, llm=None) -> FollowUpDecision:
    client = llm if llm is not None else llm_module.default_client()
    try:
        output = llm_module.call_json(
            client,
            system_prompt=prompting.system_prompt(),
            user_prompt=prompting.follow_up_prompt(job, resume_text, question, answer_text),
            schema=FollowUpOutput,
            stage=STAGE,
        )
    except InterviewError as exc:
        if exc.code != AI_OUTPUT_INVALID:
            raise
        logger.warning("stage=%s fallback=NO_FOLLOW_UP errorCode=%s", STAGE, exc.code)
        return FollowUpDecision(need=False, reason=JUDGE_FAILED, question=None)
    chosen = output.follow_up_questions[0] if output.need_follow_up else None
    logger.info("stage=%s reason=%s candidates=%d dropped=%d", STAGE, output.reason,
                len(output.follow_up_questions), output.dropped_candidates)
    return FollowUpDecision(need=output.need_follow_up, reason=output.reason, question=chosen)
