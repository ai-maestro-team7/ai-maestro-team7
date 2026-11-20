"""온통청년 청년정책. 정책 지갑과 서울·부산 비교용 수집 B-01. 상세 호출은 없다."""

from collections.abc import Callable

from ..ports import RawStore
from .field_maps import YOUTHCENTER
from .http import HttpGet, KeyCache
from .source import SourceClient

SPEC = YOUTHCENTER


def client(keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
           sleep: Callable[[float], None] | None = None) -> SourceClient:
    """목록은 `client(...).fetch_list()`로 부른다."""
    return SourceClient(SPEC, keys, raw_store, day=day, http_get=http_get, sleep=sleep)
