"""A 함수가 받는 의존성 묶음. 입구(REST·작업)가 한 번 만들어 넘긴다."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import MentoringConfig
from .ports import DocumentExtractor, Llm, ObjectStore, ReferenceLookup, TaskDispatcher, UserRepo
from .text_tools import TextTools

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def new_id(prefix: str) -> str:
    """`{접두사}-{uuid4 앞 12자}` (db-schema §6). `#`이 들어가지 않는다."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class Deps:
    config: MentoringConfig
    users: UserRepo
    objects: ObjectStore
    llm: Llm
    tasks: TaskDispatcher
    text: TextTools
    # 개인 문서 경로 users/{hashedUserId}/ 의 해시. 방식은 백엔드와 정한다 (BE-6, 미결정 M-1)
    hash_user_id: Callable[[str], str]
    reference: ReferenceLookup | None = None  # 없으면 NCS 능력단위 코드를 붙이지 않는다
    extractor: DocumentExtractor | None = None  # 없으면 PDF 업로드 완료를 받지 않는다 (텍스트 입력만)
    metrics_sink: Callable[[str], None] | None = None  # EMF 한 줄을 받을 곳. 없으면 stdout
    now: Callable[[], datetime] = field(default=now_kst)
    new_id: Callable[[str], str] = field(default=new_id)

    def now_iso(self) -> str:
        return self.now().astimezone(KST).isoformat(timespec="seconds")
