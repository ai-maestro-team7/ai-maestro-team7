"""피드백 에이전트 write_feedback (프롬프트 C-2, report design §6, requirements 결정 7·Requirement 4).

점수는 scoring.py가 먼저 확정한다. 에이전트(Strands)는 아래 읽기 전용 툴 4개를 골라 불러 정보를 모은 뒤
피드백 JSON을 쓴다. 툴은 이미 확정된 값의 복사본만 돌려주고 계산·AWS 호출·저장을 하지 않는다.
- 툴은 이 리포트 하나의 데이터(FeedbackContext)에 묶여 만들어진다. 사용자·세션 ID를 인자로 받지 않는다
- 점수를 바꾸는 툴이 없고, 출력 스키마에도 점수 필드가 없다
"""

import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import llm as llm_module
from . import prompting, settings
from .bundles import Bundle
from .models import ContentEvaluation, DeliveryMetrics, QuestionType, ScoreResult, _LLMOutputModel

logger = logging.getLogger("interview")

STAGE = "write_feedback"

RESUME_PASSAGE_LIMIT = 3
PASSAGE_MAX_CHARS = 200
KEYWORD_MAX_CHARS = 30
TEXT_MIN, TEXT_MAX = 5, 200
FEEDBACK_LIST_MAX = 2  # 강점·보완은 질문마다 최대 2개

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


# ---------------------------------------------------------------- 툴이 보는 데이터 (고정)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FeedbackBundle(_Frozen):
    question_id: str
    question_type: QuestionType
    question: str
    answer_text: str
    follow_up_question: str | None
    follow_up_answer: str | None
    time_limit_reached: bool
    delivery: DeliveryMetrics | None
    content: ContentEvaluation


class FeedbackContext(_Frozen):
    bundles: tuple[FeedbackBundle, ...]
    score: ScoreResult
    resume_text: str

    def bundle(self, question_id: str) -> FeedbackBundle | None:
        return next((b for b in self.bundles if b.question_id == question_id), None)

    @property
    def question_ids(self) -> list[str]:
        return [b.question_id for b in self.bundles]


def build_feedback_context(bundles: list[Bundle], content: dict[str, ContentEvaluation], score: ScoreResult,
                           resume_text: str) -> FeedbackContext:
    """평가 가능한 묶음만 담는다. 측정값은 기본 답변 것이다."""
    items = []
    for b in bundles:
        follow_up = b.follow_up if b.follow_up is not None and b.follow_up.evaluable else None
        items.append(FeedbackBundle(
            question_id=b.question_id, question_type=b.question.question_type, question=b.base.question,
            answer_text=b.base.answer_text or "",
            follow_up_question=follow_up.question if follow_up else None,
            follow_up_answer=follow_up.answer_text if follow_up else None,
            time_limit_reached=b.base.time_limit_reached, delivery=b.base.delivery, content=content[b.question_id],
        ))
    return FeedbackContext(bundles=tuple(items), score=score, resume_text=resume_text)


# ---------------------------------------------------------------- 툴 (조회만)


class ToolUsage:
    """툴 호출 횟수. 상한을 넘으면 툴이 '지금까지 정보로 답하라'를 돌려준다."""

    def __init__(self, limit: int):
        self.limit = limit
        self.calls: Counter[str] = Counter()

    @property
    def total(self) -> int:
        return sum(self.calls.values())

    def take(self, name: str) -> dict | None:
        self.calls[name] += 1
        if self.total > self.limit:
            return {"error": "TOOL_LIMIT", "message": "도구 호출 한도에 닿았습니다. 지금까지 받은 정보로 답을 쓰세요."}
        return None

    def summary(self) -> str:
        return ",".join(f"{name}:{n}" for name, n in sorted(self.calls.items())) or "none"


def _normalize(text: str) -> str:
    return " ".join(text.split())


