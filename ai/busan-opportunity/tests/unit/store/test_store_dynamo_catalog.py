"""DynamoCatalog: moto 테이블로 키 구조, 왕복, GSI 조회, BatchGet, 오류 변환을 확인한다."""

from unittest import mock

import pytest
from botocore.exceptions import ClientError

from opportunity.models import OppError
from opportunity.seeds import demo_world as w
from opportunity.store.dynamo import DynamoCatalog

CATALOG = "team07-catalog"


@pytest.fixture
def memory_world(deps):
    """데모 데이터가 든 메모리 저장소. DynamoDB 구현과 같은 답이 나오는지 견주는 기준이다."""
    return deps.catalog


@pytest.fixture
def loaded(catalog, memory_world):
    """데모 데이터를 DynamoCatalog에 그대로 옮겨 넣는다."""
    for snap in memory_world.snapshots.values():
        catalog.put_snapshot(snap)
    for latest in memory_world.latest.values():
        catalog.put_latest(latest)
    for alts in memory_world.alts.values():
        catalog.put_alts(alts)
    for policy in memory_world.policies.values():
        catalog.put_policy(policy)
    for company in memory_world.companies.values():
        catalog.put_company(company)
    catalog.set_data_as_of(memory_world.data_as_of())
    return catalog


def test_roundtrip_matches_models(loaded, memory_world):
    """스냅샷·LATEST·ALTS·정책·기업이 모델 그대로 돌아온다 (float → Decimal → float 포함)."""
    for (pid, sid), snap in memory_world.snapshots.items():
        assert loaded.get_snapshot(pid, sid) == snap
    for pid, latest in memory_world.latest.items():
        assert loaded.get_latest(pid) == latest
    for pid, alts in memory_world.alts.items():
        assert loaded.get_alts(pid) == alts
    for policy_id, policy in memory_world.policies.items():
        assert loaded.get_policy(policy_id) == policy
    for company_id, company in memory_world.companies.items():
        assert loaded.get_company(company_id) == company
    assert loaded.data_as_of() == w.DATA_AS_OF


def test_missing_items_are_none(catalog):
    assert catalog.get_latest("nope") is None and catalog.get_alts("nope") is None
    assert catalog.get_snapshot("nope", "s") is None and catalog.get_policy("nope") is None
    assert catalog.get_company("nope") is None and catalog.data_as_of() is None


def test_item_layout_follows_db_schema(loaded, raw):
    latest = raw(CATALOG, f"POSTING#{w.BUSAN_DATA}", "LATEST")
    assert latest["GSI1PK"] == "POSTING#26" and latest["GSI1SK"] == loaded.get_latest(w.BUSAN_DATA).closes_at
    assert latest["entityType"] == "PostingLatest" and latest["schemaVersion"]
    assert latest["createdAt"] and latest["updatedAt"] and latest["jobPostingId"] == w.BUSAN_DATA
    snap_id = loaded.get_latest(w.BUSAN_DATA).snapshot_id
    snap = raw(CATALOG, f"POSTING#{w.BUSAN_DATA}", f"SNAP#{snap_id}")
    assert "GSI1PK" not in snap and snap["entityType"] == "PostingSnapshot"
    alts = raw(CATALOG, f"POSTING#{w.SEOUL_DATA}", "ALTS")
    assert alts["candidates"][0]["jobPostingId"] == w.BUSAN_DATA and "GSI1PK" not in alts
    policy = raw(CATALOG, f"POLICY#{w.P_DIDIMDOL}", "META")
    assert policy["GSI1PK"] == "POLICY#26" and policy["GSI1SK"] == loaded.get_policy(w.P_DIDIMDOL).apply_end
    assert raw(CATALOG, f"POLICY#{w.P_NATIONAL_JOB}", "META")["GSI1PK"] == "POLICY#00"
    company = loaded.list_companies("26")[0]
    row = raw(CATALOG, f"COMPANY#{company.company_id}", "META")
    assert row["GSI1PK"] == "COMPANY#26" and row["GSI1SK"] == company.name
    meta = raw(CATALOG, "META#OPP", "INGEST")
    assert meta["dataAsOf"] == w.DATA_AS_OF and meta["entityType"] and meta["createdAt"]


