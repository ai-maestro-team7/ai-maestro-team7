"""부산 주변 생활 정보 원본 읽기 (`ingest/local_data.py`). fixture는 실제 원본에서 일부만 잘라 왔다."""

import json
import shutil
from pathlib import Path

import pytest

from opportunity.ingest import local_data as ld
from opportunity.models.region import FestivalInfo, LocalLifeData, TransitInfo

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


DAY = "2026-11-20"


def festivals():
    return ld.parse_festivals(fixture_bytes("local_festival_p01.json"), as_of=DAY)


def test_festival_fields_from_real_sample():
    rows = festivals()
    assert [f.festival_id for f in rows] == ["fest-71", "fest-253", "fest-329", "fest-1705"]
    assert [f.title for f in rows] == ["부산바다축제", "수국축제", "센텀맥주축제", "별바다부산 나이트페스타"]
    sea = rows[0]
    assert sea.gugun == "수영구" and sea.place == "다대포 해수욕장 일원"
    assert sea.period == "2025. 8. 1. ~ 8. 3."  # 기간은 원문 그대로
    assert sea.traffic.startswith("도시철도 1호선 다대포해수욕장역")
    assert sea.url == "http://www.bfo.or.kr/festival_sea/info/01.asp?MENUDIV=1"
    assert rows[1].url is None  # 빈 홈페이지
    assert all(f.source == ld.FESTIVAL_SOURCE and f.as_of == DAY for f in rows)


def test_festival_drops_phone_number():
    raw = fixture_bytes("local_festival_p01.json").decode()
    assert "051-713-5000" in raw  # 원본에는 연락처가 있다
    dumped = json.dumps([f.to_api() for f in festivals()], ensure_ascii=False)
    assert "051-" not in dumped and "CNTCT" not in dumped and "tel" not in dumped.lower()


@pytest.mark.parametrize("raw, title", [
    ("부산불꽃축제(한, 영, 중간, 중번, 일)", "부산불꽃축제"),
    ("부산푸드필름페스타(한, 영)", "부산푸드필름페스타"),
    ("부산국제마케팅광고제(한)", "부산국제마케팅광고제"),
    ("2026 원아시아페스티벌(BOF)", "2026 원아시아페스티벌(BOF)"),
    ("택슐랭", "택슐랭"),
])
def test_festival_title_strips_language_marks_only(raw, title):
    assert ld.festival_title(raw) == title


def test_festival_url_needs_scheme():
    body = {"getFestivalKr": {"item": [{"UC_SEQ": 1, "MAIN_TITLE": "가", "HOMEPAGE_URL": "www.festivalbusan.com/x/"},
                                       {"UC_SEQ": 2, "MAIN_TITLE": ""}]}}
    rows = ld.parse_festivals(body, as_of=DAY)
    assert [f.festival_id for f in rows] == ["fest-1"] and rows[0].url is None


def test_subway_lines():
    row = ld.parse_subway_lines(fixture_bytes("local_busan_subway_lines_20210414.csv"))
    assert row.value == "2개 노선 · 1호선 40개 역 · 2호선 43개 역"
    assert row.source == ld.SUBWAY_SOURCE and row.as_of == "2021-04-14"


def test_bus_stops_busan_row_only():
    row = ld.parse_bus_stops(fixture_bytes("local_bus_stops_by_sido_20241231.csv"), as_of="2024-12-31")
    assert row.value == "3,888곳 (지붕 있는 정류장 2,963곳)" and row.source == ld.BUS_STOP_SOURCE


def test_bus_routes_count_and_sum():
    row = ld.parse_bus_routes(fixture_bytes("local_busan_bus_route_usage_20251231.csv"), as_of="2025-12-31")
    total = 3322542 + 44467 + 1115291 + 2409
    assert row.value == f"4개 노선 · 교통카드 이용 연 {total:,}건" and row.source == ld.BUS_ROUTE_SOURCE


