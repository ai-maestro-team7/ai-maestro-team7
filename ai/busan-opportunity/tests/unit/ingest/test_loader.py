"""seeds/loader.py: source·asOf가 없는 시드는 거부한다."""

import json

import pytest

from opportunity.seeds.loader import SeedError, load_companies, load_policies, load_region_stats

SRC = {"source": "청끌기업 2026 선정 목록", "asOf": "2026-05-01"}


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def company(**override):
    return {"companyId": "biz-1", "name": "가상기업", "sido": "26", **SRC, **override}


def policy(**override):
    return {"policyId": "seed-1", "title": "가상 정책", "source": "BUSAN_SEED", "asOf": "2026-11-20",
            "verified": False, **override}


def test_loads_valid_companies(tmp_path):
    badge = {"type": "CHEONGKKEUL", "label": "청끌기업", "cheonggeulType": "SALARY", **SRC}
    rows = load_companies(write(tmp_path, "c.json", [company(highlights=[badge])]))
    assert rows[0].company_id == "biz-1" and rows[0].highlights[0].source == SRC["source"]
    assert load_companies(write(tmp_path, "c2.json", {"items": [company()]}))[0].name == "가상기업"


def test_rejects_company_without_source_and_names_it(tmp_path):
    bad = company(companyId="biz-2", name="출처없는기업")
    del bad["source"]
    path = write(tmp_path, "c.json", [company(), bad])
    with pytest.raises(SeedError) as caught:
        load_companies(path)
    assert "#1 biz-2" in str(caught.value) and "source" in str(caught.value)
    assert caught.value.problems == ["#1 biz-2: source 없음"]


def test_rejects_company_without_as_of_and_blank_values(tmp_path):
    with pytest.raises(SeedError) as caught:
        load_companies(write(tmp_path, "c.json", [company(asOf=""), company(companyId="biz-3", source="  ")]))
    assert len(caught.value.problems) == 2 and "asOf" in caught.value.problems[0]


def test_rejects_badge_without_source(tmp_path):
    badge = {"type": "CHEONGKKEUL", "label": "청끌기업"}
    with pytest.raises(SeedError) as caught:
        load_companies(write(tmp_path, "c.json", [company(highlights=[badge])]))
    assert "highlights[청끌기업]" in str(caught.value)


def test_reports_every_bad_item_at_once(tmp_path):
    rows = [{"companyId": "a", "name": "가"}, {"companyId": "b", "name": "나", "source": "s"}, company()]
    with pytest.raises(SeedError) as caught:
        load_companies(write(tmp_path, "c.json", rows))
    assert [p.split(":")[0] for p in caught.value.problems] == ["#0 a", "#1 b"]


def test_policy_verified_is_kept_as_written(tmp_path):
    rows = load_policies(write(tmp_path, "p.json", [
        policy(), policy(policyId="seed-2", verified=True, verifiedBy="MANUAL", youthcenterId="2026")]))
    assert rows[0].verified is False and rows[1].verified is True and rows[1].verified_by == "MANUAL"
    assert rows[1].youthcenter_id == "2026"


def test_rejects_policy_without_source_or_as_of(tmp_path):
    no_source, no_asof = policy(policyId="seed-3"), policy(policyId="seed-4")
    del no_source["source"]
    del no_asof["asOf"]
    with pytest.raises(SeedError) as caught:
        load_policies(write(tmp_path, "p.json", [policy(), no_source, no_asof]))
    assert caught.value.problems == ["#1 seed-3: source 없음", "#2 seed-4: asOf 없음"]


def test_rejects_malformed_policy(tmp_path):
    with pytest.raises(SeedError) as caught:
        load_policies(write(tmp_path, "p.json", [policy(source="모르는출처")]))
    assert "형식이 맞지 않는다" in caught.value.problems[0]


def test_unreadable_files_raise_seed_error(tmp_path):
    with pytest.raises(SeedError):
        load_policies(tmp_path / "none.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SeedError):
        load_policies(broken)
    with pytest.raises(SeedError):
        load_policies(write(tmp_path, "obj.json", {"x": 1}))


def test_region_stats(tmp_path):
    rent = {"label": "부산 해운대구", "value": 48, "sampleSize": 52, "period": "2026-05~2026-10", "method": "중앙값",
            **SRC}
    commute = {"label": "부산 해운대구", "value": 61.5, "source": "통계", "asOf": "2025-12-31"}
    stats = load_region_stats(write(tmp_path, "r.json", {"rent": {"26350": rent}, "commute": {"26350": commute}}))
    assert stats.rent["26350"].value == 48 and stats.rent["26350"].region_code == "26350"
    assert stats.commute["26350"].value == 61.5


def test_region_stats_reject_missing_source(tmp_path):
    rent = {"label": "부산 해운대구", "value": 48, "sampleSize": 52, "period": "p", "method": "m", "asOf": "2026-11-01"}
    with pytest.raises(SeedError) as caught:
        load_region_stats(write(tmp_path, "r.json", {"rent": {"26350": rent}}))
    assert caught.value.problems == ["rent[26350]: source 없음"]
