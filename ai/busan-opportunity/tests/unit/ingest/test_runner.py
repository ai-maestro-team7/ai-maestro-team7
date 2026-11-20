"""runner.py: 출처별 수집, 출처 실패 격리, 재시도, 키 보안."""

import json
import logging

from opportunity.ingest.field_maps import WORK24
from opportunity.ingest.runner import run_ingest
from opportunity.store.memory import MemorySecrets

DAY = "2026-11-21"
ALL = ("work24", "alio", "youthcenter")


def run(config, catalog, raw_store, secrets, api, *, sources=ALL, as_of="2026-11-21T04:30:00+09:00"):
    return run_ingest(config, catalog, raw_store, secrets, sources=sources, as_of=as_of, http_get=api)


def test_full_run_loads_postings_and_policies(config, catalog, raw_store, secrets, api, small_pages):
    report = run(config, catalog, raw_store, secrets, api)
    w, a, y = (report["sources"][n] for n in ALL)
    assert (w["status"], w["listed"], w["normalized"], w["created"]) == ("OK", 3, 3, 3)
    assert w["pages"] == 2 and w["detailFetched"] == 2  # 부산·서울 공고만. 근무지 미상은 부르지 않는다
    assert (a["listed"], a["normalized"], a["created"], a["skipped"]) == (3, 2, 2, {"bad_id": 1})
    assert (y["listed"], y["normalized"], y["created"], y["skipped"]) == (8, 8, 8, {})
    assert report["ok"] is True
    assert catalog.get_latest("wk24-K000000001").is_busan and catalog.get_latest("alio-2026001").is_busan
    assert catalog.get_snapshot("wk24-K000000001", catalog.get_latest("wk24-K000000001").snapshot_id
                                ).job_description.startswith("데이터 분석과 SQL")
    assert len(catalog.policies) == 8
    assert catalog.get_policy("ythc-20260923005400113568").region_key() == "26"  # 여러 시·도 정책은 부산이 먼저
    assert catalog.data_as_of() == "2026-11-21T04:30:00+09:00"


def test_raw_responses_and_run_report_are_stored(config, catalog, raw_store, secrets, api, small_pages):
    run(config, catalog, raw_store, secrets, api)
    keys = raw_store.list("")
    assert f"raw/work24/{DAY}/list-0001.xml" in keys and f"raw/work24/{DAY}/list-0002.xml" in keys
    assert f"raw/work24/{DAY}/detail-K000000001.xml" in keys
    assert f"raw/alio/{DAY}/list-0001.json" in keys and f"raw/youthcenter/{DAY}/list-0001.json" in keys
    assert raw_store.get(f"raw/work24/{DAY}/list-0001.xml") == (
        __import__("pathlib").Path(__file__).parent / "fixtures" / "work24_list_p1.xml").read_bytes()  # 원본 그대로
    saved = json.loads(raw_store.get(f"runs/{DAY}.json"))
    assert saved["sources"]["work24"]["created"] == 3 and saved["asOf"] == "2026-11-21T04:30:00+09:00"
    assert "_postingIds" not in saved["sources"]["work24"]


def test_t17_running_twice_on_same_day_keeps_counts(config, catalog, raw_store, secrets, api, small_pages):
    run(config, catalog, raw_store, secrets, api)
    snapshots, latest, policies = dict(catalog.snapshots), dict(catalog.latest), dict(catalog.policies)
    report = run(config, catalog, raw_store, secrets, api)
    w, a, y = (report["sources"][n] for n in ALL)
    assert (w["created"], w["updated"], w["unchanged"]) == (0, 0, 3)
    assert (a["created"], a["updated"], a["unchanged"]) == (0, 0, 2)
    assert (y["created"], y["updated"], y["unchanged"]) == (0, 0, 8)
    assert w["needsEnrich"] == [] and a["needsEnrich"] == []
    assert (catalog.snapshots, catalog.latest, catalog.policies) == (snapshots, latest, policies)


def test_failed_page_is_retried_three_times_with_backoff(config, catalog, raw_store, secrets, api, small_pages,
                                                         sleeps):
    api.failing = {"startPage=2"}
    report = run(config, catalog, raw_store, secrets, api, sources=("work24",))
    assert api.count("startPage=2") == 4  # 처음 한 번과 다시 부르기 세 번
    assert sleeps == [1.0, 2.0, 4.0]
    w = report["sources"]["work24"]
    assert w["status"] == "PARTIAL" and w["failedPages"] == 1 and w["listed"] == 2
    assert w["created"] == 2  # 성공한 페이지는 적재한다
    assert any("p2" in text for text in w["warnings"])