def raw_tree(tmp_path):
    fest = tmp_path / "busan_festival" / DAY
    files = tmp_path / "files" / DAY
    fest.mkdir(parents=True)
    files.mkdir(parents=True)
    shutil.copy(FIXTURES / "local_festival_p01.json", fest / "festival_p01.json")
    for name in ("busan_subway_lines_20210414.csv", "bus_stops_by_sido_20241231.csv",
                 "busan_bus_route_usage_20251231.csv"):
        shutil.copy(FIXTURES / f"local_{name}", files / name)
    return tmp_path


def test_build_from_folder_takes_as_of_from_file(tmp_path):
    data = ld.build_local_life_data(raw_tree(tmp_path), DAY)
    assert len(data.festivals) == 4
    assert [(t.label, t.as_of) for t in data.transit] == [
        (ld.SUBWAY_LABEL, "2021-04-14"), (ld.BUS_ROUTE_LABEL, "2025-12-31"), (ld.BUS_STOP_LABEL, "2024-12-31")]
    assert data.commute_minutes == {} and data.commute_source is None


def test_cli_writes_seed_and_roundtrips(tmp_path, capsys):
    raw = raw_tree(tmp_path / "raw")
    assert ld.main(["--raw", str(raw), "--day", DAY, "--out", str(tmp_path)]) == 0
    seed = tmp_path / "seed" / "local_life.json"
    loaded = ld.load_local_life(seed)
    assert len(loaded.festivals) == 4 and len(loaded.transit) == 3
    assert ld.load_local_life(seed.read_bytes()) == loaded
    out = capsys.readouterr().out
    assert '"festivals": 4' in out and "051-" not in out


def test_missing_files_give_empty_data(tmp_path):
    assert ld.build_local_life_data(tmp_path, DAY) == LocalLifeData()


# ---------------------------------------------------------------- 출처·기준일 검사
def test_loader_rejects_festival_without_source():
    bad = LocalLifeData(festivals=[FestivalInfo(festival_id="fest-1", title="가", source="", as_of=DAY)])
    with pytest.raises(ld.LocalDataError):
        ld.load_local_life(bad.to_api())


def test_loader_rejects_transit_without_as_of():
    bad = LocalLifeData(transit=[TransitInfo(label="가", value="1", source="출처", as_of=" ")])
    with pytest.raises(ld.LocalDataError):
        ld.load_local_life(bad.to_api())


def test_loader_rejects_missing_fields():
    with pytest.raises(ld.LocalDataError):
        ld.load_local_life({"festivals": [{"festivalId": "fest-1", "title": "가"}]})


def test_loader_rejects_commute_without_source():
    with pytest.raises(ld.LocalDataError):
        ld.load_local_life({"commuteMinutes": {"26290>26350": 40}})
    ok = ld.load_local_life({"commuteMinutes": {"26290>26350": 40}, "commuteSource": "길찾기", "commuteAsOf": DAY})
    assert ok.commute_minutes == {"26290>26350": 40}


# ---------------------------------------------------------------- 통근 CSV
def test_load_commute_csv(tmp_path):
    path = tmp_path / "commute.csv"
    path.write_text("from_sigungu,to_sigungu,minutes\n26290,26350,42\n26380,26350,55\n", encoding="utf-8")
    assert ld.load_commute_csv(path) == {"26290>26350": 42, "26380>26350": 55}


@pytest.mark.parametrize("row", ["2629,26350,42", "26290,26350,약40", "26290,26350,0"])
def test_load_commute_csv_rejects_bad_rows(tmp_path, row):
    path = tmp_path / "commute.csv"
    path.write_text(f"from_sigungu,to_sigungu,minutes\n{row}\n", encoding="utf-8")
    with pytest.raises(ld.LocalDataError):
        ld.load_commute_csv(path)


def test_cli_commute_needs_source(tmp_path):
    path = tmp_path / "commute.csv"
    path.write_text("from_sigungu,to_sigungu,minutes\n26290,26350,42\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ld.main(["--raw", str(tmp_path), "--day", DAY, "--commute", str(path)])
    assert ld.main(["--raw", str(tmp_path), "--day", DAY, "--commute", str(path), "--commute-source", "길찾기",
                    "--commute-as-of", DAY, "--out", str(tmp_path)]) == 0
    assert ld.load_local_life(tmp_path / "seed" / "local_life.json").commute_minutes == {"26290>26350": 42}
