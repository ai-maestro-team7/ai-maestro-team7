"""수집 테스트 준비. 빈 메모리 저장소와 가짜 공공 API를 쓴다. 네트워크는 부르지 않는다."""

import re
import time
from pathlib import Path

import pytest

from opportunity.ingest.field_maps import WORK24
from opportunity.store.memory import MemoryCatalog, MemoryRawStore, MemorySecrets

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = "2026-11-21T10:00:00+09:00"
SECRET_VALUES = {
    "WORK24_AUTH_KEY": "W24-SECRET-AAAA1111",
    "DATA_GO_KR_SERVICE_KEY": "GOKR%2BSECRET%2FBBBB2222%3D%3D",  # 공공데이터포털은 URL 인코딩된 키를 준다
    "YOUTHCENTER_API_KEY": "YTH-SECRET-CCCC3333",
}


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def param(url: str, name: str) -> str | None:
    found = re.search(rf"[?&]{re.escape(name)}=([^&]*)", url)
    return found.group(1) if found else None


class FakeApi:
    """URL을 보고 정해 둔 응답을 돌려주는 가짜 `http_get`. 호출한 URL은 calls에 남는다."""

    def __init__(self):
        self.calls: list[str] = []
        self.timeouts: list[float] = []
        self.failing: set[str] = set()  # 이 글이 URL에 들어 있으면 늘 실패한다

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append(url)
        self.timeouts.append(timeout)
        if any(needle in url for needle in self.failing):
            raise OSError(f"연결 실패 {url}")  # 일부러 URL을 담아 호출 쪽이 새지 않게 하는지 본다
        if "callOpenApiSvcInfo210L01" in url:
            return fixture_bytes(f"work24_list_p{param(url, 'startPage')}.xml")
        if "callOpenApiSvcInfo210D01" in url:
            return fixture_bytes(f"work24_detail_{param(url, 'wantedAuthNo')}.xml")
        if "recruitment/list" in url:
            return fixture_bytes("alio_list_p1.json")
        if "recruitment/detail" in url:
            return fixture_bytes(f"alio_detail_{param(url, 'sn')}.json")
        if "getPlcy" in url:
            return fixture_bytes("youthcenter_list_p1.json")
        raise AssertionError("가짜 API에 없는 주소")

    def count(self, needle: str) -> int:
        return sum(needle in url for url in self.calls)


@pytest.fixture
def api():
    return FakeApi()


@pytest.fixture
def catalog():
    return MemoryCatalog()


@pytest.fixture
def raw_store():
    return MemoryRawStore()


@pytest.fixture
def secrets():
    return MemorySecrets(dict(SECRET_VALUES))


@pytest.fixture
def sleeps(monkeypatch):
    """대기 시간을 기록만 하고 실제로 쉬지 않는다."""
    waited: list[float] = []
    monkeypatch.setattr(time, "sleep", waited.append)
    return waited


@pytest.fixture
def small_pages(monkeypatch):
    """고용24 목록을 페이지당 2건으로 줄여 두 페이지를 돌게 한다."""
    monkeypatch.setitem(WORK24["list"], "page_size", 2)
    return 2


@pytest.fixture
def as_of():
    return AS_OF
