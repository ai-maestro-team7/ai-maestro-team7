"""프론트에 넘긴 가짜 응답이 응답 모델과 맞는지 확인한다. 모델을 바꾸면 mocks도 다시 만든다."""

import importlib.util
import json
import re
from pathlib import Path

MOCKS = Path(__file__).parents[2] / "mocks"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_mocks", MOCKS / "build_mocks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mock_files_match_models():
    built = load_builder().build()
    assert built
    for name, body in built.items():
        on_disk = json.loads((MOCKS / f"{name}.json").read_text(encoding="utf-8"))
        assert on_disk == body, f"{name}.json을 다시 만들어야 한다 (python mocks/build_mocks.py)"


def test_mock_keys_are_camel_case():
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert "_" not in key or key.isupper(), key
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in MOCKS.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))


def test_every_rest_route_has_a_mock():
    """rest_handler의 모든 경로에 가짜 응답 파일이 있다. 파일 이름은 `메서드_경로`(`<x>`는 id)이다."""
    source = (Path(__file__).parents[2] / "src/opportunity/api/rest_handler.py").read_text(encoding="utf-8")
    routes = re.findall(r'@app\.(get|post|put|delete)\(f"\{PREFIX\}/([^"]+)"\)', source)
    assert len(routes) >= 20
    for method, path in routes:
        name = method.upper() + "_" + re.sub(r"<[^>]+>", "id", path).replace("/", "_")
        assert (MOCKS / f"{name}.json").exists(), f"{name}.json이 없다 ({method} {path})"


def test_no_orphan_mock_files():
    built = load_builder().build()
    assert {p.stem for p in MOCKS.glob("*.json")} == set(built)


def read(name: str) -> dict:
    return json.loads((MOCKS / f"{name}.json").read_text(encoding="utf-8"))


def test_ask_mocks_cover_answered_and_unanswered():
    for name in ("POST_postings_id_ask", "POST_policies_ask", "POST_policies_id_ask"):
        body = read(name)
        assert body["answered"] is True and body["answer"] and body["sources"]
        assert all(s["quote"] for s in body["sources"])
    for name in ("POST_postings_id_ask_unanswered", "POST_policies_ask_unanswered"):
        body = read(name)
        assert body["answered"] is False and "answer" not in body and body["notice"]


def test_feed_mock_shows_optional_fields_both_ways():
    cards = {c["jobPostingId"]: c for c in read("GET_postings")["items"]}
    assert any("commuteMinutes" in c for c in cards.values()) and any("commuteMinutes" not in c for c in cards.values())
    overseas = [c for c in cards.values() if c["workRegion"]["overseas"]]
    assert overseas and overseas[0]["workRegion"]["country"] and not overseas[0]["isBusan"] and not overseas[0]["isCapitalArea"]
    assert any(c["salary"].get("min") and "max" not in c["salary"] for c in cards.values())


def test_busan_detail_mock_has_local_life_and_others_do_not():
    life = read("GET_postings_id_busan")["localLife"]
    assert life["commuteMinutes"] and len(life["festivals"]) == 2 and len(life["transit"]) == 3
    assert all(f["source"] and f["asOf"] for f in life["festivals"])
    assert all(t["source"] and t["asOf"] for t in life["transit"])
    assert "localLife" not in read("GET_postings_id")


def test_companies_mock_has_source_and_notice():
    body = read("GET_companies")
    assert body["notice"] and body["basis"]
    assert all(c["source"] and c["asOf"] for c in body["items"])
