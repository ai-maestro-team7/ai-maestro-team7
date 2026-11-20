"""면접 함수 데이터 계약 (design §4, C ★ 주요 데이터 형식).

- JSON 키는 카멜 표기, Python 속성은 snake_case. 밖으로 줄 때는 dump()를 쓴다.
- 함수 입력·Session·Answer_Result는 모르는 키를 거절한다 (계약 어긋남을 바로 드러내기 위해).
- LLM 출력은 모르는 키를 무시한다 (모델이 덧붙인 키 때문에 재시도하지 않게).
- profile은 계약 패키지 team07_contracts.CareerProfileSummary로 검사한다 (#26, D-12, D-18).
"""

import logging
from typing import Any, Literal, TypeVar

from pydantic import (BaseModel, ConfigDict, Field, FiniteFloat, PrivateAttr, StrictBool, ValidationError,
                      field_validator, model_validator)
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
# 답변 기록에 남기는 꼬리질문 판단 결과 (follow-up 결정 6). JUDGE_FAILED = 판단 출력이 실패해 꼬리질문 없이 진행
FollowUpCheck = Literal["ABSTRACT", "INCONSISTENT", "SUFFICIENT", "JUDGE_FAILED"]
DeliveryReason = Literal["TOO_SHORT", "NON_HANGUL_HEAVY"]

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


# ---------------------------------------------------------------- 카메라 (4차, camera design §6.1)

FrameType = Literal["CALIBRATION", "ANSWER"]


class Angle(_CamelModel):
    """좌우(yaw)·위아래(pitch) 각도(도). DynamoDB를 거치면 정수 값은 int가 된다."""

    yaw: FiniteFloat
    pitch: FiniteFloat


class EyesOpen(_CamelModel):
    value: bool
    confidence: FiniteFloat = Field(ge=0, le=100)


class Baseline(_CamelModel):
    """compute_baseline 결과. 백엔드가 session.baseline에 그대로 넣는다 (camera 결정 6)."""

    gaze: Angle
    head: Angle


class FaceResult(BaseModel):
    """analyze_face 결과 (★ 형식). compute_baseline 입력 검사에 쓴다.

    모르는 키는 무시한다. 백엔드가 저장 키를 더해도 캡처가 빠지지 않게 하려는 것이다 (camera 결정 5).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    valid: StrictBool
    reason: str | None = None
    gaze: Angle | None = None
    head: Angle | None = None
    eyes_open: EyesOpen | None = None

    @model_validator(mode="after")
    def _angles_when_valid(self) -> "FaceResult":
        if self.valid and (self.gaze is None or self.head is None):
            raise ValueError("valid result needs gaze and head")
        return self


class Frame(FaceResult):
    """백엔드가 FaceResult에 캡처 정보를 붙여 저장한 값 (C ★ frames)."""

    type: FrameType
    question_id: str | None = None
    answer_id: str | None = None
    captured_at: str | None = None
    accepted: StrictBool


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


class DeliveryMetrics(_CamelModel):
    """답변 하나의 전달력 측정값 (voice design §7). 점수가 아니다 (점수 환산은 3차).

    수치는 실수지만 백엔드가 DynamoDB를 거쳐 돌려줄 때 정수 값은 int가 된다(300.0 → 300).
    float 필드는 엄격 모드가 아니라서 int도 받는다 (voice 결정 6).
    """

    answer_sec: float = Field(ge=0)
    speech_rate: float | None = Field(ge=0)
    speech_rate_reason: DeliveryReason | None
    long_pause_count: int | None = Field(ge=0)
    long_pause_per_min: float | None = Field(ge=0)
    long_pause_reason: DeliveryReason | None

    @model_validator(mode="after")
    def _value_or_reason(self) -> "DeliveryMetrics":
        # 항목마다 값과 미측정 사유 중 정확히 하나만 있다
        if (self.speech_rate is None) == (self.speech_rate_reason is None):
            raise ValueError("speech rate needs a value or a reason")
        pause_missing = self.long_pause_count is None, self.long_pause_per_min is None
        if pause_missing[0] != pause_missing[1]:
            raise ValueError("long pause count and per minute go together")
        if pause_missing[0] == (self.long_pause_reason is None):
            raise ValueError("long pause needs a value or a reason")
        return self


class AnswerRecord(_CamelModel):
    answer_id: str
    question_id: str
    is_follow_up: bool
    question: str
    answer_text: str | None
    evaluable: bool
    reason: UnevaluableReason | None
    time_limit_reached: bool
    delivery: DeliveryMetrics | None = None  # 2차. 1차 Session에는 키가 없다
    # #109. 꼬리질문을 판단한 기본 답변에만 값이 있다. 예전 Session에는 키가 없다. 리포트·lastAnswer에는 보이지 않는다
    follow_up_check: FollowUpCheck | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "AnswerRecord":
        if self.evaluable and (self.reason is not None or not (self.answer_text or "").strip()):
            raise ValueError("evaluable answer needs text and no reason")
        if not self.evaluable and self.reason is None:
            raise ValueError("unevaluable answer needs a reason")
        if not self.evaluable and self.delivery is not None:
            raise ValueError("unevaluable answer has no delivery metrics")
        if self.follow_up_check is not None and (self.is_follow_up or not self.evaluable):
            raise ValueError("follow-up check only on evaluable base answers")
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
    baseline: Baseline | None = None  # 백엔드가 compute_baseline 결과를 넣는다. None이면 태도 미측정

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
    """Prompt_B 출력. 꼬리질문은 목록으로 받고 첫 번째만 쓴다 (judge_follow_up).

    길이가 맞지 않는 후보(공백 정리 뒤 QUESTION_MIN 미만, FOLLOW_UP_QUESTION_MAX 초과)는 실패시키지 않고 버린다.
    남은 후보가 없는데 꼬리질문이 필요하다고 하면 출력 실패다 (follow-up 결정 7).
    """

    need_follow_up: bool
    reason: FollowUpReason
    follow_up_questions: list[str] = Field(default_factory=list)
    _dropped: int = PrivateAttr(default=0)  # 길이 때문에 버린 후보 수 (로그용, 빈 문자열은 세지 않음)

    @model_validator(mode="after")
    def _filter_and_require(self) -> "FollowUpOutput":
        kept, dropped = [], 0
        for value in self.follow_up_questions:
            value = value.strip()
            if not value:
                continue
            if not settings.QUESTION_MIN <= len(value) <= settings.FOLLOW_UP_QUESTION_MAX:
                dropped += 1
                continue
            kept.append(value)
        if self.need_follow_up and not kept:
            raise ValueError("follow-up question missing")
        self.follow_up_questions = kept if self.need_follow_up else []
        self._dropped = dropped
        return self

    @property
    def dropped_candidates(self) -> int:
        return self._dropped


# ---------------------------------------------------------------- 채점 (3차, report design §4·§5)

EvidenceType = Literal["quote", "missing"]
# 태도 미측정 사유 (camera 결정 3). 3차의 ATTITUDE_NOT_READY는 4차에서 없앴다
AttitudeReason = Literal["CAMERA_NOT_USED", "CALIBRATION_FAILED", "NOT_ENOUGH_FRAMES"]
AreaReason = Literal["CAMERA_NOT_USED", "CALIBRATION_FAILED", "NOT_ENOUGH_FRAMES", "NOT_ENOUGH_SPEECH"]


class QuestionFrontal(_CamelModel):
    """묶음(기본 질문 ID) 하나의 정면 응시 비율(%). 표시할 때 정수로 반올림한다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    question_id: str
    frontal_ratio: float = Field(ge=0, le=100)


