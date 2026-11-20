"""채팅 Agent 데이터 계약 (개발계획서4 §7·§8). Python 속성은 snake_case, JSON 키는 카멜 표기 (D-02)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SupModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def to_api(self) -> dict:
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


class Role(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"  # 사용자가 답을 만드는 중에 멈췄다. 늦게 나온 결과는 저장하지 않는다


class CardType(StrEnum):
    POSTING = "POSTING"
    POLICY = "POLICY"


class ActionType(StrEnum):
    SAVE_CONDITIONS = "SAVE_CONDITIONS"            # 조건 저장 묻기. 누르면 화면이 PUT /api/v1/me/profile
    SUGGEST_INTERVIEW = "SUGGEST_INTERVIEW"        # "이 직무로 모의면접 체험하기" 칩
    START_INTERVIEW = "START_INTERVIEW"            # 저장된 자소서로 면접 화면 이동
    REQUEST_COVER_LETTER = "REQUEST_COVER_LETTER"  # 자소서 입력 받기 → 면접 화면 이동
    CONDITIONS_SAVED = "CONDITIONS_SAVED"          # 사용자가 채팅으로 저장을 승낙해 저장 도구가 저장함
    # 지난 대화를 읽기 위해서만 남긴다. 진단 도구를 지워(#155) 새로 만들지 않고, 화면도 그리지 않는다
    OPEN_DIAGNOSIS = "OPEN_DIAGNOSIS"


# ---------------------------------------------------------------- 요청
class Attachment(SupModel):
    document_id: str = Field(min_length=1, max_length=200)


class ChatRequest(SupModel):
    session_id: str | None = Field(default=None, max_length=100)
    message: str
    attachments: list[Attachment] = Field(default_factory=list)


# ---------------------------------------------------------------- 모델 답 (고정 스키마)
class ChatReply(BaseModel):
    """Agent의 마지막 답. 카드·숫자는 여기 넣지 않는다. 코드가 도구 결과로 만든다."""

    reply: str = Field(description="사용자에게 보여 줄 한국어 답. 도구 결과에 있는 사실만 말한다")
    follow_ups: list[str] = Field(default_factory=list,
                                  description="사용자가 이어서 누를 짧은 질문 (최대 3개, 각 40자 이하)")


# ---------------------------------------------------------------- 저장·응답
class ToolCall(SupModel):
    name: str
    ok: bool
    duration_ms: int


class ChatCard(SupModel):
    type: CardType
    posting: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None


class ChatAction(SupModel):
    type: ActionType
    job: str | None = None
    document_id: str | None = None
    title: str | None = None
    conditions: list[str] = Field(default_factory=list)
    profile_patch: dict[str, Any] | None = None
    min_chars: int | None = None
    max_chars: int | None = None
    # 지난 대화의 OPEN_DIAGNOSIS 행동을 읽을 때만 채워진다 (#155에서 진단 도구 삭제)
    analysis_id: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    target_ncs_code: str | None = None
    # START_INTERVIEW·REQUEST_COVER_LETTER: "이 공고로" 면접할 때 그 공고. 면접 화면이 공고 올리기를 끄고 이 공고로 질문을 만든다 (#167)
    job_posting_id: str | None = None
    posting_title: str | None = None
    posting_organization: str | None = None


class ErrorInfo(SupModel):
    code: str
    message: str
    retryable: bool = False


class ChatMessage(SupModel):
    session_id: str
    message_id: str
    owner_user_id: str
    role: Role
    content: str = ""
    status: MessageStatus = MessageStatus.COMPLETED
    follow_ups: list[str] = Field(default_factory=list)
    cards: list[ChatCard] = Field(default_factory=list)
    actions: list[ChatAction] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    notice: str | None = None
    data_as_of: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    config_version: str | None = None
    error: ErrorInfo | None = None
    created_at: str
    updated_at: str

    def view(self) -> dict:
        """화면 응답. 소유자·내부 기록(도구 호출)은 뺀다. 사용자 말은 content, Agent 답은 reply로 준다."""
        body = self.to_api()
        for key in ("ownerUserId", "toolCalls", "modelId", "promptVersion", "configVersion"):
            body.pop(key, None)
        if self.role == Role.ASSISTANT:
            body["reply"] = body.pop("content", "")
        return body


class ChatSession(SupModel):
    session_id: str
    owner_user_id: str
    title: str
    pending_message_id: str | None = None
    pending_since: str | None = None
    message_count: int = 0
    pinned: bool = False  # 대화 목록 위에 고정
    created_at: str
    last_message_at: str

    def view(self) -> dict:
        body = self.to_api()
        body.pop("ownerUserId", None)
        body.pop("pendingSince", None)
        return body


class DocumentInfo(SupModel):
    """A 문서 요약 (`DOC_LATEST#`). 원문·키는 담지 않는다."""

    document_id: str
    document_type: str  # RESUME, COVER_LETTER, CAREER_HISTORY, PORTFOLIO
    title: str | None = None
    status: str          # A ExtractionStatus
    has_text: bool = False
    updated_at: str | None = None
