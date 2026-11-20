"""PDF 업로드 (Requirement 3, 4 기준 1~3, 5, 개발계획서1 F-01 처리 1~6단계, §6.2).

흐름: 업로드 URL 발급(PENDING) → 브라우저가 S3에 바로 PUT → 업로드 완료(크기·형식 확인, UPLOADED)
     → DOCUMENT_EXTRACT 작업(EXTRACTING → EXTRACTED) → PROFILE_EXTRACT 작업(역량 추출, `core/extraction.py`)

업로드 완료 전에 사용자가 떠나도 남지 않게 한다 (고아 정리):
- 브라우저는 `pending/` 아래 임시 키에 올린다. 버킷 수명 주기가 1일 뒤 지운다 (infra/setup-data.sh)
- PENDING 문서 기록에는 `expiresAt`을 넣어 DynamoDB TTL이 지운다 (`upload.pendingTtlHours`)
- 업로드 완료 때 원본을 `users/...` 정식 키로 복사하고 `expiresAt`을 뺀 뒤, 임시 키를 지운다

- presigned URL은 응답에만 넣는다. 멱등 결과·DynamoDB·로그에 남기지 않고, 같은 요청이 다시 오면 새로 서명한다
- S3 키는 서버가 만든다. 요청으로 받은 키는 쓰지 않는다
- 작업 ID는 문서·버전으로 정해서 업로드 완료가 두 번 와도 작업이 하나만 생긴다
"""
from datetime import timedelta

from ..errors import MentoringError, document_not_found, invalid_input, not_implemented
from ..models import (
    DocumentLatest,
    DocumentSource,
    DocumentVersion,
    ExtractionStatus,
    Task,
    TaskStatus,
    TaskType,
    UploadUrlRequest,
)
from ..ports import AlreadyExists
from . import tasks
from .documents import check_id, set_document_status, text_key
from .extraction import ExtractionOutcome
from .idempotency import run_idempotent
from .logs import log_event, user_hash
from .metrics import emit_metric

REVIEW_TOO_LITTLE_TEXT = "TOO_LITTLE_TEXT"


def original_key(deps, user_id: str, document_id: str, version: int) -> str:
    return f"users/{deps.hash_user_id(user_id)}/documents/{document_id}/v{version}/original.pdf"


PENDING_PREFIX = "pending/"


def pending_key(deps, user_id: str, document_id: str, version: int) -> str:
    """업로드 완료 전 임시 키. 버킷 수명 주기 규칙이 이 접두사만 지운다."""
    return PENDING_PREFIX + original_key(deps, user_id, document_id, version)


def _file_too_large(message: str, **details) -> MentoringError:
    return MentoringError(413, "FILE_TOO_LARGE", message, False, details)


# ---------------------------------------------------------------- 업로드 URL
def create_upload_url(deps, user_id: str, request: UploadUrlRequest, idempotency_key: str | None = None) -> dict:
    cfg = deps.config.upload
    file_name = request.file_name.strip()
    if not file_name or len(file_name) > cfg.file_name_max_chars:
        raise invalid_input("파일 이름이 올바르지 않아요.", field="fileName", maxChars=cfg.file_name_max_chars)
    content_type = request.content_type.split(";")[0].strip().lower()
    if content_type not in cfg.allowed_content_types:
        raise invalid_input("PDF 파일만 올릴 수 있어요.", field="contentType", allowed=cfg.allowed_content_types)
    if request.size_bytes <= 0:
        raise invalid_input("파일 크기가 올바르지 않아요.", field="sizeBytes")
    if request.size_bytes > cfg.max_bytes:
        raise _file_too_large(f"{cfg.max_bytes // (1024 * 1024)}MB 이하 파일만 올릴 수 있어요.", maxBytes=cfg.max_bytes)
    check_id(request.workspace_id, "workspaceId")

    payload = {"fileName": file_name, "contentType": content_type, "sizeBytes": request.size_bytes,
               "documentType": request.document_type.value, "workspaceId": request.workspace_id}

    def create() -> dict:
        now = deps.now_iso()
        expires_at = int((deps.now() + timedelta(hours=cfg.pending_ttl_hours)).timestamp())
        document_id = deps.new_id("doc")
        version = DocumentVersion(
            document_id=document_id, version=1, owner_user_id=user_id, document_type=request.document_type,
            source=DocumentSource.UPLOAD, title=file_name, file_name=file_name, workspace_id=request.workspace_id,
            original_key=pending_key(deps, user_id, document_id, 1), content_type=content_type,
            size_bytes=request.size_bytes, extraction_status=ExtractionStatus.PENDING, expires_at=expires_at,
            created_at=now, updated_at=now)
        deps.users.create_document(DocumentLatest.of(version, now), version)
        log_event("document.upload_url", userHash=user_hash(deps, user_id), feature="profile",
                  stage=ExtractionStatus.PENDING.value)
        return {"documentId": document_id, "version": 1, "status": ExtractionStatus.PENDING.value}

    result = run_idempotent(deps, user_id, idempotency_key, payload, create)
    version = deps.users.get_document_version(user_id, result["documentId"], result["version"])
    if version is None:  # 멱등 결과는 남았지만 PENDING 기록은 TTL로 지워진 경우
        raise document_not_found()
    url = deps.objects.presign_put(version.original_key, content_type=version.content_type,
                                   size_bytes=version.size_bytes, expires_in=cfg.presign_expires_seconds)
    return {**result, "uploadUrl": url, "expiresInSeconds": cfg.presign_expires_seconds}


