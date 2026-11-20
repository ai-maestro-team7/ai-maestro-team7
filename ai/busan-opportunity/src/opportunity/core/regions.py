"""지역 코드. 시·도는 법정동 코드 앞 2자리다. 부산 여부는 본사가 아니라 근무지로 판단한다."""

from ..config import OpportunityConfig
from ..models.posting import WorkRegion

SIDO_NAMES = {
    "11": "서울", "12": "전남광주", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산",
    "36": "세종", "41": "경기", "43": "충북", "44": "충남", "46": "전남", "47": "경북", "48": "경남",
    "50": "제주", "51": "강원", "52": "전북",
}
NATIONAL = "00"
# 2026년에 합쳐진 시·도. 옛 코드(광주 29, 전남 46)와 통합 코드(12)를 같은 곳으로 본다
MERGED_SIDO = {"29": "12", "46": "12"}
# 부산 구·군 코드 → 이름. 사용자 거주지(residenceSigungu)는 부산만 구·군까지 받는다
BUSAN_SIGUNGU_NAMES = {
    "26110": "중구", "26140": "서구", "26170": "동구", "26200": "영도구", "26230": "부산진구",
    "26260": "동래구", "26290": "남구", "26320": "북구", "26350": "해운대구", "26380": "사하구",
    "26410": "금정구", "26440": "강서구", "26470": "연제구", "26500": "수영구", "26530": "사상구",
    "26710": "기장군",
}


def sido_name(sido: str | None) -> str | None:
    return SIDO_NAMES.get(sido or "")


def same_sido(a: str | None, b: str | None) -> bool:
    """시·도 코드가 같은 곳인지. 합쳐진 시·도는 옛 코드와 통합 코드를 같게 본다."""
    return bool(a) and bool(b) and MERGED_SIDO.get(a, a) == MERGED_SIDO.get(b, b)


def sigungu_name(code: str | None) -> str | None:
    return BUSAN_SIGUNGU_NAMES.get(code or "")


def is_busan(config: OpportunityConfig, region: WorkRegion) -> bool:
    """근무지를 모르면 부산으로 세지 않는다."""
    return not region.unknown and not region.overseas and region.sido == config.data.busan_sido


def is_capital_area(config: OpportunityConfig, region: WorkRegion) -> bool:
    return not region.unknown and not region.overseas and region.sido in config.data.capital_area_sido


def is_overseas(region: WorkRegion) -> bool:
    return region.overseas


def region_sidos(config: OpportunityConfig, region: str | None) -> list[str] | None:
    """피드의 region 인자를 시·도 목록으로 바꾼다. ALL이면 None (걸러 내지 않음)."""
    if not region or region == "ALL":
        return None
    if region == "BUSAN":
        return [config.data.busan_sido]
    if region == "CAPITAL":
        return list(config.data.capital_area_sido)
    return [region]
