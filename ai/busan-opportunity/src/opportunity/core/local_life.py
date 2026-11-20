"""부산 공고 상세의 "이 동네에서 일하면" 묶음 (축제·대중교통·통근). 규칙 코드라 LLM을 부르지 않는다.

- 부산 근무 공고의 상세에만 붙인다. 근무지를 모르거나 해외면 붙이지 않는다. 다른 지역 공고의 정보는 줄이지 않는다.
- 홍보처럼 보이지 않게 config.localLife의 festivalMax·transitMax만큼만 보여 준다.
- 출처·기준일이 없는 항목은 내보내지 않는다. 통근은 표에 있는 값만 쓰고 추정하지 않는다.
- 축제 기간은 자유 서술이라 지난 축제를 가려내지 않고 원문 그대로 보여 준다.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.posting import PostingLatest, PostingSnapshot, WorkRegion
from ..models.profile import BasicProfile
from ..models.region import FestivalInfo, LocalLifeView, TransitInfo
from . import copy_rules, facts, regions

# 부산 구·군 코드 → 축제 데이터의 GUGUN_NM. 근무지 구의 축제를 먼저 고를 때만 쓴다
BUSAN_GUGUN = {
    "26110": "중구", "26140": "서구", "26170": "동구", "26200": "영도구", "26230": "부산진구",
    "26260": "동래구", "26290": "남구", "26320": "북구", "26350": "해운대구", "26380": "사하구",
    "26410": "금정구", "26440": "강서구", "26470": "연제구", "26500": "수영구", "26530": "사상구",
    "26710": "기장군",
}


def gugun_name(region: WorkRegion) -> str | None:
    """근무지 구·군 이름. 코드가 없으면 label("부산 해운대구")에서 찾는다. 모르면 None."""
    name = BUSAN_GUGUN.get(region.sigungu or "")
    if name:
        return name
    words = (region.label or "").split()
    return next((w for w in words if w in BUSAN_GUGUN.values()), None)


def _sourced(item: FestivalInfo | TransitInfo) -> bool:
    return bool(item.source and item.source.strip() and item.as_of and item.as_of.strip())


def pick_festivals(festivals: list[FestivalInfo], gugun: str | None, limit: int) -> list[FestivalInfo]:
    """근무지 구의 축제를 먼저, 모자라면 부산 다른 곳에서 채운다. 같은 묶음 안에서는 원본 순서를 지킨다."""
    if limit <= 0:
        return []
    usable = [f for f in festivals if _sourced(f)]
    local = [f for f in usable if gugun and f.gugun == gugun]
    rest = [f for f in usable if f not in local]
    return (local + rest)[:limit]


def commute_for(deps: Deps, profile: BasicProfile, region: WorkRegion) -> tuple[int, str, str] | None:
    """(분, 문구, 출처). 거주·근무 시군구 쌍이 표에 있고 출처·기준일이 있을 때만."""
    data = deps.local_life
    home, work = profile.residence_sigungu, region.sigungu
    if not (home and work and data.commute_source and data.commute_as_of):
        return None
    minutes = data.commute_minutes.get(f"{home}>{work}")
    if minutes is None:
        return None
    return minutes, copy_rules.COMMUTE_LABEL.format(minutes=minutes), data.commute_source


def build_local_life(deps: Deps, profile: BasicProfile, posting: PostingSnapshot | PostingLatest, *,
                     as_of: str | date | datetime | None = None) -> LocalLifeView | None:
    """부산 근무 공고면 축제(festivalMax)·대중교통(transitMax)·통근을 묶어 준다. 아니면, 또는 셋 다 비면 None.

    as_of는 다른 상세 계산과 맞춰 받는다. 축제 기간이 자유 서술이라 지금은 날짜로 거르지 않는다.
    """
    region = posting.work_region
    if not regions.is_busan(deps.config, region):
        return None
    limits = deps.config.local_life
    data = deps.local_life
    festivals = pick_festivals(data.festivals, gugun_name(region), limits.festival_max)
    transit = [t for t in data.transit if _sourced(t)][:max(limits.transit_max, 0)]
    commute = commute_for(deps, profile, region)
    distance = facts.distance_km(data, profile, region)
    if not (festivals or transit or commute or distance is not None):
        return None
    minutes, label, source = commute or (None, None, None)
    return LocalLifeView(commute_minutes=minutes, commute_label=label, commute_source=source,
                         distance_km=distance, distance_label=facts.distance_fact(distance),
                         festivals=festivals, transit=transit)
