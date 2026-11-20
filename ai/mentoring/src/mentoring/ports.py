"""A가 바깥에 기대는 것들의 인터페이스.
core는 이 인터페이스만 보고 짠다. 테스트는 `store/memory.py`와 `llm/mock.py`를 쓰고, AWS 구현(DynamoDB·S3·Bedrock·
Lambda 자기 호출)은 다음 작업에서 같은 인터페이스로 만든다 (Requirement 11 기준 1).
"""
from dataclasses import dataclass
from typing import Any, Protocol

from .models import CareerProfile, DocumentLatest, DocumentVersion, ProfilePointer, Task, TaskStatus


class AlreadyExists(Exception):
    """조건부 쓰기에서 같은 키가 이미 있을 때."""


class VersionConflict(Exception):
    """`latestVersion = :expected` 조건이 맞지 않을 때 (db-schema §0 원칙 6)."""


@dataclass
class IdemResult:
    """`IDEM#` 조건부 쓰기 결과 (D-31)."""
    state: str  # NEW(처음), REPLAY(같은 본문 재요청), CONFLICT(같은 키에 다른 본문)
    result: dict | None = None


class UserRepo(Protocol):
    """`team07-career-mentor`, PK = `USER#{userId}`. 모든 메서드는 user_id 범위 안에서만 읽고 쓴다. Scan은 쓰지 않는다."""

    # 문서 (DOC_LATEST#, DOC#..#V#)
    def create_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        """둘을 한 트랜잭션으로 쓴다. 같은 문서가 있으면 AlreadyExists."""
        ...

    def save_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        """상태 변경. 둘을 한 트랜잭션으로 덮어쓴다."""
        ...

    def get_document_latest(self, user_id: str, document_id: str) -> DocumentLatest | None: ...

    def get_document_version(self, user_id: str, document_id: str, version: int) -> DocumentVersion | None: ...

    # 역량 프로필 (PROFILE#LATEST, PROFILE#{id}#V#)
    def get_profile_pointer(self, user_id: str) -> ProfilePointer | None: ...

    def get_profile_version(self, user_id: str, profile_id: str, version: int) -> CareerProfile | None: ...

    def put_profile_version(self, profile: CareerProfile, *, expected_version: int | None) -> None:
        """새 버전과 포인터를 한 트랜잭션으로 쓴다. 포인터 버전이 expected_version과 다르면 VersionConflict.
        expected_version이 None이면 포인터가 없어야 한다."""
        ...

    # 작업 (TASK#)
    def create_task(self, task: Task) -> None: ...

    def get_task(self, user_id: str, task_id: str) -> Task | None: ...

    def update_task(self, task: Task, *, expected_status: TaskStatus) -> bool:
        """저장된 상태가 expected_status일 때만 바꾼다. 바꿨으면 True."""
        ...

    # 멱등 키 (IDEM#)
    def idem_begin(self, user_id: str, key: str, request_hash: str, expires_at: str) -> IdemResult: ...

    def idem_complete(self, user_id: str, key: str, result: dict) -> None: ...


class ObjectInfo(Protocol):
    """head() 결과. S3 구현(#61)은 `S3ObjectInfo`로 같은 필드를 준다."""
    size_bytes: int
    content_type: str | None


class ObjectStore(Protocol):
    """개인 문서 버킷 (`team07-career-docs-<계정ID>`). 키는 서버가 만든 것만 쓴다 (Requirement 2 기준 4).
    URL과 키는 로그·오류·DynamoDB 항목에 남기지 않는다 (Requirement 3 기준 6)."""

    def put_text(self, key: str, text: str) -> None: ...

    def get_text(self, key: str) -> str | None: ...

    def get_bytes(self, key: str) -> bytes | None: ...

    def presign_put(self, key: str, *, content_type: str, size_bytes: int, expires_in: int) -> str:
        """브라우저가 바로 올릴 PUT presigned URL. 형식과 크기를 서명에 넣는다 (Requirement 3 기준 3)."""
        ...

    def head(self, key: str) -> ObjectInfo | None: ...

    def copy(self, source_key: str, target_key: str) -> None:
        """같은 버킷 안에서 복사한다. 형식(Content-Type)도 그대로 옮긴다."""
        ...

    def delete(self, key: str) -> None: ...


class Llm(Protocol):
    """모델 호출. model_id는 결과에 기록한다 (Requirement 6 기준 9)."""
    model_id: str

    def invoke(self, system: str, user: str, *, max_tokens: int) -> str: ...


class TaskDispatcher(Protocol):
    """비동기 작업 보내기. 운영은 Lambda 비동기 자기 호출(D-19), 테스트는 대기열."""

    def dispatch(self, message: dict) -> None: ...


class DocumentExtractor(Protocol):
    """PDF → 정규화 텍스트 (Requirement 5). 구현은 `core/pdf_extractor.py`가 #41 `extract_document`를 감싼다.
    key는 OCR이 S3에서 직접 읽을 원본 PDF 위치다."""

    def extract(self, pdf_bytes: bytes, key: str) -> Any: ...


class ReferenceLookup(Protocol):
    """NCS 기준 데이터 조회 (Requirement 10, 이슈 #37). 이 작업은 능력단위 존재 확인만 쓴다."""

    def get_competency_unit(self, unit_code: str) -> Any | None: ...
