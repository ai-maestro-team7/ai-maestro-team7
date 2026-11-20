"""지역 코드. 시·도는 법정동 코드 앞 2자리다. 부산 여부는 본사가 아니라 근무지로 판단한다."""

from ..config import OpportunityConfig
from ..models.posting import WorkRegion

SIDO_NAMES = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산",
    "36": "세종", "41": "경기", "43": "충북", "44": "충남", "46": "전남", "47": "경북", "48": "경남",
    "50": "제주", "51": "강원", "52": "전북",
}
NATIONAL = "00"


def sido_name(sido: str | None) -> str | None:
    return SIDO_NAMES.get(sido or "")


def is_busan(config: OpportunityConfig, region: WorkRegion) -> bool:
    """근무지를 모르면 부산으로 세지 않는다."""
    return not region.unknown and region.sido == config.data.busan_sido


def is_capital_area(config: OpportunityConfig, region: WorkRegion) -> bool:
    return not region.unknown and region.sido in config.data.capital_area_sido


def region_sidos(config: OpportunityConfig, region: str | None) -> list[str] | None:
    """피드의 region 인자를 시·도 목록으로 바꾼다. ALL이면 None (걸러 내지 않음)."""
    if not region or region == "ALL":
        return None
    if region == "BUSAN":
        return [config.data.busan_sido]
    if region == "CAPITAL":
        return list(config.data.capital_area_sido)
    return [region]
