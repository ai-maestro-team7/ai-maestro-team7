"""면접 함수 데이터 계약 (design §4, C ★ 주요 데이터 형식).

- JSON 키는 카멜 표기, Python 속성은 snake_case. 밖으로 줄 때는 dump()를 쓴다.
- 함수 입력·Session·Answer_Result는 모르는 키를 거절한다 (계약 어긋남을 바로 드러내기 위해).
- LLM 출력은 모르는 키를 무시한다 (모델이 덧붙인 키 때문에 재시도하지 않게).
- profile은 계약 패키지 team07_contracts.CareerProfileSummary로 검사한다 (#26, D-12, D-18).
"""

import logging
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel
from team07_contracts import CareerProfileSummary

from . import settings
from .errors import INVALID_INPUT, InterviewError

logger = logging.getLogger("interview")

InterviewType = Literal["PERSONALITY", "JOB", "MIXED"]
QuestionType = Literal["experience", "knowledge", "situation"]
UnevaluableReason = Literal["NO_ANSWER", "TRANSCRIBE_FAILED"]
TranscriptionStatus = Literal["COMPLETED", "FAILED", "IN_PROGRESS"]
FollowUpReason = Literal["ABSTRACT", "INCONSISTENT", "SUFFICIENT"]

INVALID_INPUT_MESSAGE = "면접 정보를 확인할 수 없어요. 입력 내용을 확인해 주세요."


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _LLMOutputModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("blank")
    return value


def _normalize(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------- 함수 입력


class QuestionRequest(_CamelModel):
    """generate_questions 입력. start_interview도 같은 규칙을 쓴다 (Requirement 7 기준 2)."""

    job: str
    resume_text: str
    interview_type: InterviewType
    profile: CareerProfileSummary | None = None

    @field_validator("job")
    @classmethod
    def _job(cls, value: str) -> str:
        value = value.strip()
        if not settings.JOB_MIN <= len(value) <= settings.JOB_MAX:
            raise ValueError("length")
        return value

    @field_validator("resume_text")
    @classmethod
    def _resume(cls, value: str) -> str:
        # 백엔드 /start와 같은 기준으로 원문 길이를 잰다 (backend/interview_api.py h_start)
        if not settings.RESUME_MIN <= len(value) <= settings.RESUME_MAX:
            raise ValueError("length")
        return value


class StartInterviewInput(QuestionRequest):
    session_id: str
    camera_consent: StrictBool

    @field_validator("session_id")
    @classmethod
    def _session_id(cls, value: str) -> str:
        return _non_blank(value)


# ---------------------------------------------------------------- Session


class Question(_CamelModel):
    question_id: str = Field(pattern=r"^q\d+$")
    question_type: QuestionType
    question: str


class NextQuestion(_CamelModel):
    question_id: str = Field(pattern=r"^q\d+(-f)?$")
    answer_id: str = Field(pattern=r"^a-q\d+-[12]$")
    text: str
    is_follow_up: bool


class AnswerRecord(_CamelModel):
    answer_id: str
    question_id: str
    is_follow_up: bool
    question: str
    answer_text: str | None
    evaluable: bool
    reason: UnevaluableReason | None
    time_limit_reached: bool

    @model_validator(mode="after")
    def _consistent(self) -> "AnswerRecord":
        if self.evaluable and (self.reason is not None or not (self.answer_text or "").strip()):
            raise ValueError("evaluable answer needs text and no reason")
        if not self.evaluable and self.reason is None:
            raise ValueError("unevaluable answer needs a reason")
        return self


class Session(_CamelModel):
    session_id: str
    job: str
    interview_type: InterviewType
    camera_consent: bool
    resume_text: str
    profile: CareerProfileSummary | None = None
    scoring_version: str
    model_id: str
    prompt_version: str
    questions: list[Question]
    current_index: int = Field(ge=0)
    follow_up_used: bool
    current_question: NextQuestion | None
    answers: list[AnswerRecord]
    baseline: dict[str, Any] | None = None  # 백엔드가 compute_baseline 결과를 넣는다. 형식은 4차에서 정함

    # pydantic이 model_ 접두사를 예약어로 보지 않게 한다 (model_id 필드)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid",
                              protected_namespaces=())

    @model_validator(mode="after")
    def _shape(self) -> "Session":
        if len(self.questions) != settings.BASE_QUESTION_COUNT:
            raise ValueError("question count")
        if self.current_index > len(self.questions):
            raise ValueError("current index")
        return self


