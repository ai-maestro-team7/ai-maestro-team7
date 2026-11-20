"""꼬리질문 판단 (Prompt_B, design §7.3, C F-07).

LLM이 꼬리질문을 여러 개 주면 첫 번째 하나만 쓴다 (C §7 "꼬리질문 2개 이상 요청").
꼬리질문을 몇 개 낼지는 process_answer가 정한다. 이 함수는 필요 여부와 문장만 돌려준다.
"""

import logging
from dataclasses import dataclass

from . import llm as llm_module
from . import prompting
from .models import FollowUpOutput

logger = logging.getLogger("interview")

STAGE = "judge_follow_up"


@dataclass(frozen=True)
class FollowUpDecision:
    need: bool
    reason: str
    question: str | None


def judge_follow_up(job: str, resume_text: str, question: str, answer_text: str, *, llm=None) -> FollowUpDecision:
    client = llm if llm is not None else llm_module.default_client()
    output = llm_module.call_json(
        client,
        system_prompt=prompting.system_prompt(),
        user_prompt=prompting.follow_up_prompt(job, resume_text, question, answer_text),
        schema=FollowUpOutput,
        stage=STAGE,
    )
    chosen = output.follow_up_questions[0] if output.need_follow_up else None
    logger.info("stage=%s reason=%s candidates=%d", STAGE, output.reason, len(output.follow_up_questions))
    return FollowUpDecision(need=output.need_follow_up, reason=output.reason, question=chosen)
