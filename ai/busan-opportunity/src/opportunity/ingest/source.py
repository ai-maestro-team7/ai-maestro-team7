"""출처 하나를 부르는 공통 클라이언트. 목록은 페이지마다, 상세는 받은 ID에만 부르고 원본을 `RawStore`에 그대로 남긴다.

저장 경로는 `raw/{출처}/{날짜}/{이름}`이다. 이름에는 페이지 번호나 공고 ID만 들어가고 URL·키는 들어가지 않는다.
"""

import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..ports import RawStore
from .field_maps import HTTP_TIMEOUT_SECONDS
from .http import FetchError, HttpGet, KeyCache, as_list, build_url, fetch_parsed, walk

log = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class ListPages:
    records: list[dict] = field(default_factory=list)
    pages: int = 0
    failed_pages: int = 0
    warnings: list[str] = field(default_factory=list)


def _int_or_none(value) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


class SourceClient:
    def __init__(self, spec: dict, keys: KeyCache, raw_store: RawStore, *, day: str, http_get: HttpGet,
                 sleep: Callable[[float], None] | None = None):
        self.spec = spec
        self.name = spec["source"]
        self._keys = keys
        self._raw = raw_store
        self._day = day
        self._http_get = http_get
        self._sleep = sleep

    # ------------------------------------------------------------ 내부
    def _url(self, section: dict, extra: dict) -> str:
        key = self._keys.get(self.spec["secret"])
        return build_url(section["url"], key_param=self.spec["key_param"], key=key,
                         params={**section.get("params", {}), **extra})

    def _save(self, name: str, body: bytes) -> None:
        is_xml = body.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")
        extension, content_type = ("xml", "application/xml") if is_xml else ("json", "application/json")
        self._raw.put(f"raw/{self.name}/{self._day}/{name}.{extension}", body, content_type)

    # ------------------------------------------------------------ 목록
    def fetch_list(self) -> ListPages:
        """페이지마다 부른다. 실패한 페이지는 다시 부르고, 그래도 안 되면 건너뛴다.

        전체 건수를 알면 다음 페이지로 계속 가고, 모르면 실패한 자리에서 멈춘다.
        """
        cfg = self.spec["list"]
        size = cfg["page_size"]
        first = cfg["first_page"]
        out = ListPages()
        total_pages: int | None = None
        for offset in range(cfg["max_pages"]):
            page = first + offset
            url = self._url(cfg, {cfg["page_param"]: page, cfg["size_param"]: size})
            try:
                body, parsed = fetch_parsed(self._http_get, url, label=f"{self.name}:list:p{page}",
                                            sleep=self._sleep, timeout=HTTP_TIMEOUT_SECONDS)
            except FetchError as e:
                out.failed_pages += 1
                out.warnings.append(f"p{page} 실패: {e}")
                if total_pages is None or offset + 1 >= total_pages:
                    break
                continue
            self._save(f"list-{page:04d}", body)
            out.pages += 1
            items = [item for item in as_list(walk(parsed, cfg["items_path"])) if isinstance(item, dict)]
            out.records.extend(items)
            total = _int_or_none(walk(parsed, cfg.get("total_path")))
            if total_pages is None and total is not None:
                total_pages = max(1, math.ceil(total / size))
            if not items:
                if page == first:
                    out.warnings.append("첫 페이지에서 항목을 찾지 못함 · 응답 필드 매핑 확인 필요")
                break
            if len(items) < size or (total_pages is not None and offset + 1 >= total_pages):
                break
        else:
            out.warnings.append(f"최대 {cfg['max_pages']}페이지에서 멈춤")
        return out

    # ------------------------------------------------------------ 상세
    def fetch_detail(self, external_id: str) -> dict | None:
        """받은 ID 하나의 상세. 응답에서 항목을 찾지 못하면 None, 호출이 끝내 실패하면 FetchError."""
        cfg = self.spec.get("detail")
        if cfg is None:
            return None
        url = self._url(cfg, {cfg["id_param"]: external_id})
        body, parsed = fetch_parsed(self._http_get, url, label=f"{self.name}:detail", sleep=self._sleep,
                                    timeout=HTTP_TIMEOUT_SECONDS)
        self._save(f"detail-{_UNSAFE.sub('_', external_id)[:80]}", body)
        items = as_list(walk(parsed, cfg["item_path"]))
        return items[0] if items and isinstance(items[0], dict) else None
