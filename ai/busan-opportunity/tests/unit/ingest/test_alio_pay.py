"""알리오 경영공시 「직원 평균보수」 수집 (B-D11).

보고서 fixture는 2026-11-21에 받은 부산항만공사 보고서다. 공시 담당자 표(이름·전화번호)는 잘라 냈다.
"""

import json
from pathlib import Path

from opportunity.ingest.alio_pay import fetch_org_pays, parse_report, to_org_pay
from opportunity.ingest.field_maps import ALIO_PAY, ALIO_PAY_SOURCE
from opportunity.ingest.http import FetchError
from opportunity.ingest.runner import run_ingest
from opportunity.store.memory import MemoryCatalog

FIXTURE = Path(__file__).parent / "fixtures" / "alio_pay_report_C0072.html"
ORG = {"apbaId": "C0072", "apbaNa": "부산항만공사", "typeNa": "공기업(준시장형)", "jidtNa": "해양수산부",
       "disclosureNo": "2026041603162610"}


def report_html():
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_report_reads_regular_staff_table_only():
    parsed = parse_report(report_html())
    assert [(y.year, y.average, y.budget) for y in parsed.years] == [
        (2021, 7601, False), (2022, 7669, False), (2023, 8193, False), (2024, 8510, False), (2025, 9118, False),
        (2026, 8511, True)]  # 천 원 → 만 원 반올림. 무기계약직 표(2025년 9,588만 원)는 읽지 않는다
    assert parsed.tenure_by_year[2025] == 132
    assert parsed.as_of == "2025-12-31"


def test_parse_report_without_regular_table_is_none():
    assert parse_report("<table><tr><td>정규직(무기계약직)</td></tr><tr><td>1인당 평균 보수액</td><td>1</td></tr></table>") is None
    assert parse_report("") is None


def test_to_org_pay_uses_latest_settled_year():
    pay = to_org_pay(ORG, parse_report(report_html()), checked_day="2026-11-21")
    assert (pay.org_id, pay.name, pay.latest_year, pay.latest_average, pay.tenure_months) == (
        "C0072", "부산항만공사", 2025, 9118, 132)
    assert pay.source == ALIO_PAY_SOURCE and pay.as_of == "2025-12-31"
    assert pay.source_url.startswith(ALIO_PAY["page_url"]) and "apbaId=C0072" in pay.source_url


class FakeAlio:
    def __init__(self, orgs, fail_once=(), fail_always=()):
        self.orgs, self.fail_once, self.fail_always = orgs, set(fail_once), set(fail_always)
        self.gets: list[str] = []
        self.posts: list[dict] = []

    def post(self, url, body, timeout):
        assert url == ALIO_PAY["list_url"] and body["reportFormRootNo"] == ALIO_PAY["form"]
        self.posts.append(body)
        return json.dumps({"status": "success", "data": {"totalCnt": len(self.orgs), "organList": self.orgs}}).encode()

    def get(self, url, timeout):
        assert timeout == 5
        self.gets.append(url)
        no = url.split("disclosureNo=")[1]
        if no in self.fail_always or (no in self.fail_once and self.gets.count(url) == 1):
            raise FetchError("요청 실패 (TimeoutError)")
        return report_html().encode("utf-8")


def test_fetch_retries_once_and_skips_missing_reports():
    orgs = [ORG, {**ORG, "apbaId": "C0001", "apbaNa": "가", "disclosureNo": "D1"},
            {**ORG, "apbaId": "C0002", "apbaNa": "나", "disclosureNo": "D2"},
            {**ORG, "apbaId": "C0003", "apbaNa": "다", "disclosureNo": None}]
    alio = FakeAlio(orgs, fail_once={"D1"}, fail_always={"D2"})
    pays, stats = fetch_org_pays(alio.get, alio.post, timeout=5, sleep=lambda s: None)
    assert [p.org_id for p in pays] == ["C0072", "C0001"]  # D1은 다시 시도해 성공, D2는 두 번 다 실패
    assert stats == {"listed": 4, "noReport": 1, "failed": 1, "unparsed": 0,
                     "warnings": ["보고서 실패 C0002: 요청 실패 (TimeoutError)"]}
    assert len(alio.gets) == 5 and len(alio.posts) == 1


class FakeRaw:
    def __init__(self):
        self.files = {}

    def put(self, key, body):
        self.files[key] = body

    def get(self, key):
        return self.files.get(key)


def test_runner_writes_org_pay_and_numbers_only(config):
    catalog, raw = MemoryCatalog(), FakeRaw()
    alio = FakeAlio([ORG])
    report = run_ingest(config, catalog, raw, secrets=None, sources=["alio_pay"], as_of="2026-11-23T05:00:00+09:00",
                        http_get=alio.get, http_post=alio.post, sleep=lambda s: None)
    assert report["sources"]["alio_pay"]["status"] == "OK" and report["sources"]["alio_pay"]["normalized"] == 1
    assert [p.latest_average for p in catalog.org_pays()] == [9118]
    saved = json.loads(raw.files["raw/alio_pay/2026-11-23/org_pays.json"])
    assert saved[0]["orgId"] == "C0072" and "담당자" not in json.dumps(saved, ensure_ascii=False)
    assert not any(key.endswith(".html") for key in raw.files)  # 보고서 원문은 남기지 않는다
