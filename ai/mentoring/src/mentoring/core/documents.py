"""문서 등록·조회 (Requirement 4 기준 4~8). PDF 업로드(Requirement 3·5)는 다음 작업이다."""
from ..errors import document_not_found, invalid_input
from ..models import (
    DocumentLatest,
    DocumentSource,
    DocumentVersion,
    DocumentView,
    ExtractionStatus,
    Task,
    TaskStatus,
    TaskType,
    TextDocumentRequest,
)
from . import tasks
from .idempotency import run_idempotent
from .logs import log_event, user_hash


def text_key(deps, user_id: str, document_id: str, version: int) -> str:
    """S3 키는 서버만 만든다. 요청으로 받은 키는 쓰지 않는다 (Requirement 2 기준 4, db-schema §7)."""
    return f"users/{deps.hash_user_id(user_id)}/documents/{document_id}/v{version}/extracted.txt"


def check_id(value: str | None, field: str) -> None:
    """ID에 `#`이 들어가면 400 (docs/api.md §2)."""
    if value is not None and (not value.strip() or "#" in value or len(value) > 200):
        raise invalid_input("ID 형식이 올바르지 않아요.", field=field)


def create_text_document(deps, user_id: str, request: TextDocumentRequest, idempotency_key: str | None = None) -> dict:
    """텍스트로 받은 이력서를 저장하고 역량 추출 작업을 보낸다. 202 응답 본문을 돌려준다.
    텍스트 입력은 추출 단계를 건너뛰어 EXTRACTED에서 시작한다 (A F-01 "상태 전이")."""
    limits = deps.config.document
    check_id(request.workspace_id, "workspaceId")
    if request.title is not None and len(request.title) > limits.title_max_chars:
        raise invalid_input("제목이 너무 길어요.", field="title", maxChars=limits.title_max_chars)
    normalized = deps.text.normalize(request.text)
    if not limits.text_min_chars <= len(normalized) <= limits.text_max_chars:
        raise invalid_input(f"이력서 텍스트는 {limits.text_min_chars:,}자 이상 {limits.text_max_chars:,}자 이하로 "
                            "입력해 주세요.", field="text", minChars=limits.text_min_chars,
                            maxChars=limits.text_max_chars, length=len(normalized))

    payload = {"text": normalized, "documentType": request.document_type.value, "title": request.title,
               "workspaceId": request.workspace_id}

    def create() -> dict:
        now = deps.now_iso()
        document_id = deps.new_id("doc")
        task_id = deps.new_id("task")
        key = text_key(deps, user_id, document_id, 1)
        deps.objects.put_text(key, normalized)
        version = DocumentVersion(
            document_id=document_id, version=1, owner_user_id=user_id, document_type=request.document_type,
            source=DocumentSource.TEXT, title=request.title, workspace_id=request.workspace_id, text_key=key,
            char_count=len(normalized), page_count=1, page_starts=[0],
            extraction_status=ExtractionStatus.EXTRACTED, task_id=task_id, created_at=now, updated_at=now)
        task = Task(task_id=task_id, task_type=TaskType.PROFILE_EXTRACT, status=TaskStatus.PENDING,
                    owner_user_id=user_id, resource_id=document_id, resource_version=1,
                    created_at=now, updated_at=now)
        deps.users.create_document(DocumentLatest.of(version, now), version)
        deps.users.create_task(task)
        deps.tasks.dispatch(tasks.build_message(task))
        log_event("document.created", userHash=user_hash(deps, user_id), taskId=task_id,
                  taskType=task.task_type.value, feature="profile", stage="EXTRACTED",
                  counts={"chars": len(normalized)})
        return {"documentId": document_id, "version": 1, "taskId": task_id,
                "status": TaskStatus.PENDING.value, "extractionStatus": ExtractionStatus.EXTRACTED.value}

    return run_idempotent(deps, user_id, idempotency_key, payload, create)


def get_document(deps, user_id: str, document_id: str) -> DocumentView:
    check_id(document_id, "documentId")
    latest = deps.users.get_document_latest(user_id, document_id)
    if latest is None or latest.owner_user_id != user_id:
        raise document_not_found()
    version = deps.users.get_document_version(user_id, document_id, latest.latest_version)
    if version is None:
        raise document_not_found()
    task = deps.users.get_task(user_id, version.task_id) if version.task_id else None
    return DocumentView(
        document_id=version.document_id, document_type=version.document_type, title=version.title,
        version=version.version, extraction_status=version.extraction_status, char_count=version.char_count,
        page_count=version.page_count, task_id=version.task_id, task_status=task.status.value if task else None,
        error_code=version.error_code, review_reason=version.review_reason,
        created_at=latest.created_at, updated_at=version.updated_at)


def set_document_status(deps, user_id: str, document_id: str, version_number: int, status: ExtractionStatus, *,
                        error_code: str | None = None, review_reason: str | None = None) -> None:
    latest = deps.users.get_document_latest(user_id, document_id)
    version = deps.users.get_document_version(user_id, document_id, version_number)
    if latest is None or version is None:
        return
    now = deps.now_iso()
    version = version.model_copy(update={"extraction_status": status, "error_code": error_code,
                                         "review_reason": review_reason, "updated_at": now})
    if latest.latest_version == version_number:
        latest = latest.model_copy(update={"extraction_status": status, "updated_at": now})
    deps.users.save_document(latest, version)
