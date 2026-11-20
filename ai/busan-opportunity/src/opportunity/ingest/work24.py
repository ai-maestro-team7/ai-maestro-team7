"""고용24. 채용정보(목록·상세, 민간 공고 B-01)와 청년일자리강소기업(배지 시드)."""

from collections.abc import Callable, Iterable

from ..ports import RawStore
from .field_maps import WORK24, WORK24_GANGSO
from .http import HttpGet, KeyCache
from .source import ListPages, SourceClient

SPEC = WORK24
GANGSO_SPEC = WORK24_GANGSO


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `client(...).fetch_list()`, 상세는 `client(...).fetch_detail(구인인증번호)`로 부른다.

    응답 미확인 (개인회원 불가). 필드 매핑은 `field_maps.WORK24`의 임시 값이다.
    """
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)


def gangso_client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
                  sleep: Callable[[float], None] | None = None) -> SourceClient:
    return SourceClient(GANGSO_SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)


def region_param(sido: str) -> str:
    """시·도 2자리 → 강소기업 API의 region 값 (부산 26 → 26000)."""
    return f"{sido}000"


def fetch_gangso(client_: SourceClient, sidos: Iterable[str]) -> ListPages:
    """시·도마다 강소기업 목록을 모두 받는다. 원본은 `raw/work24_gangso/{날짜}/region{코드}-{페이지}`에 남는다."""
    out = ListPages()
    for sido in sidos:
        region = region_param(sido)
        pages = client_.fetch_list({GANGSO_SPEC["region_param"]: region}, name=f"region{region}")
        out.records.extend(pages.records)
        out.pages += pages.pages
        out.failed_pages += pages.failed_pages
        out.warnings.extend(f"region{region} {w}" for w in pages.warnings)
    return out