def make_feedback_tools(context: FeedbackContext, usage: ToolUsage) -> list[Callable[..., Any]]:
    """context에 묶인 읽기 전용 툴 4개. 반환 값은 모두 새로 만든 dict(복사본)이다."""

    def _unknown(question_id: str) -> dict:
        return {"error": "UNKNOWN_QUESTION", "questionIds": context.question_ids}

    def get_confirmed_scores(question_id: str) -> dict:
        """확정된 점수를 조회한다. 코드가 계산한 값이며 바꿀 수 없다.

        Args:
            question_id: 기본 질문 ID (예: "q1")
        """
        if (limited := usage.take("get_confirmed_scores")) is not None:
            return limited
        b = context.bundle(question_id)
        if b is None:
            return _unknown(question_id)
        bundle_score = next(s for s in context.score.bundles if s.question_id == question_id)
        return {
            "questionId": question_id,
            "contentScore": bundle_score.content_score,
            "contentItems": [{"key": i.key, "score": i.score, "evidenceType": i.evidence_type,
                              "evidence": i.evidence} for i in b.content.items if i.evidence_verified],
            "deliveryScore": bundle_score.delivery_score,
            "areas": context.score.areas.model_dump(by_alias=True, mode="json"),
            "notMeasured": list(context.score.not_measured_messages),
        }

    def get_delivery_metrics(question_id: str) -> dict:
        """기본 답변의 전달력 측정값(말 속도, 분당 긴 침묵, 시간 제한 도달)을 조회한다. 값이 null이면 미측정이다.

        Args:
            question_id: 기본 질문 ID (예: "q1")
        """
        if (limited := usage.take("get_delivery_metrics")) is not None:
            return limited
        b = context.bundle(question_id)
        if b is None:
            return _unknown(question_id)
        metrics = b.delivery.model_dump(by_alias=True, mode="json") if b.delivery is not None else None
        return {"questionId": question_id, "timeLimitReached": b.time_limit_reached, "metrics": metrics}

    def get_answer_text(question_id: str) -> dict:
        """질문과 지원자의 답변 원문(꼬리질문과 그 답변 포함)을 조회한다.

        Args:
            question_id: 기본 질문 ID (예: "q1")
        """
        if (limited := usage.take("get_answer_text")) is not None:
            return limited
        b = context.bundle(question_id)
        if b is None:
            return _unknown(question_id)
        return {"questionId": question_id, "questionType": b.question_type, "question": b.question,
                "answer": b.answer_text, "followUpQuestion": b.follow_up_question,
                "followUpAnswer": b.follow_up_answer}

    def find_resume_passages(keyword: str) -> dict:
        """자소서에서 키워드가 들어 있는 문장을 최대 3개 찾는다. 답변을 자소서 내용과 연결할 때 쓴다.

        Args:
            keyword: 찾을 단어 (1~30자)
        """
        if (limited := usage.take("find_resume_passages")) is not None:
            return limited
        word = _normalize(keyword or "")
        if not word:
            return {"error": "EMPTY_KEYWORD"}
        if len(word) > KEYWORD_MAX_CHARS:
            return {"error": "KEYWORD_TOO_LONG", "maxChars": KEYWORD_MAX_CHARS}
        sentences = [_normalize(s) for s in _SENTENCE_SPLIT.split(context.resume_text) if s.strip()]
        hits = [s[:PASSAGE_MAX_CHARS] for s in sentences if word.lower() in s.lower()]
        return {"keyword": word, "passages": hits[:RESUME_PASSAGE_LIMIT], "found": len(hits)}

    return [get_confirmed_scores, get_delivery_metrics, get_answer_text, find_resume_passages]


# ---------------------------------------------------------------- 출력


def _sentence(value: str) -> str:
    value = value.strip()
    if not TEXT_MIN <= len(value) <= TEXT_MAX:
        raise ValueError("length")
    if any(word in value for word in settings.FEEDBACK_BANNED_WORDS):
        raise ValueError("banned word")  # 합격·확률 같은 표현 (제품 원칙 4)
    return value


class FeedbackItem(_LLMOutputModel):
    question_id: str
    strengths: list[str] = Field(min_length=1, max_length=FEEDBACK_LIST_MAX)
    improvements: list[str] = Field(min_length=1, max_length=FEEDBACK_LIST_MAX)
    direction: str
    comment: str

    @field_validator("strengths", "improvements", mode="before")
    @classmethod
    def _keep_first(cls, values):
        # 모델이 3개 이상 써도 실패시키지 않고 앞의 2개만 남긴다. 남긴 것만 아래에서 검사한다
        return values[:FEEDBACK_LIST_MAX] if isinstance(values, list) else values

    @field_validator("strengths", "improvements")
    @classmethod
    def _sentences(cls, values: list[str]) -> list[str]:
        return [_sentence(v) for v in values]

    @field_validator("direction", "comment")
    @classmethod
    def _one(cls, value: str) -> str:
        return _sentence(value)


class FeedbackOutput(_LLMOutputModel):
    """C-2 출력. 점수 필드가 없다 (점수를 바꿀 수 없게)."""

    questions: list[FeedbackItem]

    @model_validator(mode="after")
    def _unique(self) -> "FeedbackOutput":
        ids = [q.question_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate questionId")
        return self

    def by_question(self) -> dict[str, FeedbackItem]:
        return {q.question_id: q for q in self.questions}


# ---------------------------------------------------------------- 공개 함수


def write_feedback(context: FeedbackContext, *, llm=None) -> FeedbackOutput:
    if not context.bundles:
        raise ValueError("no evaluable bundle")
    started = time.monotonic()
    client = llm if llm is not None else llm_module.default_client()
    usage = ToolUsage(settings.FEEDBACK_MAX_TOOL_CALLS)
    tools = make_feedback_tools(context, usage)
    expected = set(context.question_ids)

    def check(output: FeedbackOutput) -> None:
        if {q.question_id for q in output.questions} != expected:
            raise ValueError("questionId mismatch")

    try:
        return llm_module.call_json_with_tools(
            client,
            system_prompt=prompting.eval_system_prompt(),
            user_prompt=prompting.feedback_prompt([(b.question_id, b.question_type, b.question)
                                                   for b in context.bundles]),
            tools=tools,
            limits={"turns": settings.FEEDBACK_MAX_TURNS, "total_tokens": settings.FEEDBACK_MAX_TOTAL_TOKENS},
            schema=FeedbackOutput, stage=STAGE, check=check,
        )
    finally:
        # 툴 이름과 횟수만 남긴다. 툴 입력·결과(답변 원문)는 남기지 않는다
        logger.info("stage=%s toolCalls=%s totalToolCalls=%d durationMs=%d", STAGE, usage.summary(), usage.total,
                    int((time.monotonic() - started) * 1000))
