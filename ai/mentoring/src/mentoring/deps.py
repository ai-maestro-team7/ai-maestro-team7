"""A 함수가 받는 의존성 묶음. 입구(REST·작업)가 한 번 만들어 넘긴다."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .config import MentoringConfig
from .ports import DocumentExtractor, Llm, ObjectStore, ReferenceLookup, TaskDispatcher, UserRepo
from .text_tools import TextTools

if TYPE_CHECKING:  # stories·fit 패키지가 이 모듈을 import하므로 실행 중에는 가져오지 않는다
    from .fit.ports import AnalysisStore, CatalogReader, EligibilityFn, KnowledgeSearch, NcsLookup
    from .stories.repo import StoryRepo

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
    stories: "StoryRepo | None" = None  # 없으면 경험 블록 경로가 501
    # 직무 적합도 (#88). analyses가 없으면 /analyses가 501
    analyses: "AnalysisStore | None" = None
    catalog: "CatalogReader | None" = None      # B 공고 (읽기만). 없으면 공고 기준 분석이 501
    ncs: "NcsLookup | None" = None              # NCS 정확 조회. 없으면 NCS 기준 분석이 501
    knowledge: "KnowledgeSearch | None" = None  # Bedrock KB. 없으면 출처 없이 분석하고 경고를 남긴다
    eligibility: "EligibilityFn | None" = None  # 백엔드가 evaluate_eligibility를 넣는다 (BE-8). 없으면 확인 필요
    now: Callable[[], datetime] = field(default=now_kst)
    new_id: Callable[[str], str] = field(default=new_id)

    def now_iso(self) -> str:
        return self.now().astimezone(KST).isoformat(timespec="seconds")