def test_one_failing_source_does_not_stop_the_others(config, catalog, raw_store, secrets, api, sleeps):
    api.failing = {"callOpenApiSvcInfo210L01"}
    report = run(config, catalog, raw_store, secrets, api)
    assert report["sources"]["work24"]["status"] == "FAILED"
    assert report["sources"]["alio"]["created"] == 2 and report["sources"]["youthcenter"]["created"] == 8
    assert report["ok"] is False
    assert catalog.data_as_of() == "2026-11-21T04:30:00+09:00"  # 하나라도 성공하면 기준 시각을 올린다


def test_exception_in_a_source_is_isolated(config, catalog, raw_store, api, small_pages):
    secrets = MemorySecrets({"DATA_GO_KR_SERVICE_KEY": "x%2By", "YOUTHCENTER_API_KEY": "k"})  # 고용24 키가 없다
    report = run(config, catalog, raw_store, secrets, api)
    assert report["sources"]["work24"] == {"status": "FAILED", "error": "KeyError"}
    assert report["sources"]["alio"]["created"] == 2


def test_all_sources_failing_does_not_move_data_as_of(config, catalog, raw_store, secrets, api, sleeps):
    api.failing = {"https://"}
    report = run(config, catalog, raw_store, secrets, api)
    assert all(r["status"] == "FAILED" for r in report["sources"].values()) and report["ok"] is False
    assert catalog.data_as_of() is None
    assert json.loads(raw_store.get(f"runs/{DAY}.json"))["ok"] is False  # 실패해도 기록은 남긴다


def test_unknown_source_is_reported(config, catalog, raw_store, secrets, api):
    report = run(config, catalog, raw_store, secrets, api, sources=("nope",))
    assert report["sources"]["nope"]["status"] == "FAILED"


def test_unmappable_response_is_flagged_for_mapping_review(config, catalog, raw_store, secrets, api, monkeypatch):
    monkeypatch.setitem(WORK24["fields"], "external_id", "없는필드")  # 매핑표가 틀린 상황
    report = run(config, catalog, raw_store, secrets, api, sources=("work24",))
    w = report["sources"]["work24"]
    assert w["status"] == "NEEDS_MAPPING" and w["normalized"] == 0 and w["skipped"] == {"missing_id": 2}
    assert raw_store.list("raw/work24/")  # 원본은 남아 있어 매핑표를 고칠 수 있다
    assert catalog.data_as_of() is None


def test_empty_first_page_warns(config, catalog, raw_store, secrets, api):
    api_empty = lambda url, timeout: b"<wantedRoot><total>0</total></wantedRoot>"  # noqa: E731
    report = run(config, catalog, raw_store, secrets, api_empty, sources=("work24",))
    w = report["sources"]["work24"]
    assert w["status"] == "EMPTY" and any("매핑 확인" in text for text in w["warnings"])


def test_run_marks_listed_postings_past_deadline_as_expired(config, catalog, raw_store, secrets, api, small_pages):
    run(config, catalog, raw_store, secrets, api)
    run(config, catalog, raw_store, secrets, api, as_of="2026-12-16T04:30:00+09:00")
    assert catalog.get_latest("wk24-K000000001").is_expired is True  # 마감 12-15
    assert catalog.get_latest("wk24-K000000003").is_expired is True  # 마감 12-01, 근무지 미상
    assert catalog.get_latest("wk24-K000000002").is_expired is False  # 상시 채용
    assert len(catalog.snapshots) == 5  # 지우지 않는다 (work24 3 + alio 2)


def test_run_expires_postings_that_dropped_out_of_the_list(config, catalog, raw_store, secrets, api, small_pages):
    run(config, catalog, raw_store, secrets, api)
    report = run(config, catalog, raw_store, secrets, api, sources=("youthcenter",),
                 as_of="2026-12-16T04:30:00+09:00")  # 이번에는 공고 출처를 부르지 않았다
    assert report["expired"] == 2  # K1(부산, 12-15)과 alio-2026001(부산, 12-10)
    assert catalog.get_latest("wk24-K000000001").is_expired and catalog.get_latest("alio-2026001").is_expired
    assert len(catalog.snapshots) == 5


def test_detail_only_for_busan_and_capital(config, catalog, raw_store, secrets, api, small_pages):
    run(config, catalog, raw_store, secrets, api, sources=("work24",))
    detail_calls = [url for url in api.calls if "210D01" in url]
    assert len(detail_calls) == 2
    assert not any("K000000003" in url for url in detail_calls)


def test_youthcenter_request_has_page_type(config, catalog, raw_store, secrets, api):
    run(config, catalog, raw_store, secrets, api, sources=("youthcenter",))
    url = next(u for u in api.calls if "getPlcy" in u)
    assert "pageType=1" in url and "rtnType=json" in url and "pageNum=1" in url  # pageType이 없으면 e003 오류


