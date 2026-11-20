"""해외취업 모집공고 (한국산업인력공단 월드잡플러스). 해외 근무 공고 수집 B-01.

100건씩 페이지를 넘겨 받는다. 원본은 `raw/worldjob/{날짜}/list-{페이지}.xml`에 남는다.
인증키는 다른 계정으로 발급받은 공공데이터포털 키(`SECRET_DATA_GO_KR_TEAM`)다.
"""

from collections.abc import Callable

from ..ports import RawStore
from .field_maps import WORLDJOB
from .http import HttpGet, KeyCache
from .source import ListPages, SourceClient

SPEC = WORLDJOB


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `fetch_all(client(...))`로 부른다. 공고 번호가 없어서 상세 호출은 없다."""
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)


def fetch_all(client_: SourceClient) -> ListPages:
    return client_.fetch_list()