# ---------------------------------------------------------------- Answer_Result


class Word(_CamelModel):
    word: str
    start: float
    end: float


class Transcription(_CamelModel):
    status: TranscriptionStatus
    text: str | None = None
    words: list[Word] = Field(default_factory=list)


class AnswerResult(_CamelModel):
    answer_id: str
    time_limit_reached: bool = False
    transcription: Transcription

    @field_validator("answer_id")
    @classmethod
    def _answer_id(cls, value: str) -> str:
        return _non_blank(value)


# ---------------------------------------------------------------- LLM 출력


class GeneratedQuestion(_LLMOutputModel):
    question_type: QuestionType
    question: str

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        value = value.strip()
        if not settings.QUESTION_MIN <= len(value) <= settings.QUESTION_MAX:
            raise ValueError("length")
        return value


class QuestionsOutput(_LLMOutputModel):
    """Prompt_A 출력."""

    questions: list[GeneratedQuestion]

    @model_validator(mode="after")
    def _three_distinct(self) -> "QuestionsOutput":
        if len(self.questions) != settings.BASE_QUESTION_COUNT:
            raise ValueError("question count")
        texts = [_normalize(q.question) for q in self.questions]
        if len(set(texts)) != len(texts):
            raise ValueError("duplicate question")
        return self


class FollowUpOutput(_LLMOutputModel):
    """Prompt_B 출력. 꼬리질문은 목록으로 받고 첫 번째만 쓴다 (judge_follow_up)."""

    need_follow_up: bool
    reason: FollowUpReason
    follow_up_questions: list[str] = Field(default_factory=list)

    @field_validator("follow_up_questions")
    @classmethod
    def _items(cls, values: list[str]) -> list[str]:
        out = []
        for value in values:
            value = value.strip()
            if not value:
                continue
            if len(value) > settings.QUESTION_MAX or len(value) < settings.QUESTION_MIN:
                raise ValueError("length")
            out.append(value)
        return out

    @model_validator(mode="after")
    def _need_has_question(self) -> "FollowUpOutput":
        if self.need_follow_up and not self.follow_up_questions:
            raise ValueError("follow-up question missing")
        if not self.need_follow_up:
            self.follow_up_questions = []
        return self


# ---------------------------------------------------------------- 변환


M = TypeVar("M", bound=BaseModel)


def _loc(loc: tuple) -> str:
    return ".".join(str(part) for part in loc) or "(root)"


def parse_input(model: type[M], data: Any, *, stage: str) -> M:
    """입력을 검사한다. 실패하면 INVALID_INPUT. 로그에는 실패한 필드 이름만 남긴다 (Requirement 12)."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        fields = sorted({_loc(e["loc"]) for e in exc.errors(include_input=False, include_url=False)})
        logger.warning("stage=%s errorCode=%s fields=%s", stage, INVALID_INPUT, ",".join(fields))
        # 원래 예외에는 입력값이 들어 있을 수 있어 이어 붙이지 않는다
        raise InterviewError(INVALID_INPUT, INVALID_INPUT_MESSAGE) from None


def dump(model: BaseModel) -> dict[str, Any]:
    """카멜 키 JSON 값으로 바꾼다. 백엔드는 이 값을 그대로 저장한다."""
    return model.model_dump(by_alias=True, mode="json")
