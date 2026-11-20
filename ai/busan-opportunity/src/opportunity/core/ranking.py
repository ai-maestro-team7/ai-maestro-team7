"""맞춤 공고 피드 (B-03). matchScore에는 부산 가산점을 넣지 않는다. 가산점은 rankScore에만 넣는다.

담당 워크트리: core-match. 명세: 개발계획서2 §4.2 B-03, §4.4, §4.5. 테스트: T-01, T-02, T-04, T-21.
"""

from dataclasses import dataclass
from datetime import date, datetime

from ..config import OpportunityConfig
from ..deps import Deps
from ..models.api import EligibilityResult, FeedResponse
from ..models.enums import MatchLevel, Sort
from ..models.posting import PostingLatest
from ..models.profile import BasicProfile


@dataclass
class MatchBreakdown:
    """적합도와 항목별 값. 측정하지 못한 항목은 None이고 가중치를 나머지로 다시 나눈다."""

    score: float
    job_match: float | None = None
    content_sim: float | None = None
    required_ok: float | None = None
    preferred_ok: float | None = None


def match_score(config: OpportunityConfig, profile: BasicProfile, posting: PostingLatest, *,
                content_similarity: float | None = None,
                eligibility: EligibilityResult | None = None) -> MatchBreakdown:
    """적합도 0~1. 공고의 부산 여부는 계산에 쓰지 않는다 (T-04)."""
    raise NotImplementedError("core-match 워크트리에서 구현한다")


def rank_score(config: OpportunityConfig, match: float, *, is_busan: bool, sort: Sort) -> float:
    """정렬 점수. sort=BUSAN_FIRST이고 부산 근무이며 match >= boostMinMatch일 때만 busanBoost를 더한다."""
    raise NotImplementedError("core-match 워크트리에서 구현한다")


def match_level(config: OpportunityConfig, match: float) -> MatchLevel:
    """화면에 보여 줄 3단계. good 이상 GOOD, fair 이상 FAIR, 그 밖은 LOW."""
    raise NotImplementedError("core-match 워크트리에서 구현한다")


def search_postings(deps: Deps, user_id: str, *, region: str = "ALL", sort: Sort | None = None,
                    job_codes: list[str] | None = None, keyword: str | None = None, cursor: str | None = None,
                    limit: int = 20, as_of: str | date | datetime | None = None) -> FeedResponse:
    """전국 공고를 찾아 정렬한다. 후보는 벡터 질의 두 번(부산, 전국)으로 모은다. 이 경로에 LLM은 없다.

    sort가 None이면 사용자 설정을 쓴다. BUSAN_FIRST와 MATCH는 공고 집합이 같고 순서만 다르다 (T-01).
    마감된 공고는 뺀다 (T-21). 수도권 공고에는 busanAlternativesCount를 붙인다.
    """
    raise NotImplementedError("core-match 워크트리에서 구현한다")
