"""http.py: 키 인코딩, 재시도, 키 캐시, 오류에 URL이 새지 않는지."""

import logging
import urllib.error

import pytest

from opportunity.ingest import http
from opportunity.ingest.http import FetchError, KeyCache, build_url, encode_key, fetch_parsed, parse_body, walk
from opportunity.store.memory import MemorySecrets


def test_encode_key_keeps_already_encoded_value():
    assert encode_key("AB%2BCD%2F%3D%3D") == "AB%2BCD%2F%3D%3D"


def test_encode_key_encodes_decoded_value_once():
    assert encode_key("AB+CD/==") == "AB%2BCD%2F%3D%3D"
    assert encode_key("plainKey123") == "plainKey123"


def test_build_url_does_not_double_encode_key():
    url = build_url("https://x.invalid/api", key_param="serviceKey", key="AB%2BCD%3D%3D",
                    params={"pageNo": 1, "q": "부산 청년", "skip": None})
    assert url.startswith("https://x.invalid/api?serviceKey=AB%2BCD%3D%3D&")
    assert "%252B" not in url and "pageNo=1" in url and "skip" not in url
    assert "q=%EB%B6%80%EC%82%B0+%EC%B2%AD%EB%85%84" in url


def test_retries_three_times_with_exponential_backoff():
    calls, waited = [], []

    def failing(url, timeout):
        calls.append(timeout)
        raise OSError(f"boom {url}")

    with pytest.raises(FetchError) as caught:
        fetch_parsed(failing, "https://x.invalid/?authKey=SECRET", label="work24:list:p1", sleep=waited.append)
    assert len(calls) == 4  # 처음 한 번과 다시 부르기 세 번
    assert waited == [1.0, 2.0, 4.0]
    assert set(calls) == {5}  # 타임아웃 5초
    assert "SECRET" not in str(caught.value) and "x.invalid" not in str(caught.value)


def test_succeeds_when_a_retry_works():
    state = {"n": 0}

    def flaky(url, timeout):
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("temporary")
        return b'{"ok": 1}'

    waited = []
    body, parsed = fetch_parsed(flaky, "https://x.invalid/", label="t", sleep=waited.append)
    assert parsed == {"ok": 1} and state["n"] == 3 and waited == [1.0, 2.0]


def test_unparseable_body_is_retried_then_fails():
    waited = []
    with pytest.raises(FetchError):
        fetch_parsed(lambda u, t: b"<html>not xml", "https://x.invalid/", label="t", sleep=waited.append)
    assert len(waited) == 3


def test_failure_logs_do_not_contain_url_or_key(caplog):
    def failing(url, timeout):
        raise OSError(url)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(FetchError):
            fetch_parsed(failing, "https://x.invalid/?authKey=TOPSECRET", label="work24:list:p1", sleep=lambda s: None)
    assert "TOPSECRET" not in caplog.text and "x.invalid" not in caplog.text
    assert "work24:list:p1" in caplog.text


def test_default_http_get_hides_url(monkeypatch):
    def boom(request, timeout):
        raise urllib.error.URLError(f"cannot reach {request.full_url}")

    monkeypatch.setattr(http.urllib.request, "urlopen", boom)
    with pytest.raises(FetchError) as caught:
        http.default_http_get("https://x.invalid/?authKey=TOPSECRET", 5)
    assert "TOPSECRET" not in str(caught.value) and caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_key_cache_holds_five_minutes():
    secrets = MemorySecrets({"K": "v1"})
    now = {"t": 1000.0}
    cache = KeyCache(secrets, monotonic=lambda: now["t"])
    assert cache.get("K") == "v1"
    secrets.values["K"] = "v2"
    now["t"] += 299
    assert cache.get("K") == "v1"  # 5분 안에는 다시 읽지 않는다
    now["t"] += 2
    assert cache.get("K") == "v2"


def test_parse_body_json_and_xml():
    assert parse_body(b'\xef\xbb\xbf{"a": [1]}') == {"a": [1]}
    parsed = parse_body("<r><i><n>1</n></i><i><n>2</n></i><t>합계</t></r>".encode())
    assert parsed == {"r": {"i": [{"n": "1"}, {"n": "2"}], "t": "합계"}}


def test_parse_body_rejects_entity_declarations():
    with pytest.raises(FetchError):
        parse_body(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(FetchError):
        parse_body(b"")


def test_walk_tries_candidates_in_order():
    data = {"a": {"b": 1}, "c": 2}
    assert walk(data, "a.b") == 1 and walk(data, ("x.y", "c")) == 2 and walk(data, "a.z") is None
