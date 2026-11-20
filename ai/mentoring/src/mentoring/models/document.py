"""문서와 문서 버전 (db-schema §2.1 `DOC_LATEST#{docId}`, `DOC#{docId}#V#{n}`).
원문·추출 텍스트는 S3에만 두고 여기에는 키와 메타데이터만 둔다 (db-schema §0 원칙 7).
"""
from pydantic import Field

from .base import MentoringModel
from .enums import DocumentSource, DocumentType, ExtractionStatus


class DocumentVersion(MentoringModel):
    document_id: str
    version: int = Field(ge=1)
    owner_user_id: str
    document_type: DocumentType
    source: DocumentSource
    title: str | None = None
    workspace_id: str | None = None
    text_key: str | None = None             # S3 개인 문서 버킷의 정규화 텍스트 키
    char_count: int | None = None
    page_count: int | None = None
    page_starts: list[int] = Field(default_factory=list)  # 페이지마다 정규화 텍스트에서 시작하는 위치
    extraction_status: ExtractionStatus
    task_id: str | None = None
    error_code: str | None = None
    review_reason: str | None = None
    created_at: str
    updated_at: str


class DocumentLatest(MentoringModel):
    """목록·조회용 최신 포인터. 최신 버전의 상태를 복사해 둔다."""
    document_id: str
    owner_user_id: str
    document_type: DocumentType
    title: str | None = None
    latest_version: int = Field(ge=1)
    extraction_status: ExtractionStatus
    task_id: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, version: DocumentVersion, created_at: str) -> "DocumentLatest":
        return cls(document_id=version.document_id, owner_user_id=version.owner_user_id,
                   document_type=version.document_type, title=version.title, latest_version=version.version,
                   extraction_status=version.extraction_status, task_id=version.task_id,
                   created_at=created_at, updated_at=version.updated_at)


class DocumentView(MentoringModel):
    """GET /documents/{documentId} 응답. 원문 URL과 추출 텍스트 본문은 넣지 않는다 (Requirement 4 기준 8)."""
    document_id: str
    document_type: DocumentType
    title: str | None = None
    version: int
    extraction_status: ExtractionStatus
    char_count: int | None = None
    page_count: int | None = None
    task_id: str | None = None
    task_status: str | None = None
    error_code: str | None = None
    review_reason: str | None = None
    created_at: str
    updated_at: str
