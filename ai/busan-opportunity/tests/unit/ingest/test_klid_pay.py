"""지방출자·출연기관 직원평균임금 시드 (B-D11). 행정안전부 파일의 연도별 시트를 `OrgPay`로 바꾼다."""

import json

from opportunity.ingest.field_maps import KLID_PAY, KLID_PAY_SOURCE
from opportunity.ingest.klid_pay import load_seed, org_id, org_pays_from_sheets, write_seed
from opportunity.ingest.runner import run_ingest
from opportunity.store.memory import MemoryCatalog

HEAD = ("연번", "설립지자체", "기관유형", "기관명", "기본급", "급여성복리후생비", "제수당", "성과급", "직원수",
        "평균근수년", "평균근속월", "1인당 평균임금")


def row(founder, kind, name, won, years=0, months=0):
    return (1, founder, kind, name, 0, 0, 0, 0, 10, years, months, won)


def test_rows_become_org_pay_in_manwon_with_latest_year():
    sheets = {
        2024: [HEAD, row("부산광역시", "출연기관", "가상문화재단", 47_412_300, 5, 1)],
        2025: [HEAD, row("부산광역시", "출연기관", "가상문화재단", 53_012_000, 6, 2),
               row("부산광역시", "출자기관", "(주)가상센터", 0)],  # 0은 값이 없다
    }
    pays = org_pays_from_sheets(sheets)
    assert [p.name for p in pays] == ["가상문화재단"]
    pay = pays[0]
    assert [(y.year, y.average) for y in pay.years] == [(2024, 4741), (2025, 5301)]  # 원 → 만 원 반올림
    assert (pay.latest_year, pay.latest_average, pay.tenure_months) == (2025, 5301, 74)
    assert (pay.org_type, pay.ministry, pay.year_note) == ("지방출연기관", "부산광역시", "")
    assert pay.org_id == org_id("부산광역시", "가상문화재단") and pay.org_id.startswith("klid-")
    assert pay.source == KLID_PAY_SOURCE and pay.source_url == KLID_PAY["page_url"]


def test_implausible_years_and_test_rows_are_dropped():
    sheets = {
        2024: [HEAD, row("서울특별시 구로구", "출연기관", "가상장학회", 31_800_000)],
        2025: [HEAD, row("서울특별시 구로구", "출연기관", "가상장학회", 3_000_000),  # 300만 원: 그해만 뺀다
               row("서울특별시 중랑구", "출자기관", "통합테스트출자출연", 40_000_000)],
    }
    pays = org_pays_from_sheets(sheets)
    assert [(p.name, p.latest_year, p.latest_average) for p in pays] == [("가상장학회", 2024, 3180)]


def test_seed_roundtrip(tmp_path):
    pays = org_pays_from_sheets({2025: [HEAD, row("부산광역시", "출연기관", "가상재단", 50_000_000, 3, 0)]})
    path = tmp_path / "seed.json"
    assert write_seed(pays, path) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["source"] == KLID_PAY_SOURCE
    assert load_seed(path) == pays


def test_packaged_seed_covers_busan_institutions():
    pays = {p.name: p for p in load_seed()}
    assert len(pays) > 700
    for name in ("부산의료원", "부산문화재단", "(주)벡스코", "부산테크노파크"):
        assert pays[name].ministry == "부산광역시" and pays[name].latest_average >= KLID_PAY["min_plausible"]
    assert not any("테스트" in n for n in pays)


class Raw:
    def __init__(self):
        self.files = {}

    def put(self, key, body):
        self.files[key] = body

    def get(self, key):
        return self.files.get(key)


def test_runner_loads_seed_without_network(config):
    catalog = MemoryCatalog()
    report = run_ingest(config, catalog, Raw(), secrets=None, sources=["klid_pay"], as_of="2026-11-23T05:00:00+09:00",
                        http_get=lambda url, timeout: (_ for _ in ()).throw(AssertionError("외부 호출 없음")))
    assert report["sources"]["klid_pay"]["status"] == "OK"
    assert len(catalog.org_pays()) == report["sources"]["klid_pay"]["normalized"] > 700
