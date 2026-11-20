"""고용24 채용정보 (목록·상세). 민간 공고 수집 B-01."""

from collections.abc import Callable

from ..ports import RawStore
from .field_maps import WORK24
from .http import HttpGet, KeyCache
from .source import SourceClient

SPEC = WORK24


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `client(...).fetch_list()`, 상세는 `client(...).fetch_detail(구인인증번호)`로 부른다."""
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)
