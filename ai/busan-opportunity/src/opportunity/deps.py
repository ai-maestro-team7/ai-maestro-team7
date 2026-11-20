"""B 함수가 받는 의존성 묶음. 입구(REST·Agent·배치)가 한 번 만들어 넘긴다."""

from dataclasses import dataclass, field

from .config import OpportunityConfig
from .models.region import LocalLifeData, RegionStats
from .ports import (
    CatalogRepo,
    EligibilityFn,
    Embedder,
    EventSink,
    Llm,
    Mailer,
    Scheduler,
    UserRepo,
    VectorIndex,
    WorkspacePort,
)


@dataclass
class Deps:
    config: OpportunityConfig
    catalog: CatalogRepo
    users: UserRepo
    vectors: VectorIndex
    embedder: Embedder
    eligibility: EligibilityFn
    workspaces: WorkspacePort
    scheduler: Scheduler
    events: EventSink
    llm: Llm | None = None        # 설명 문장·요건 추출에만
    mailer: Mailer | None = None  # 메일 알림. 없으면 알림함만
    region_stats: RegionStats = field(default_factory=RegionStats)  # 비교 패널의 주거비·통근
    local_life: LocalLifeData = field(default_factory=LocalLifeData)  # 부산 근무지 주변 생활 정보
