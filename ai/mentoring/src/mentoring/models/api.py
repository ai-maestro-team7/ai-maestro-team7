"""REST 요청 본문 (개발계획서1 §6.1). 길이 한도는 설정에서 읽어 core에서 검사한다."""
from typing import Literal

from pydantic import Field

from .base import RequestModel
from .enums import ConfirmAction, DocumentType


class UploadUrlRequest(RequestModel):
    """POST /documents/upload-url (개발계획서1 §6.2)"""
    file_name: str
    content_type: str
    size_bytes: int
    document_type: DocumentType = DocumentType.RESUME
    workspace_id: str | None = None


class TextDocumentRequest(RequestModel):
    """POST /documents/text"""
    text: str
    document_type: DocumentType = DocumentType.RESUME
    title: str | None = None
    workspace_id: str | None = None


class ConfirmDecision(RequestModel):
    skill_id: str = Field(min_length=1)
    action: ConfirmAction
    name: str | None = None  # RENAME 일 때만


class ConfirmAddition(RequestModel):
    name: str


class ConfirmEntryDecision(RequestModel):
    """프로젝트·경험·자격 이름/확인 상태를 사용자 판단으로 고친다 (#196)."""
    group: Literal["PROJECT", "EXPERIENCE", "CERTIFICATE"]
    item_id: str = Field(min_length=1)
    action: Literal[ConfirmAction.CONFIRM, ConfirmAction.RENAME, ConfirmAction.DELETE]
    name: str | None = None


class ConfirmRequest(RequestModel):
    """POST /profiles/{profileId}/confirm. base_version이 최신이 아니면 409 (Requirement 7 기준 5)."""
    base_version: int = Field(ge=1)
    decisions: list[ConfirmDecision] = Field(default_factory=list)
    additions: list[ConfirmAddition] = Field(default_factory=list)
    entry_decisions: list[ConfirmEntryDecision] = Field(default_factory=list)
