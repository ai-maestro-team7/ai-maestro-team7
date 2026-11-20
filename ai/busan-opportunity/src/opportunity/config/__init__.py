"""설정 로더. 숫자는 `opportunity_config.json`에서만 읽는다. 코드에 박지 않는다.

읽을 때 가중치 합 1, busanBoost < inversionGuard, 기준값 0~1을 검사하고 어긋나면 멈춘다 (T-03).
모델 ID는 이 파일에 두지 않고 환경변수 `MODEL_ID`, `EMBEDDING_MODEL_ID`로 받는다.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from ..models.base import OppModel

DEFAULT_PATH = Path(__file__).with_name("opportunity_config.json")


class ConfigError(RuntimeError):
    """설정이 없거나 규칙에 어긋난다. 시작하지 않는다."""


def _unit(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name}은 0~1이어야 한다: {value}")


def _sum_one(values: list[float], name: str) -> None:
    if abs(sum(values) - 1.0) > 1e-9:
        raise ValueError(f"{name} 합이 1이 아니다: {sum(values)}")


class ModelsConfig(OppModel):
    embed_dim: int


class MatchWeights(OppModel):
    job_match: float
    content_sim: float
    required_ok: float
    preferred_ok: float


class JobMatchLevels(OppModel):
    exact: float
    same_middle: float
    same_major: float


class Range(OppModel):
    low: float
    high: float


class MatchLevels(OppModel):
    good: float
    fair: float


class MatchConfig(OppModel):
    weights: MatchWeights
    job_match_levels: JobMatchLevels
    content_sim_range: Range
    unknown_condition_value: float
    levels: MatchLevels

    @model_validator(mode="after")
    def _check(self):
        w = self.weights
        _sum_one([w.job_match, w.content_sim, w.required_ok, w.preferred_ok], "match.weights")
        for name, value in (("jobMatchLevels.exact", self.job_match_levels.exact),
                            ("jobMatchLevels.sameMiddle", self.job_match_levels.same_middle),
                            ("jobMatchLevels.sameMajor", self.job_match_levels.same_major),
                            ("contentSimRange.low", self.content_sim_range.low),
                            ("contentSimRange.high", self.content_sim_range.high),
                            ("unknownConditionValue", self.unknown_condition_value),
                            ("levels.good", self.levels.good), ("levels.fair", self.levels.fair)):
            _unit(value, f"match.{name}")
        if not self.content_sim_range.low < self.content_sim_range.high:
            raise ValueError("match.contentSimRange는 low < high여야 한다")
        if not self.levels.fair < self.levels.good:
            raise ValueError("match.levels는 fair < good이어야 한다")
        return self


class CandidateTopK(OppModel):
    busan: int
    all: int


class RankingConfig(OppModel):
    busan_boost: float
    boost_min_match: float
    inversion_guard: float
    candidate_top_k: CandidateTopK

    @model_validator(mode="after")
    def _check(self):
        _unit(self.busan_boost, "ranking.busanBoost")
        _unit(self.boost_min_match, "ranking.boostMinMatch")
        _unit(self.inversion_guard, "ranking.inversionGuard")
        if not self.busan_boost < self.inversion_guard:
            raise ValueError("ranking.busanBoost는 inversionGuard보다 작아야 한다")
        return self


class AltWeights(OppModel):
    similarity: float
    match: float
    reason: float


class AlternativesConfig(OppModel):
    min_similarity: float
    expanded_min_similarity: float
    mini_card_max: int
    view_max: int
    precompute_top_k: int = 10
    weights: AltWeights

    @model_validator(mode="after")
    def _check(self):
        _sum_one([self.weights.similarity, self.weights.match, self.weights.reason], "alternatives.weights")
        _unit(self.min_similarity, "alternatives.minSimilarity")
        _unit(self.expanded_min_similarity, "alternatives.expandedMinSimilarity")
        if not self.expanded_min_similarity <= self.min_similarity:
            raise ValueError("alternatives.expandedMinSimilarity는 minSimilarity 이하여야 한다")
        return self


class CompareConfig(OppModel):
    rent_conversion_rate: float | None = None  # 출처와 함께 입력하기 전에는 null. null이면 주거비 행을 숨긴다
    rent_max_area_m2: int
    rent_months: int
    min_sample: int


class PoliciesConfig(OppModel):
    hide_unverified: bool = True


class NotificationsConfig(OppModel):
    immediate_per_week: int
    digest_hour: int
    quiet_hours: list[int]
    recheck_days: int
    max_rechecks: int
    deadline_days: list[int] = Field(default_factory=lambda: [7, 3])
    retention_days: int = 90


class LeaveReasonConfig(OppModel):
    ask_once_per_user: bool = True


class ExplanationConfig(OppModel):
    cache_hours: int = 24
    sentences: int = 2


class AgentConfig(OppModel):
    max_postings: int = 5


class LocalLifeConfig(OppModel):
    festival_max: int = 2    # 상세에 보여 줄 축제 수. 많이 보여 주면 홍보처럼 보인다
    transit_max: int = 3


class AskConfig(OppModel):
    top_k: int = 5            # LLM에 넘길 정책 문서 수
    candidate_k: int = 20     # 검색에서 먼저 가져올 수
    max_doc_chars: int = 2000  # 문서 하나에서 LLM에 넘길 글자 수
    max_tokens: int = 700
    max_question_chars: int = 300


class DataConfig(OppModel):
    stale_after_hours: int
    busan_sido: str
    capital_area_sido: list[str]
    demo_job_families: list[str] = Field(default_factory=list)


class OpportunityConfig(OppModel):
    config_version: str
    region: str
    models: ModelsConfig
    match: MatchConfig
    ranking: RankingConfig
    alternatives: AlternativesConfig
    compare: CompareConfig
    policies: PoliciesConfig
    notifications: NotificationsConfig
    leave_reason: LeaveReasonConfig
    explanation: ExplanationConfig = Field(default_factory=ExplanationConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    local_life: LocalLifeConfig = Field(default_factory=LocalLifeConfig)
    ask: AskConfig = Field(default_factory=AskConfig)
    data: DataConfig


def parse_config(raw: dict) -> OpportunityConfig:
    try:
        return OpportunityConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"opportunity_config.json이 규칙에 어긋난다: {e}") from e


def load_config(path: str | os.PathLike | None = None) -> OpportunityConfig:
    """설정 파일을 읽어 검사한다. 경로는 인자 → 환경변수 `OPPORTUNITY_CONFIG_PATH` → 패키지 기본 파일 순서."""
    target = Path(path or os.environ.get("OPPORTUNITY_CONFIG_PATH") or DEFAULT_PATH)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"설정 파일을 읽지 못했다: {target}") from e
    return parse_config(raw)


@lru_cache(maxsize=1)
def get_config() -> OpportunityConfig:
    return load_config()


def require_env(name: str) -> str:
    """필수 환경변수를 읽는다. 없으면 변수 이름을 담은 오류를 내고 멈춘다. 기본값으로 대체하지 않는다."""
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"환경변수 {name}이(가) 없다")
    return value
