"""Agent 함수가 받는 의존성 묶음. 백엔드 입구가 한 번 만들어 넘긴다."""

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from .config import SupervisorConfig, get_config
from .ports import AgentRunner, CareerDocsPort, ChatStore, Dispatcher, OpportunityPort, ProfilePort

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def new_session_id() -> str:
    return f"chat-{uuid.uuid4().hex[:12]}"


def new_message_id(now: datetime) -> str:
    """`{yyyyMMddTHHmmssSSS}-{16진 6자}`. 시각이 앞에 있어 SK가 시간순으로 정렬된다. `#`이 없다."""
    stamp = now.astimezone(KST).strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}"
    return f"{stamp}-{secrets.token_hex(3)}"


def _hash(user_id: str) -> str:
    return sha256(user_id.encode("utf-8")).hexdigest()[:16]


@dataclass
class Deps:
    store: ChatStore
    opportunities: OpportunityPort
    docs: CareerDocsPort
    profiles: ProfilePort
    runner: AgentRunner
    dispatcher: Dispatcher
    model_id: str
    config: SupervisorConfig = field(default_factory=get_config)
    hash_user_id: Callable[[str], str] = _hash  # 로그용. 백엔드가 공통 해시를 넣는다
    now: Callable[[], datetime] = now_kst
    new_session_id: Callable[[], str] = new_session_id
    new_message_id: Callable[[datetime], str] = new_message_id

    def now_iso(self) -> str:
        return self.now().astimezone(KST).isoformat(timespec="seconds")
