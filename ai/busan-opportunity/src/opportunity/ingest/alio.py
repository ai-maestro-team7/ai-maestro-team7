"""잡알리오 채용공시 (목록·상세). 이전기관·공공기관 공고 수집 B-01."""

from collections.abc import Callable

from ..ports import RawStore
from .field_maps import ALIO
from .http import HttpGet, KeyCache
from .source import SourceClient

SPEC = ALIO


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `client(...).fetch_list()`, 상세는 `client(...).fetch_detail(공시번호)`로 부른다."""
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)