# ---------------------------------------------------------------- 업로드 완료
def complete_upload(deps, user_id: str, document_id: str) -> dict:
    check_id(document_id, "documentId")
    latest = deps.users.get_document_latest(user_id, document_id)
    if latest is None or latest.owner_user_id != user_id:
        raise document_not_found()
    version = deps.users.get_document_version(user_id, document_id, latest.latest_version)
    if version is None:
        raise document_not_found()
    if version.source != DocumentSource.UPLOAD:
        raise invalid_input("파일 업로드로 만든 문서가 아니에요.", field="documentId")
    if version.extraction_status != ExtractionStatus.PENDING:  # 두 번째 완료 요청은 처음 결과를 돌려준다
        task = deps.users.get_task(user_id, version.task_id) if version.task_id else None
        return {"documentId": document_id, "version": version.version, "taskId": version.task_id,
                "status": task.status.value if task else None, "extractionStatus": version.extraction_status.value}
    if version.expires_at is not None and deps.now().timestamp() >= version.expires_at:
        # TTL이 기록을 실제로 지우기 전까지 시간이 걸려서, 지난 기록은 여기서 막는다
        raise invalid_input("업로드할 수 있는 시간이 지났어요. 파일을 다시 올려 주세요.", field="documentId")
    if deps.extractor is None:
        raise not_implemented()

    staged_key = version.original_key
    info = deps.objects.head(staged_key)
    if info is None:
        raise invalid_input("업로드된 파일을 찾을 수 없어요. 다시 올려 주세요.", field="documentId")
    stored_type = (info.content_type or "").split(";")[0].strip().lower()
    if info.size_bytes != version.size_bytes or stored_type != version.content_type:
        # ETag만 믿지 않고 발급 때 값과 크기·형식을 비교한다 (개발계획서1 §6.2)
        raise invalid_input("업로드된 파일이 요청한 형식이나 크기와 달라요. 다시 올려 주세요.", field="documentId")

    # 정식 키로 옮긴다. 기록을 바꾸기 전에 복사해서, 중간에 실패해도 다시 완료를 부르면 이어서 된다.
    # 이 변경 전에 발급한 문서는 이미 정식 키라 복사하지 않는다
    final_key = original_key(deps, user_id, document_id, version.version)
    if staged_key != final_key:
        deps.objects.copy(staged_key, final_key)

    now = deps.now_iso()
    task = Task(task_id=f"task-{document_id}-v{version.version}-extract", task_type=TaskType.DOCUMENT_EXTRACT,
                status=TaskStatus.PENDING, owner_user_id=user_id, resource_id=document_id,
                resource_version=version.version, created_at=now, updated_at=now)
    try:
        deps.users.create_task(task)
        created = True
    except AlreadyExists:
        created = False
    version = version.model_copy(update={"extraction_status": ExtractionStatus.UPLOADED, "task_id": task.task_id,
                                         "original_key": final_key, "expires_at": None, "updated_at": now})
    deps.users.save_document(latest.model_copy(update={"extraction_status": ExtractionStatus.UPLOADED,
                                                       "task_id": task.task_id, "expires_at": None,
                                                       "updated_at": now}), version)
    if created:
        deps.tasks.dispatch(tasks.build_message(task))
    if staged_key != final_key:
        try:
            deps.objects.delete(staged_key)
        except Exception:  # noqa: BLE001 - 남아도 수명 주기 규칙이 1일 뒤 지우므로 완료는 실패시키지 않는다
            log_event("document.pending_cleanup_failed", userHash=user_hash(deps, user_id), feature="profile",
                      stage=ExtractionStatus.UPLOADED.value)
    log_event("document.uploaded", userHash=user_hash(deps, user_id), taskId=task.task_id,
              taskType=task.task_type.value, feature="profile", stage=ExtractionStatus.UPLOADED.value)
    return {"documentId": document_id, "version": version.version, "taskId": task.task_id,
            "status": TaskStatus.PENDING.value, "extractionStatus": ExtractionStatus.UPLOADED.value}


