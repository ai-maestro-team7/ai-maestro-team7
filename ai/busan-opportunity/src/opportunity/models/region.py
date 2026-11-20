"""지역 통계 (비교 패널). 출처와 기준일이 없는 값은 쓰지 않는다."""

from pydantic import Field

from .base import OppModel


class RentStat(OppModel):
    """원룸 환산 월세 중앙값 (만 원). 표본이 minSample보다 적으면 시·도 값으로 바꿔 보여 준다."""

    region_code: str  # 시군구 5자리 또는 시·도 2자리
    label: str
    value: int
    sample_size: int
    period: str
    method: str
    source: str
    as_of: str


class CommuteStat(OppModel):
    """통근 30분 미만 비율 (%). 지역 평균이다."""

    region_code: str
    label: str
    value: float
    source: str
    as_of: str


class RegionStats(OppModel):
    rent: dict[str, RentStat] = Field(default_factory=dict)
    commute: dict[str, CommuteStat] = Field(default_factory=dict)
