"""지방공공기관 채용정보 (행정안전부·한국지역정보개발원). 지방공사·공단·출연기관 공고 수집 B-01.

시·도마다 한 번씩 부른다 (sidoCd=007001~007017). 페이지 인자는 없다. 원본은 `raw/klid/{날짜}/sido{코드}-0001.xml`에 남는다.
"""

from collections.abc import Callable, Iterable

from ..ports import RawStore
from .field_maps import KLID
from .http import HttpGet, KeyCache
from .source import ListPages, SourceClient

SPEC = KLID


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `fetch_all(client(...))`로 부른다. 상세 API는 없다."""
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)


def fetch_all(client_: SourceClient, sido_codes: Iterable[str] | None = None) -> ListPages:
    """시·도 코드마다 목록을 받아 합친다. 공고가 없는 시·도(resultCode=3)는 경고 없이 0건이다."""
    out = ListPages()
    for code in sido_codes or SPEC["region_codes"]:
        pages = client_.fetch_list({SPEC["region_param"]: code}, name=f"sido{code}")
        out.records.extend(pages.records)
        out.pages += pages.pages
        out.failed_pages += pages.failed_pages
        out.warnings.extend(f"sido{code} {w}" for w in pages.warnings)
    return out