# ---------------------------------------------------------------- 텍스트 추출 작업
def run_document_extraction(deps, task: Task) -> ExtractionOutcome:
    uid = task.owner_user_id
    version = deps.users.get_document_version(uid, task.resource_id, task.resource_version)
    if version is None or version.owner_user_id != uid or version.original_key is None:
        raise document_not_found()
    if deps.extractor is None:
        raise not_implemented()
    set_document_status(deps, uid, version.document_id, version.version, ExtractionStatus.EXTRACTING)
    data = deps.objects.get_bytes(version.original_key)
    if data is None:
        raise MentoringError(500, "INTERNAL_ERROR", "업로드된 파일을 읽지 못했어요.", True)

    try:
        result = deps.extractor.extract(data, version.original_key)
    except MentoringError:
        raise
    except Exception as error:  # noqa: BLE001 - #41 ExtractError(code, message, retryable)를 공통 오류로 바꾼다
        code = getattr(error, "code", None)
        if code is None:
            raise
        emit_metric(deps, "DocumentParseFailure", 1, feature="profile")
        if code == "DOCUMENT_UNREADABLE":  # 손상·암호화 PDF (Requirement 5 기준 5)
            raise MentoringError(422, code, "문서를 읽을 수 없어요. 텍스트로 직접 입력해 주세요.", False) from None
        raise MentoringError(503, "AWS_SERVICE_ERROR", "문서 글자를 읽지 못했어요. 잠시 후 다시 시도하거나 텍스트로 "
                             "직접 입력해 주세요.", bool(getattr(error, "retryable", True))) from None

    extracted = getattr(result, "extracted", None)
    limits = deps.config.document
    if result.status != "EXTRACTED" or extracted is None or len(extracted.text) < limits.text_min_chars:
        # 텍스트가 부족하면 사용자에게 직접 입력을 안내한다 (Requirement 5 기준 6)
        emit_metric(deps, "DocumentParseFailure", 1, feature="profile")
        reason = getattr(result, "reason", None) or REVIEW_TOO_LITTLE_TEXT
        set_document_status(deps, uid, version.document_id, version.version, ExtractionStatus.REQUIRES_USER_REVIEW,
                            review_reason=reason)
        return ExtractionOutcome(status=TaskStatus.REQUIRES_USER_REVIEW, result_id=version.document_id,
                                 review_reason=reason, retry_count=0)
    if extracted.page_count > deps.config.upload.max_pages:
        raise _file_too_large(f"{deps.config.upload.max_pages}쪽 이하 문서만 분석할 수 있어요.",
                              maxPages=deps.config.upload.max_pages)
    if len(extracted.text) > limits.text_max_chars:
        raise _file_too_large(f"문서 글자 수가 {limits.text_max_chars:,}자를 넘어요.", maxChars=limits.text_max_chars)

    now = deps.now_iso()
    key = text_key(deps, uid, version.document_id, version.version)
    deps.objects.put_text(key, extracted.text)  # 정규화 텍스트. 근거 위치는 이 텍스트 기준이다
    profile_task = Task(task_id=f"task-{version.document_id}-v{version.version}-profile",
                        task_type=TaskType.PROFILE_EXTRACT, status=TaskStatus.PENDING, owner_user_id=uid,
                        resource_id=version.document_id, resource_version=version.version,
                        created_at=now, updated_at=now)
    try:
        deps.users.create_task(profile_task)
        created = True
    except AlreadyExists:
        created = False
    latest = deps.users.get_document_latest(uid, version.document_id)
    version = version.model_copy(update={
        "text_key": key, "char_count": len(extracted.text), "page_count": extracted.page_count,
        "page_starts": list(extracted.page_starts), "extraction_method": extracted.method,
        "extraction_status": ExtractionStatus.EXTRACTED, "task_id": profile_task.task_id, "updated_at": now})
    deps.users.save_document(latest.model_copy(update={"extraction_status": ExtractionStatus.EXTRACTED,
                                                       "task_id": profile_task.task_id, "updated_at": now}), version)
    if created:
        deps.tasks.dispatch(tasks.build_message(profile_task))
    log_event("document.extracted", userHash=user_hash(deps, uid), taskId=task.task_id, feature="profile",
              stage=ExtractionStatus.EXTRACTED.value, validation=extracted.method,
              counts={"pages": extracted.page_count, "chars": len(extracted.text)})
    return ExtractionOutcome(status=TaskStatus.COMPLETED, result_id=version.document_id, review_reason=None,
                             retry_count=0)
