"""수집 배치 입구.

담당 워크트리: ingest. 명세: 개발계획서2 §4.2 B-01, §3. 테스트: T-17.
"""

from datetime import date, datetime

from ..config import OpportunityConfig
from ..models.policy import Policy
from ..models.posting import PostingSnapshot
from ..ports import CatalogRepo


def upsert_postings(config: OpportunityConfig, catalog: CatalogRepo, snapshots: list[PostingSnapshot], *,
                    as_of: str | date | datetime | None = None) -> dict:
    """정규화한 공고를 넣는다. contentHash가 바뀐 공고만 새 SNAP#을 쓰고 LATEST를 바꾼다.

    같은 날 두 번 돌려도 건수가 같다 (T-17). 돌려주는 값: {"created", "updated", "unchanged", "needsEnrich": [id…]}.
    """
    raise NotImplementedError("ingest 워크트리에서 구현한다")


def expire_postings(config: OpportunityConfig, catalog: CatalogRepo, *,
                    as_of: str | date | datetime | None = None) -> int:
    """마감이 지난 공고의 LATEST.isExpired를 true로 바꾼다. 스냅샷은 지우지 않는다. 바꾼 건수를 돌려준다."""
    raise NotImplementedError("ingest 워크트리에서 구현한다")


def upsert_policies(catalog: CatalogRepo, policies: list[Policy]) -> dict:
    """정책을 넣는다. 같은 정책이 온통청년에도 있으면 youthcenterId로 묶어 보강만 한다."""
    raise NotImplementedError("ingest 워크트리에서 구현한다")
