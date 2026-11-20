"""local_load.py: 저장한 원본 → 정규화 → 메모리 저장소 → 요약. 네트워크와 AWS는 부르지 않는다."""

import json
import shutil

from opportunity.ingest import local_load
from opportunity.models.policy import Policy

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"
DAY = "2026-11-20"


def make_raw(tmp_path, *, with_codes=True):
    """손으로 받은 파일 이름 그대로 raw 폴더를 꾸민다."""
    raw = tmp_path / "raw"
    youth = raw / "youthcenter" / DAY
    gangso = raw / "work24_gangso" / DAY
    youth.mkdir(parents=True)
    gangso.mkdir(parents=True)
    shutil.copy(FIXTURES / "youthcenter_list_p1.json", youth / "policies_p001.json")
    shutil.copy(FIXTURES / "work24_gangso_region26000_p1.xml", gangso / "region26000_p001.xml")
    (gangso / "region11000_p001.xml").write_bytes(b"<smallGiantsList><total>0</total></smallGiantsList>")
    (youth / "policies_p002.json").write_bytes(b"{not json")  # 깨진 파일은 세고 넘어간다
    if with_codes:
        codes = raw / "work24_codes" / DAY
        codes.mkdir(parents=True)
        shutil.copy(FIXTURES / "work24_codes_CMCD_1.xml", codes / "CMCD_1.xml")
        shutil.copy(FIXTURES / "work24_codes_CMCD_2.xml", codes / "CMCD_2.xml")
    return raw


def test_load_summarizes_counts(tmp_path):
    catalog, summary, policies, companies = local_load.load(make_raw(tmp_path), DAY)
    p, c = summary["policies"], summary["companies"]
    assert (p["listed"], p["apiTotal"], p["normalized"], p["stored"]) == (8, 8, 8, 8)
    assert p["byRegionKey"] == {"busan": 5, "seoul": 1, "national": 1}
    assert p["includesBusan"] == 5 and p["multiSidoIncludingBusan"] == 1
    assert p["periodType"] == {"ALWAYS": 1, "FIXED": 6, "TBD": 1}
    # 2026-11-20에 열려 있는 것: 사하(~12-31), 부산 이사비(~12-31), AI 거점대학(상시), 전국(~11-21),
    # 서울(~11-30), 청주(~12-15). 기쁨카드(4월)와 수영구(마감)는 닫혀 있다
    assert p["open"] == 6
    assert p["failed"] == 1 and p["failedBy"] == {"unreadable_file": 1}
    assert (c["listed"], c["normalized"], c["stored"], c["failed"]) == (3, 3, 3, 0)
    assert c["apiTotal"] == {"region11000": 0, "region26000": 3} and c["bySido"]["26"] == 3
    assert summary["codes"] == {"regions": 17, "jobs": 3}
    assert len(catalog.policies) == 8 and len(catalog.companies) == 3
    assert {p.policy_id for p in policies} == set(catalog.policies) and len(companies) == 3
    # 지역 표가 있으면 청주시 구 4곳을 시 하나로 묶는다
    assert catalog.get_policy("ythc-20261106005400214758").regions[0].sigungu == "43110"


def test_load_without_code_tables(tmp_path):
    catalog, summary, _, _ = local_load.load(make_raw(tmp_path, with_codes=False), DAY)
    assert summary["codes"] == {"regions": 0, "jobs": 0} and summary["policies"]["normalized"] == 8
    assert catalog.get_policy("ythc-20261106005400214758").regions[0].scope == "SIDO"


def test_main_writes_jsonl(tmp_path, capsys):
    raw = make_raw(tmp_path)
    assert local_load.main(["--raw", str(raw), "--day", DAY, "--out", str(tmp_path / "data")]) == 0
    printed = json.loads(capsys.readouterr().out)
    folder = tmp_path / "data" / "normalized" / DAY
    assert printed["written"] == {"policies": 8, "companies": 3, "dir": str(folder)}
    lines = (folder / "policies.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["policyId"].startswith("ythc-") and first["source"] == "YOUTHCENTER"  # 카멜 표기
    assert Policy.model_validate(first).verified is True  # 다시 읽으면 같은 모델
    company = json.loads((folder / "companies.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert company["companyId"].startswith("biz-") and company["highlights"][0]["asOf"] == "2024"


def test_main_without_out_writes_nothing(tmp_path, capsys):
    raw = make_raw(tmp_path)
    local_load.main(["--raw", str(raw), "--day", DAY])
    assert "written" not in json.loads(capsys.readouterr().out)
    assert not (tmp_path / "normalized").exists()
