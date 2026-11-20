"""공공 API 호출 바닥 계층. 표준 라이브러리 `urllib`만 쓴다.

- 요청 함수(`http_get`)는 주입할 수 있다. 테스트는 가짜를 넣는다.
- 실패한 요청은 지수 백오프로 다시 부른다. 대기 함수(`sleep`)도 주입할 수 있다.
- 인증키와 키가 든 URL은 로그, 예외 메시지, S3 키에 남기지 않는다. 오류에는 종류와 상태 코드만 담는다.
"""

import json
import logging
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

from ..ports import Secrets
from .field_maps import BACKOFF_BASE_SECONDS, HTTP_TIMEOUT_SECONDS, MAX_RETRIES, SECRET_CACHE_SECONDS

log = logging.getLogger(__name__)

HttpGet = Callable[[str, float], bytes]
"""`http_get(url, timeout_seconds) -> 응답 본문`. 실패하면 예외를 던진다."""

_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")
_FORBIDDEN_XML = re.compile(rb"<!(DOCTYPE|ENTITY)", re.IGNORECASE)


class FetchError(RuntimeError):
    """호출이나 응답 해석에 실패했다. 메시지에 URL과 키를 넣지 않는다."""


def default_http_get(url: str, timeout: float = HTTP_TIMEOUT_SECONDS) -> bytes:
    """GET 한 번. 오류에서 URL이 새지 않게 `from None`으로 원인 연결을 끊는다."""
    request = urllib.request.Request(url, headers={"Accept": "application/json, application/xml"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https 공공 API만 부른다)
            return response.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}") from None
    except Exception as e:
        raise FetchError(f"요청 실패 ({type(e).__name__})") from None


# ---------------------------------------------------------------- 인증키
def encode_key(key: str) -> str:
    """URL에 넣을 키. 이미 인코딩된 값(공공데이터포털 발급 키)이면 그대로 두고, 아니면 인코딩한다."""
    if _ENCODED.search(key):
        return key
    return quote(key, safe="")


def build_url(base: str, *, key_param: str, key: str, params: dict[str, Any]) -> str:
    """키는 `encode_key`로, 나머지 인자는 `urlencode`로 붙인다. 키가 두 번 인코딩되지 않는다."""
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{base}?{key_param}={encode_key(key)}" + (f"&{query}" if query else "")


class KeyCache:
    """`Secrets`에서 읽은 키를 5분 동안 들고 있는다. 키 값은 로그에 남기지 않는다."""

    def __init__(self, secrets: Secrets, *, ttl: float = SECRET_CACHE_SECONDS,
                 monotonic: Callable[[], float] = time.monotonic):
        self._secrets = secrets
        self._ttl = ttl
        self._monotonic = monotonic
        self._cache: dict[str, tuple[float, str]] = {}

    def get(self, name: str) -> str:
        now = self._monotonic()
        hit = self._cache.get(name)
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        value = self._secrets.get(name)
        self._cache[name] = (now, value)
        return value


# ---------------------------------------------------------------- 응답 해석
def _xml_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    out: dict[str, Any] = {}
    for child in children:
        value = _xml_to_value(child)
        if child.tag in out:
            if not isinstance(out[child.tag], list):
                out[child.tag] = [out[child.tag]]
            out[child.tag].append(value)
        else:
            out[child.tag] = value
    return out


def parse_body(body: bytes) -> Any:
    """JSON이나 XML 응답을 dict·list로 바꾼다. 바꿀 수 없으면 FetchError."""
    text = body.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not text:
        raise FetchError("빈 응답")
    try:
        if text.startswith(b"<"):
            if _FORBIDDEN_XML.search(text):
                raise FetchError("허용하지 않는 XML 선언")
            root = ET.fromstring(text)
            return {root.tag: _xml_to_value(root)}
        return json.loads(text.decode("utf-8"))
    except FetchError:
        raise
    except (ET.ParseError, ValueError):
        raise FetchError("응답을 해석하지 못함") from None


def walk(obj: Any, path: str | tuple[str, ...] | None) -> Any:
    """점으로 이은 경로를 따라간다. 경로가 여러 개면 값이 있는 첫 경로를 쓴다. 없으면 None."""
    if path is None or obj is None:
        return None
    if isinstance(path, tuple):
        for candidate in path:
            found = walk(obj, candidate)
            if found is not None:
                return found
        return None
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def as_list(value: Any) -> list:
    """XML은 항목이 하나면 dict, 여럿이면 list로 온다. 항상 list로 맞춘다."""
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


# ---------------------------------------------------------------- 재시도
def fetch_parsed(http_get: HttpGet, url: str, *, label: str, sleep: Callable[[float], None] | None = None,
                 retries: int = MAX_RETRIES, base_delay: float = BACKOFF_BASE_SECONDS,
                 timeout: float = HTTP_TIMEOUT_SECONDS) -> tuple[bytes, Any]:
    """GET 후 해석까지 한다. 실패하면 지수 백오프로 `retries`번까지 다시 부르고, 그래도 안 되면 FetchError.

    돌려주는 값은 (원본 본문, 해석한 값). label은 로그에 쓸 이름으로 URL이나 키를 넣지 않는다.
    """
    last = "알 수 없음"
    for attempt in range(retries + 1):
        try:
            body = http_get(url, timeout)
            return body, parse_body(body)
        except Exception as e:  # 호출 함수가 무엇을 던져도 같은 방식으로 다룬다
            last = str(e) if isinstance(e, FetchError) else type(e).__name__
            log.warning("호출 실패 label=%s attempt=%d/%d reason=%s", label, attempt + 1, retries + 1, last)
            if attempt < retries:
                # 대기 함수는 호출 때 고른다. 테스트가 time.sleep을 바꿔 끼울 수 있다
                (sleep or time.sleep)(base_delay * (2 ** attempt))
    raise FetchError(f"{label}: {retries + 1}번 시도했으나 실패 ({last})")
