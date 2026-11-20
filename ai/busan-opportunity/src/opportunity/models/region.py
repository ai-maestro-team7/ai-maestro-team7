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


class FestivalInfo(OppModel):
    """부산 축제 (부산광역시 축제정보). 기간은 원문 그대로 둔다."""

    festival_id: str
    title: str
    gugun: str | None = None
    place: str | None = None
    period: str | None = None
    traffic: str | None = None
    url: str | None = None
    source: str
    as_of: str


class TransitInfo(OppModel):
    """대중교통 사실 한 줄 (예: 도시철도 1호선 40개 역). 출처와 기준일이 꼭 있어야 한다."""

    label: str
    value: str
    source: str
    as_of: str


class GuOffice(OppModel):
    """구·군청 위치. 통근 시간과 직선거리의 기준점이다 (집 주소는 받지 않는다)."""

    sigungu: str
    name: str
    lat: float
    lng: float


class LocalLifeData(OppModel):
    """부산 근무지 주변 생활 정보의 원천. 입구가 시드에서 읽어 `Deps.local_life`에 넣는다."""

    festivals: list[FestivalInfo] = Field(default_factory=list)
    transit: list[TransitInfo] = Field(default_factory=list)
    commute_minutes: dict[str, int] = Field(default_factory=dict)  # "거주 시군구>근무 시군구" → 대중교통 분
    commute_source: str | None = None
    commute_as_of: str | None = None
    gu_offices: dict[str, GuOffice] = Field(default_factory=dict)  # 시군구 코드 → 구·군청 위치
    gu_offices_source: str | None = None
    gu_offices_as_of: str | None = None


class LocalLifeView(OppModel):
    """부산 공고 상세에만 붙는 "이 동네에서 일하면" 묶음. 피드와 다른 지역 공고에는 붙이지 않는다."""

    commute_minutes: int | None = None
    commute_label: str | None = None
    commute_source: str | None = None
    distance_km: float | None = None   # 구청 사이 직선거리. 통근 시간이 없는 구간에서도 나온다
    distance_label: str | None = None
    festivals: list[FestivalInfo] = Field(default_factory=list)
    transit: list[TransitInfo] = Field(default_factory=list)
