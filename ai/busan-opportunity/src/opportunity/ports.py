"""B가 바깥에 기대는 것들의 인터페이스.

core는 이 인터페이스만 보고 짠다. 실제 구현은 `store/`(DynamoDB, S3 Vectors, Scheduler, SES)와
`enrich/bedrock.py`(Bedrock)에 있고, 테스트는 `store/memory.py`의 메모리 구현을 쓴다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .models.policy import Policy
from .models.posting import AltCandidates, CompanyRecord, PostingLatest, PostingSnapshot
from .models.profile import BasicProfile, OppPrefs
from .models.user_state import ExplanationCache, Notification, PolicyAlert, SavedItem


# ---------------------------------------------------------------- team07-catalog
class CatalogRepo(Protocol):
    """공고·정책·기업. 읽기는 모든 흐름이, 쓰기는 B 수집·보강 배치만 한다. Scan은 쓰지 않는다."""

    def get_latest(self, job_posting_id: str) -> PostingLatest | None: ...
    def batch_get_latest(self, job_posting_ids: Sequence[str]) -> dict[str, PostingLatest]: ...
    def get_snapshot(self, job_posting_id: str, snapshot_id: str) -> PostingSnapshot | None: ...
    def get_alts(self, job_posting_id: str) -> AltCandidates | None: ...

    def query_postings_by_sido(self, sido: str, *, closes_from: str, limit: int = 100) -> list[PostingLatest]:
        """GSI1 `POSTING#{sido}`, closesAt >= closes_from. 마감 임박순."""
        ...

    def query_policies(self, region_key: str) -> list[Policy]:
        """GSI1 `POLICY#{region_key}`. 전국은 "00", 부산 "26", 서울 "11"."""
        ...

    def get_policy(self, policy_id: str) -> Policy | None: ...
    def get_company(self, company_id: str) -> CompanyRecord | None: ...
    def list_companies(self, sido: str) -> list[CompanyRecord]: ...

    def data_as_of(self) -> str | None:
        """마지막으로 수집이 끝난 시각 (ISO 8601 +09:00). 한 번도 없으면 None."""
        ...

    # 쓰기 (수집·보강 배치만)
    def put_snapshot(self, snapshot: PostingSnapshot) -> None: ...
    def put_latest(self, latest: PostingLatest) -> None: ...
    def put_alts(self, alts: AltCandidates) -> None: ...
    def put_policy(self, policy: Policy) -> None: ...
    def put_company(self, company: CompanyRecord) -> None: ...
    def set_data_as_of(self, iso: str) -> None: ...


# ---------------------------------------------------------------- team07-career-mentor
@dataclass
class IdemResult:
    """`IDEM#` 조건부 쓰기 결과 (D-31)."""

    state: str  # NEW(처음), REPLAY(같은 본문 재요청 → result 그대로 반환), CONFLICT(같은 키에 다른 본문 → 409)
    result: dict | None = None


class UserRepo(Protocol):
    """사용자별 데이터. PK는 항상 `USER#{userId}`다. 공통 프로필은 읽기만 한다."""

    def get_basic_profile(self, user_id: str) -> BasicProfile | None: ...

    def get_prefs(self, user_id: str) -> OppPrefs:
        """`OPP#PREFS`. 없으면 기본값."""
        ...

    def put_prefs(self, user_id: str, prefs: OppPrefs) -> None: ...

    def mark_leave_reason_asked(self, user_id: str, asked_at: str) -> bool:
        """이유 질문을 내려 줬다고 표시한다. 조건부 쓰기라 사용자당 처음 한 번만 True (T-09)."""
        ...

    def get_saved(self, user_id: str, job_posting_id: str) -> SavedItem | None: ...
    def list_saved(self, user_id: str) -> list[SavedItem]: ...

    def put_saved(self, user_id: str, item: SavedItem, workspace_tx: dict | None = None) -> bool:
        """`OPP#SAVED#` 조건부 쓰기. workspace_tx가 있으면 한 트랜잭션으로 쓴다. 이미 있으면 False."""
        ...

    def update_saved(self, user_id: str, item: SavedItem) -> None: ...

    def get_alert(self, user_id: str, policy_id: str) -> PolicyAlert | None: ...
    def list_alerts(self, user_id: str) -> list[PolicyAlert]: ...

    def put_alert(self, user_id: str, alert: PolicyAlert) -> bool:
        """조건부 쓰기. 이미 있으면 False."""
        ...

    def update_alert(self, user_id: str, alert: PolicyAlert) -> None: ...
    def delete_alert(self, user_id: str, policy_id: str) -> None: ...

    def put_notification(self, user_id: str, notification: Notification) -> bool:
        """조건부 쓰기. 같은 notificationId가 있으면 False (T-10)."""
        ...

    def list_notifications(self, user_id: str, *, cursor: str | None = None,
                           limit: int = 20) -> tuple[list[Notification], str | None]:
        """최신순."""
        ...

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool: ...

    def incr_immediate_count(self, user_id: str, week_key: str, limit: int) -> bool:
        """`OPP#CAP#{yyyy-Www}`. 한도 안이면 1 올리고 True, 넘으면 False (T-11)."""
        ...

    def get_explanation(self, user_id: str, job_posting_id: str) -> ExplanationCache | None: ...
    def put_explanation(self, user_id: str, cache: ExplanationCache, ttl_hours: int) -> None: ...

    def idem_begin(self, user_id: str, key: str, request_hash: str) -> IdemResult: ...
    def idem_finish(self, user_id: str, key: str, result: dict) -> None: ...


# ---------------------------------------------------------------- 벡터·모델
@dataclass
class VectorHit:
    key: str            # jobPostingId
    similarity: float   # 코사인 유사도 0~1 (S3 Vectors의 distance는 구현이 1 - distance로 바꾼다)
    metadata: dict = field(default_factory=dict)


class VectorIndex(Protocol):
    """S3 Vectors `team07-opp-vectors`/`postings-v1`. 필터 키: isBusan, sido, jobMajor, active, deadline."""

    def query(self, vector: Sequence[float], *, top_k: int, filter: dict | None = None) -> list[VectorHit]: ...
    def put(self, key: str, vector: Sequence[float], metadata: dict) -> None: ...
    def get(self, key: str) -> list[float] | None: ...
    def delete(self, key: str) -> None: ...


class Embedder(Protocol):
    """Bedrock 임베딩 (`EMBEDDING_MODEL_ID`). kind는 "document"(공고) 또는 "query"(프로필)."""

    def embed(self, text: str, *, kind: str = "document") -> list[float]: ...


class Llm(Protocol):
    """Bedrock 경량 LLM (`MODEL_ID`). core에서는 부르지 않는다. enrich에서만 쓴다."""

    def invoke(self, system: str, user: str, *, max_tokens: int = 1024) -> str: ...


# ---------------------------------------------------------------- 일정·메일·지표
class Scheduler(Protocol):
    """EventBridge Scheduler 일회성 일정 (at() 식, Asia/Seoul, 실행 후 자동 삭제)."""

    def create_once(self, name: str, at: datetime, payload: dict) -> bool:
        """같은 이름이 이미 있으면 만들지 않고 False. 오류로 다루지 않는다."""
        ...

    def delete(self, name: str) -> None: ...


class Mailer(Protocol):
    """SES. 메일 알림에 동의한 사용자에게만 보낸다. 주소를 못 찾으면 False."""

    def send(self, user_id: str, subject: str, body: str) -> bool: ...


class EventSink(Protocol):
    """유도 지표 이벤트 (CloudWatch EMF). 개인정보와 원문은 넣지 않는다."""

    def emit(self, event: str, **dimensions: Any) -> None: ...


class WorkspacePort(Protocol):
    """공통 백엔드의 워크스페이스 (`backend/workspace.py`). 지원 상태는 여기에만 둔다 (D-36)."""

    def workspace_id(self, job_posting_id: str) -> str: ...

    def put_tx_item(self, user_id: str, job_posting_id: str, snapshot_id: str, status: str) -> dict | None:
        """`OPP#SAVED#`와 한 트랜잭션으로 쓸 TransactWriteItems 항목. 이미 있으면 None."""
        ...

    def get_status(self, user_id: str, workspace_id: str) -> str | None: ...
    def set_status(self, user_id: str, workspace_id: str, status: str) -> None: ...


# ---------------------------------------------------------------- 수집 배치 전용
class RawStore(Protocol):
    """S3 `team07-opp-data-<계정ID>`. 경로: raw/{출처}/{날짜}/, normalized/{날짜}/, seed/, snapshots/, runs/{날짜}.json"""

    def put(self, key: str, body: bytes, content_type: str = "application/json") -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def list(self, prefix: str) -> list[str]: ...


class Secrets(Protocol):
    """Secrets Manager. 인증키는 여기서만 읽는다. 코드·로그·저장소에 두지 않는다."""

    def get(self, name: str) -> str: ...


# 공고 지원 자격 판정. `backend/eligibility.py`의 `evaluate_eligibility(profile, rules)`를 넣는다 (D-11).
EligibilityFn = Callable[[dict, list[dict]], dict]
