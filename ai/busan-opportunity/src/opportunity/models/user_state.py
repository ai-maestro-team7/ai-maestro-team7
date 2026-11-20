"""사용자별 B 데이터. `team07-career-mentor`의 OPP# 아이템이다 (db-schema §2.2)."""

from pydantic import Field

from .base import OppModel
from .enums import NotificationChannel, NotificationType, SavedKind


class SavedItem(OppModel):
    """`OPP#SAVED#{jobPostingId}`. 지원 상태는 여기 두지 않고 워크스페이스에만 둔다 (D-36)."""

    job_posting_id: str
    kind: SavedKind
    workspace_id: str | None = None
    snapshot_id: str
    is_busan: bool
    job_major: str | None = None
    from_alternative_of: str | None = None
    saved_at: str
    schedule_names: list[str] = Field(default_factory=list)


class PolicyAlert(OppModel):
    """`OPP#ALERT#{policyId}`. 정책이 열리면 알림."""

    policy_id: str
    scheduled_at: str
    schedule_name: str
    checks: int = 0  # 재확인한 횟수


class Notification(OppModel):
    """`OPP#NOTI#{notificationId}`. ID는 `{yyyyMMddTHHmmss}-{해시 8자}`이고 `#`을 넣지 않는다."""

    notification_id: str
    type: NotificationType
    title: str
    body: str
    link: str | None = None
    read: bool = False
    channel: NotificationChannel = NotificationChannel.INBOX
    created_at: str
    simulated: bool = False  # 데모 시간 앞당기기로 만든 알림


class ExplanationCache(OppModel):
    """`OPP#EXPL#{jobPostingId}`. 설명 문장 캐시 (24시간)."""

    job_posting_id: str
    sentences: list[str]
    facts_hash: str
    created_at: str