class AttitudeResult(_CamelModel):
    """measure_attitude 결과 (camera design §6). score가 있으면 reason이 없고, 없으면 reason이 있다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    score: float | None = Field(ge=0, le=100)
    reason: AttitudeReason | None
    frontal_ratio: float | None = Field(ge=0, le=100)  # 모든 문항을 합친 비율
    used_frames: int = Field(ge=0)
    frontal_frames: int = Field(ge=0)
    by_question: tuple[QuestionFrontal, ...] = ()

    @model_validator(mode="after")
    def _one(self) -> "AttitudeResult":
        if (self.score is None) == (self.reason is None):
            raise ValueError("attitude needs a score or a reason")
        return self


class ContentItem(_CamelModel):
    """C-1 항목 하나. 점수는 1~5 정수, 근거는 답변 속 문장(quote) 또는 빠진 요소(missing)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    key: str
    score: int = Field(ge=1, le=5)
    evidence_type: EvidenceType
    evidence: str | None  # 대조에 실패한 인용은 None으로 지운다
    evidence_verified: bool


class ContentEvaluation(_CamelModel):
    """묶음 하나의 C-1 결과 (검증·근거 대조를 마친 값)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    question_id: str
    question_type: QuestionType
    items: tuple[ContentItem, ...]

    @property
    def raw_score(self) -> float:
        """항목 합계 ÷ 만점 × 100 (노션 6-①: 4개 × 5점 = 20)."""
        return sum(i.score for i in self.items) / (len(self.items) * 5) * 100


class AreaScore(_CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    score: int | None = Field(ge=0, le=100)
    not_measured_reason: AreaReason | None

    @model_validator(mode="after")
    def _one(self) -> "AreaScore":
        if (self.score is None) == (self.not_measured_reason is None):
            raise ValueError("area needs a score or a reason")
        return self


class Areas(_CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    content: AreaScore
    delivery: AreaScore
    attitude: AreaScore


class BundleScore(_CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    question_id: str
    content_score: int = Field(ge=0, le=100)
    delivery_score: float | None = Field(ge=0, le=100)  # 측정된 답변이 없으면 None


class ScoreResult(_CamelModel):
    """calculate_interview_scores 결과. 점수는 코드가 계산한 값이고 합격 확률이 아니다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

    total_score: int = Field(ge=0, le=100)
    grade: str
    weight_basis: str
    areas: Areas
    not_measured_messages: tuple[str, ...]
    evaluated_base_questions: int = Field(ge=1)
    bundles: tuple[BundleScore, ...]
    frontal_ratios: tuple[QuestionFrontal, ...] = ()  # 태도를 측정했을 때만. 리포트 metrics.frontalRatio용


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