def test_region_codes_seed_groups_city_districts(config, catalog, raw_store, secrets, api):
    from opportunity.ingest import codes
    names = codes.region_names((__import__("pathlib").Path(__file__).parent / "fixtures"
                                / "work24_codes_CMCD_1.xml").read_bytes())
    raw_store.put("seed/codes/work24_region_codes.json", json.dumps(names, ensure_ascii=False).encode())
    run(config, catalog, raw_store, secrets, api, sources=("youthcenter",))
    regions = catalog.get_policy("ythc-20261106005400214758").regions  # 청주시 구 4곳
    assert [(r.scope, r.sigungu) for r in regions] == [("SIGUNGU", "43110")]


def test_gangso_companies_are_loaded_per_region(config, catalog, raw_store, secrets, api):
    report = run(config, catalog, raw_store, secrets, api, sources=("work24_gangso",))
    g = report["sources"]["work24_gangso"]
    assert (g["status"], g["listed"], g["normalized"], g["created"], g["skipped"]) == ("OK", 3, 3, 3, {})
    regions = sorted(__import__("re").search(r"region=(\d+)", u).group(1) for u in api.calls if "216L01" in u)
    assert regions == sorted(f"{s}000" for s in [config.data.busan_sido, *config.data.capital_area_sido])
    assert f"raw/work24_gangso/{DAY}/region26000-0001.xml" in raw_store.list("raw/work24_gangso/")
    company = catalog.get_company("biz-6088195805")
    assert company.sido == "26" and company.highlights[0].label == "인재육성형중소기업"
    assert [c.company_id for c in catalog.list_companies("26")] == [
        "biz-1058163269", "biz-6088195805", "biz-6068111231"]  # 이름순
    again = run(config, catalog, raw_store, secrets, api, sources=("work24_gangso",))
    assert again["sources"]["work24_gangso"]["unchanged"] == 3


def test_job_codes_seed_limits_detail_to_demo_families(config, catalog, raw_store, secrets, api, small_pages):
    raw_store.put("seed/codes/work24_job_codes.json", json.dumps(
        {"024101": {"name": "데이터 분석가", "middle": "데이터", "major": "음식·조리"}}).encode())
    report = run(config, catalog, raw_store, secrets, api, sources=("work24",))
    assert report["sources"]["work24"]["detailFetched"] == 0  # 데모 직무군이 아니면 상세를 부르지 않는다
    assert catalog.get_latest("wk24-K000000001").job.major == "음식·조리"


# ---------------------------------------------------------------- 키 보안
def test_keys_never_reach_logs_report_storage_or_errors(config, catalog, raw_store, secrets, api, small_pages,
                                                        sleeps, caplog):
    api.failing = {"startPage=2", "recruitment/list"}  # 실패 경로의 로그와 오류도 본다
    with caplog.at_level(logging.DEBUG):
        report = run(config, catalog, raw_store, secrets, api)
    assert any("SECRET" in url for url in api.calls)  # 호출에는 키가 실제로 들어갔다
    leaked = [value for value in secrets.values.values()]
    leaked += ["GOKR%2BSECRET", "GOKR+SECRET", "BBBB2222"]
    blob = caplog.text + json.dumps(report, ensure_ascii=False) + "\n".join(raw_store.list(""))
    blob += b"".join(raw_store.get(k) for k in raw_store.list("runs/")).decode()
    for secret in leaked:
        assert secret not in blob
    assert "work24.go.kr" not in caplog.text and "youthcenter.go.kr" not in caplog.text


def test_encoded_data_go_kr_key_is_sent_as_issued(config, catalog, raw_store, secrets, api):
    run(config, catalog, raw_store, secrets, api, sources=("alio",))
    url = next(u for u in api.calls if "recruitment/list" in u)
    assert "serviceKey=GOKR%2BSECRET%2FBBBB2222%3D%3D&" in url and "%25" not in url
    assert set(api.timeouts) == {5}


def test_keys_are_read_through_five_minute_cache(config, catalog, raw_store, api, small_pages):
    class CountingSecrets(MemorySecrets):
        def __init__(self, values):
            super().__init__(values)
            self.reads = []

        def get(self, name):
            self.reads.append(name)
            return super().get(name)

    secrets = CountingSecrets({"WORK24_AUTH_KEY": "k"})
    run(config, catalog, raw_store, secrets, api, sources=("work24",))
    assert secrets.reads == ["WORK24_AUTH_KEY"]  # 목록 2페이지와 상세 2건에도 한 번만 읽는다