def test_postings_by_sido_matches_memory(loaded, memory_world):
    for sido in ("26", "11", "41"):
        for closes_from in ("2026-11-21", "2026-12-01", "2000-01-01"):
            expected = memory_world.query_postings_by_sido(sido, closes_from=closes_from)
            assert loaded.query_postings_by_sido(sido, closes_from=closes_from) == expected
    busan = loaded.query_postings_by_sido("26", closes_from="2026-11-21")
    assert busan and [p.closes_at for p in busan] == sorted(p.closes_at for p in busan)


def test_postings_by_sido_limit_keeps_tie_order(loaded, memory_world):
    """마감일이 같은 공고가 한도 경계에 걸려도 메모리 구현과 같은 순서로 자른다."""
    for limit in range(1, 8):
        assert (loaded.query_postings_by_sido("26", closes_from="2000-01-01", limit=limit)
                == memory_world.query_postings_by_sido("26", closes_from="2000-01-01", limit=limit))


def test_posting_with_unknown_region_is_not_in_gsi(loaded, raw):
    unknown = loaded.get_latest(w.DATA_UNKNOWN_REGION)
    assert unknown.work_region.unknown
    item = raw(CATALOG, f"POSTING#{w.DATA_UNKNOWN_REGION}", "LATEST")
    assert "GSI1PK" not in item and "GSI1SK" not in item
    for sido in ("26", "11", "41", "28"):
        ids = {p.job_posting_id for p in loaded.query_postings_by_sido(sido, closes_from="2000-01-01", limit=100)}
        assert w.DATA_UNKNOWN_REGION not in ids
    assert loaded.get_latest(w.DATA_UNKNOWN_REGION) == unknown  # 직접 읽기는 된다


def test_relocating_a_posting_moves_its_gsi_entry(loaded):
    latest = loaded.get_latest(w.BUSAN_DATA)
    loaded.put_latest(latest.model_copy(update={"work_region": latest.work_region.model_copy(
        update={"sido": None, "sigungu": None, "unknown": True})}))
    ids = {p.job_posting_id for p in loaded.query_postings_by_sido("26", closes_from="2000-01-01", limit=100)}
    assert w.BUSAN_DATA not in ids


def test_policies_and_companies_match_memory(loaded, memory_world):
    for key in ("00", "26", "11"):
        assert loaded.query_policies(key) == memory_world.query_policies(key)
    keys = [p.apply_end for p in loaded.query_policies("26")]
    assert keys == sorted(keys)
    assert w.P_BUSAN_NAMGU in {p.policy_id for p in loaded.query_policies("26")}  # 구 단위도 시·도 키
    assert loaded.get_policy(w.P_UNVERIFIED).verified is False
    for sido in ("26", "11"):
        assert loaded.list_companies(sido) == memory_world.list_companies(sido)
    assert [c.name for c in loaded.list_companies("26")] == sorted(c.name for c in loaded.list_companies("26"))


def test_batch_get_latest_splits_into_hundreds(loaded, memory_world, ddb):
    """키가 250개여도 100개씩 나눠 읽고, 없는 ID와 중복 ID는 걸러 낸다."""
    template = memory_world.latest[w.BUSAN_DATA]
    ids = [f"wk24-BULK{i:04d}" for i in range(250)]
    for job_posting_id in ids:
        loaded.put_latest(template.model_copy(update={"job_posting_id": job_posting_id}))
    sizes = []
    original = ddb.batch_get_item

    def spy(**kwargs):
        sizes.append(len(next(iter(kwargs["RequestItems"].values()))["Keys"]))
        return original(**kwargs)

    with mock.patch.object(ddb, "batch_get_item", side_effect=spy):
        found = loaded.batch_get_latest(ids + ["wk24-MISSING", ids[0]])
    assert sizes == [100, 100, 51]  # 마지막 쪽: 50개 + 없는 ID 1개
    assert set(found) == set(ids) and found[ids[7]].job_posting_id == ids[7]
    assert loaded.batch_get_latest([]) == {}


def test_batch_get_latest_retries_unprocessed_keys(loaded, ddb):
    original = ddb.batch_get_item
    calls = []
    sleeps = []

    def flaky(**kwargs):
        keys = next(iter(kwargs["RequestItems"].values()))["Keys"]
        calls.append(len(keys))
        if len(calls) == 1:  # 첫 호출은 절반만 처리했다고 답한다
            done = original(RequestItems={CATALOG: {"Keys": keys[:1]}})
            done["UnprocessedKeys"] = {CATALOG: {"Keys": keys[1:]}}
            return done
        return original(**kwargs)

    loaded.sleep = sleeps.append
    ids = [w.BUSAN_DATA, w.SEOUL_DATA, w.BUSAN_BACKEND]
    with mock.patch.object(ddb, "batch_get_item", side_effect=flaky):
        found = loaded.batch_get_latest(ids)
    assert set(found) == set(ids) and calls == [3, 2] and len(sleeps) == 1


