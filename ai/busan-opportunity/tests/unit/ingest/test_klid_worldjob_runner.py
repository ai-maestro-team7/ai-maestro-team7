"""runner.py·source.py: 지방공공기관·해외취업 수집. 네트워크는 부르지 않는다 (conftest의 FakeApi)."""

import json
import logging

from unit.ingest.conftest import KLID_NO_DATA, SECRET_VALUES, param

from opportunity.ingest import klid
from opportunity.ingest.field_maps import KLID
from opportunity.ingest.http import KeyCache
from opportunity.ingest.runner import ALL_SOURCES, REGION_CODES_KEY, run_ingest
from opportunity.store.memory import MemorySecrets

DAY = "2026-11-21"
AS_OF = "2026-11-21T04:30:00+09:00"


def run(config, catalog, raw_store, secrets, api, sources):
    return run_ingest(config, catalog, raw_store, secrets, sources=sources, as_of=AS_OF, http_get=api)


def test_new_sources_are_in_the_default_list():
    assert "klid" in ALL_SOURCES and "worldjob" in ALL_SOURCES


def test_klid_calls_each_sido_once_without_paging(config, catalog, raw_store, secrets, api):
    report = run(config, catalog, raw_store, secrets, api, ("klid",))
    k = report["sources"]["klid"]
    assert (k["status"], k["listed"], k["normalized"], k["created"], k["skipped"]) == ("OK", 6, 6, 6, {})
    assert k["warnings"] == [] and k["failedPages"] == 0  # 데이터 없음(resultCode=3)은 경고가 아니다
    assert k["detailFetched"] == 0
    calls = [u for u in api.calls if "openXmlEmployInfo" in u]
    assert [param(u, "sidoCd") for u in calls] == list(KLID["region_codes"])
    assert all(param(u, "pageNo") is None and param(u, "type") == "xml" for u in calls)
    assert catalog.get_latest("klid-80978").is_busan and catalog.get_latest("klid-81061").is_capital_area
    assert catalog.get_latest("klid-80978").org_type == "LOCAL_PUBLIC"
    keys = raw_store.list("")
    assert f"raw/klid/{DAY}/sido007002-0001.xml" in keys and f"raw/klid/{DAY}/sido007005-0001.xml" in keys


def test_klid_uses_region_code_seed_for_sigungu(config, catalog, raw_store, secrets, api):
    raw_store.put(REGION_CODES_KEY, json.dumps({"26000": "부산", "26230": "부산 부산진구"}).encode("utf-8"))
    run(config, catalog, raw_store, secrets, api, ("klid",))
    region = catalog.get_latest("klid-80978").work_region
    assert (region.sigungu, region.label) == ("26230", "부산 부산진구")


def test_klid_twice_keeps_counts(config, catalog, raw_store, secrets, api):
    run(config, catalog, raw_store, secrets, api, ("klid",))
    again = run(config, catalog, raw_store, secrets, api, ("klid",))["sources"]["klid"]
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 6)


def test_klid_error_code_counts_as_failed_page(config, catalog, raw_store, secrets):
    bad = KLID_NO_DATA.replace(b"<resultCode>3</resultCode>", b"<resultCode>99</resultCode>")

    def http_get(url, timeout):
        return bad

    report = run_ingest(config, catalog, raw_store, secrets, sources=("klid",), as_of=AS_OF, http_get=http_get)
    k = report["sources"]["klid"]
    assert k["status"] == "FAILED" and k["failedPages"] == len(KLID["region_codes"])
    assert "결과 코드 99" in k["warnings"][0]


def test_klid_fetch_all_with_chosen_sidos(raw_store, secrets, api):
    client = klid.client(KeyCache(secrets), raw_store, day=DAY, http_get=api)
    pages = klid.fetch_all(client, ["007002"])
    assert len(pages.records) == 3 and pages.pages == 1 and api.count("openXmlEmployInfo") == 1


def test_worldjob_pages_and_duplicates(config, catalog, raw_store, secrets, api, worldjob_pages):
    report = run(config, catalog, raw_store, secrets, api, ("worldjob",))
    w = report["sources"]["worldjob"]
    assert (w["status"], w["listed"], w["normalized"], w["duplicates"], w["created"]) == ("OK", 5, 4, 1, 4)
    assert w["pages"] == 2 and w["detailFetched"] == 0
    calls = [u for u in api.calls if "worldjob31" in u]
    assert [param(u, "pageNo") for u in calls] == ["1", "2"] and param(calls[0], "numOfRows") == "3"
    # 해외취업은 다른 계정 키를 쓴다
    assert all(SECRET_VALUES["BUSAN_PUBLIC_JOBS_KEY_ENCODED"] in u for u in calls)
    overseas = [catalog.get_latest(i) for i in catalog.latest if i.startswith("wj-")]
    assert sum(r.is_overseas for r in overseas) == 3 and not any(r.is_busan for r in overseas)
    assert f"raw/worldjob/{DAY}/list-0001.xml" in raw_store.list("")


def test_worldjob_without_team_key_fails_alone(config, catalog, raw_store, api, worldjob_pages, caplog):
    values = {k: v for k, v in SECRET_VALUES.items() if k != "BUSAN_PUBLIC_JOBS_KEY_ENCODED"}
    with caplog.at_level(logging.INFO):
        report = run(config, catalog, raw_store, MemorySecrets(values), api, ("worldjob", "klid"))
    assert report["sources"]["worldjob"]["status"] == "FAILED"
    assert report["sources"]["klid"]["status"] == "OK"
    text = json.dumps(report, ensure_ascii=False) + caplog.text
    assert all(v not in text for v in SECRET_VALUES.values())
