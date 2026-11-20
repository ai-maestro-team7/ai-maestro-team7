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


class CardType(StrEnum):
    POSTING = "POSTING"
    POLICY = "POLICY"


class ActionType(StrEnum):
    SAVE_CONDITIONS = "SAVE_CONDITIONS"            # 조건 저장 묻기. 누르면 화면이 PUT /api/v1/me/profile
    SUGGEST_INTERVIEW = "SUGGEST_INTERVIEW"        # "이 직무로 모의면접 체험하기" 칩
    START_INTERVIEW = "START_INTERVIEW"            # 저장된 자소서로 면접 화면 이동
    REQUEST_COVER_LETTER = "REQUEST_COVER_LETTER"  # 자소서 입력 받기 → 면접 화면 이동


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