def test_batch_get_gives_up_when_keys_never_get_processed(loaded, ddb):
    def never(**kwargs):
        return {"Responses": {}, "UnprocessedKeys": kwargs["RequestItems"]}

    with mock.patch.object(ddb, "batch_get_item", side_effect=never):
        with pytest.raises(OppError) as caught:
            loaded.batch_get_latest([w.BUSAN_DATA])
    assert caught.value.code == "AWS_SERVICE_ERROR" and caught.value.retryable


def test_rewrite_keeps_created_at_and_moves_updated_at(loaded, raw, fake_clock):
    first = raw(CATALOG, f"POSTING#{w.BUSAN_DATA}", "LATEST")
    fake_clock.advance(hours=3)
    loaded.put_latest(loaded.get_latest(w.BUSAN_DATA).model_copy(update={"is_expired": True}))
    second = raw(CATALOG, f"POSTING#{w.BUSAN_DATA}", "LATEST")
    assert second["createdAt"] == first["createdAt"] and second["updatedAt"] > first["updatedAt"]
    assert second["isExpired"] is True and loaded.get_latest(w.BUSAN_DATA).is_expired


def test_optional_fields_removed_when_model_drops_them(loaded):
    """모델에서 None으로 바뀐 칸은 아이템에서도 지워진다. 옛 값이 남아 되살아나지 않는다."""
    policy = loaded.get_policy(w.P_DIDIMDOL)
    assert policy.url
    loaded.put_policy(policy.model_copy(update={"url": None}))
    assert loaded.get_policy(w.P_DIDIMDOL).url is None


def test_data_as_of_is_updated_in_place(catalog, raw, fake_clock):
    catalog.set_data_as_of("2026-11-21T04:52:00+09:00")
    created = raw(CATALOG, "META#OPP", "INGEST")["createdAt"]
    fake_clock.advance(days=1)
    catalog.set_data_as_of("2026-11-22T04:50:00+09:00")
    item = raw(CATALOG, "META#OPP", "INGEST")
    assert catalog.data_as_of() == "2026-11-22T04:50:00+09:00" and item["createdAt"] == created
    assert item["updatedAt"] > created


def test_never_scans(loaded, memory_world):
    seen = []
    from botocore.client import BaseClient
    original = BaseClient._make_api_call

    def spy(self, operation_name, api_params):
        seen.append(operation_name)
        return original(self, operation_name, api_params)

    with mock.patch.object(BaseClient, "_make_api_call", spy):
        loaded.get_latest(w.BUSAN_DATA)
        loaded.batch_get_latest([w.BUSAN_DATA, w.SEOUL_DATA])
        loaded.query_postings_by_sido("26", closes_from="2026-11-21")
        loaded.query_policies("26")
        loaded.list_companies("26")
        loaded.data_as_of()
    assert seen and "Scan" not in seen
    assert set(seen) <= {"GetItem", "BatchGetItem", "Query"}


def test_boto_errors_become_aws_service_error(ddb, fake_clock):
    catalog = DynamoCatalog(ddb, CATALOG, now=fake_clock)
    denied = ClientError({"Error": {"Code": "AccessDeniedException",
                                    "Message": "User arn:aws:iam::123456789012:user/x is not authorized"}}, "GetItem")
    with mock.patch.object(catalog.t.table, "get_item", side_effect=denied):
        with pytest.raises(OppError) as caught:
            catalog.get_latest("wk24-1")
    error = caught.value
    assert (error.status, error.code, error.retryable) == (503, "AWS_SERVICE_ERROR", True)
    assert "123456789012" not in error.message and "wk24-1" not in error.message
    assert error.details == {"service": "dynamodb"}


def test_table_name_comes_from_env_when_not_given(ddb, monkeypatch):
    monkeypatch.setenv("TABLE_CATALOG", CATALOG)
    assert DynamoCatalog(ddb).t.name == CATALOG
    monkeypatch.delenv("TABLE_CATALOG")
    with pytest.raises(Exception, match="TABLE_CATALOG"):
        DynamoCatalog(ddb)
