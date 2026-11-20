"""local_load.py: 저장한 원본 → 정규화 → 메모리 저장소 → 요약. 네트워크와 AWS는 부르지 않는다."""

import json
import shutil

from opportunity.ingest import local_load
from opportunity.models.policy import Policy
from opportunity.models.posting import PostingSnapshot

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
    alio = raw / "alio" / DAY
    alio.mkdir(parents=True)
    shutil.copy(FIXTURES / "alio_list_p1.json", alio / "list_p001.json")
    shutil.copy(FIXTURES / "alio_detail_307276.json", alio / "detail_307276.json")  # 상세는 읽지 않는다
    klid = raw / "klid" / DAY
    klid.mkdir(parents=True)
    for code in ("007001", "007002", "007005", "007013"):
        shutil.copy(FIXTURES / f"klid_sido_{code}.xml", klid / f"sido_{code}.xml")
    worldjob = raw / "worldjob" / DAY
    worldjob.mkdir(parents=True)
    for page in (1, 2):
        shutil.copy(FIXTURES / f"worldjob_p{page}.xml", worldjob / f"worldjob_p{page:02d}.xml")
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


def test_load_summarizes_postings(tmp_path):
    catalog, summary, _, _ = local_load.load(make_raw(tmp_path), DAY)
    a = summary["postings"]["alio"]
    assert (a["listed"], a["apiTotal"], a["normalized"], a["stored"], a["failed"]) == (6, 6, 6, 6, 0)
    assert a["region"] == {
        "busanAny": 3, "busanOnly": 2, "busanMulti": 1, "isBusan": 3, "isCapitalArea": 1, "isOverseas": 0,
        "capitalAny": 3,  # 서울 한 곳 + 서울·인천·경기가 든 307276·307285
        "capitalOnly": 1, "multiRegion": 2, "unknown": 1, "withSigungu": 0,
        "bySido": {"11": 1, "26": 3, "27": 1, "unknown": 1}}
    assert a["salaryDisclosed"] == 0
    assert a["employmentType"] == {"CONTRACT": 3, "FULL_TIME": 1, "INTERN": 2}
    assert a["educationMin"] == {"BACHELOR": 1, "NONE": 5}
    assert a["careerType"] == {"ANY": 3, "EXPERIENCED": 1, "NEW": 2}
    assert a["rolling"] == 1 and a["expired"] == 0 and a["withOfficialUrl"] == 6
    assert a["upsert"] == {"created": 6, "updated": 0, "unchanged": 0, "needsEnrich": 6}
    assert catalog.get_latest("alio-307276").is_busan
    assert catalog.get_snapshot("alio-307276", catalog.get_latest("alio-307276").snapshot_id).documents == []


def test_load_summarizes_klid_postings(tmp_path):
    catalog, summary, _, _ = local_load.load(make_raw(tmp_path), DAY)
    k = summary["postings"]["klid"]
    # 007005는 "데이터 없음" 응답이라 0건이고 실패로 세지 않는다
    assert (k["listed"], k["apiTotal"], k["normalized"], k["stored"], k["failed"]) == (6, 6, 6, 6, 0)
    assert k["region"]["isBusan"] == 3 and k["region"]["isCapitalArea"] == 2 and k["region"]["isOverseas"] == 0
    assert k["region"]["bySido"] == {"11": 2, "12": 1, "26": 3}
    # 테스트 지역 표에는 부산진구·동래구·남구가 없어서 시·군·구 코드는 못 채우고 주소 낱말로 이름만 붙인다
    assert k["region"]["busanBySigungu"] == {"부산 남구": 1, "부산 동래구": 1, "부산 부산진구": 1}
    assert k["salaryDisclosed"] == 5 and k["salaryMinOnly"] == 4 and k["salaryMaxOnly"] == 1  # 무급 1건은 미기재
    assert k["employmentType"] == {"CONTRACT": 5, "UNKNOWN": 1}  # 비상임은 UNKNOWN
    assert k["rolling"] == 1 and k["withOfficialUrl"] == 6
    assert catalog.get_latest("klid-80978").is_busan and catalog.get_latest("klid-81061").is_capital_area


def test_load_summarizes_worldjob_postings(tmp_path):
    _, summary, _, _ = local_load.load(make_raw(tmp_path), DAY)
    w = summary["postings"]["worldjob"]
    assert (w["listed"], w["apiTotal"], w["normalized"], w["duplicates"], w["stored"]) == (5, 5, 4, 1, 4)
    assert w["region"]["isOverseas"] == 3 and w["region"]["unknown"] == 1  # 대한민국(국내 박람회)은 해외가 아니다
    assert w["region"]["isBusan"] == 0 and w["region"]["byCountry"] == {"독일": 1, "미국": 1, "베트남": 1}
    assert w["salaryDisclosed"] == 0 and w["withOfficialUrl"] == 0
    total = summary["postings"]["total"]
    assert total["stored"] == 16 and total["isBusan"] == 6 and total["isOverseas"] == 3


def test_load_counts_unreadable_and_skipped_postings(tmp_path):
    raw = make_raw(tmp_path)
    folder = raw / "alio" / DAY
    (folder / "list_p002.json").write_bytes(b"{broken")
    (folder / "list_p003.json").write_text(json.dumps({"totalCount": 1, "result": [
        {"recrutPblntSn": 1, "instNm": "기관", "recrutPbancTtl": "제목", "pbancEndYmd": ""}]}), encoding="utf-8")
    _, summary, _, _ = local_load.load(raw, DAY)
    assert summary["postings"]["alio"]["failedBy"] == {"no_deadline": 1, "unreadable_file": 1}
    assert summary["postings"]["alio"]["stored"] == 6


def test_load_without_code_tables(tmp_path):
    catalog, summary, _, _ = local_load.load(make_raw(tmp_path, with_codes=False), DAY)
    assert summary["codes"] == {"regions": 0, "jobs": 0} and summary["policies"]["normalized"] == 8
    assert catalog.get_policy("ythc-20261106005400214758").regions[0].scope == "SIDO"


def test_main_writes_jsonl(tmp_path, capsys):
    raw = make_raw(tmp_path)
    assert local_load.main(["--raw", str(raw), "--day", DAY, "--out", str(tmp_path / "data")]) == 0
    printed = json.loads(capsys.readouterr().out)
    folder = tmp_path / "data" / "normalized" / DAY
    assert printed["written"] == {"policies": 8, "companies": 3, "postings": 16, "dir": str(folder)}
    lines = (folder / "policies.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["policyId"].startswith("ythc-") and first["source"] == "YOUTHCENTER"  # 카멜 표기
    assert Policy.model_validate(first).verified is True  # 다시 읽으면 같은 모델
    company = json.loads((folder / "companies.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert company["companyId"].startswith("biz-") and company["highlights"][0]["asOf"] == "2024"
    postings = [json.loads(line) for line in (folder / "postings.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [p["jobPostingId"] for p in postings] == sorted(p["jobPostingId"] for p in postings)
    assert postings[0]["workRegion"]["label"] and postings[0]["source"] == "ALIO"
    assert {p["source"] for p in postings} == {"ALIO", "KLID", "WORLDJOB"}
    for row in postings:
        assert PostingSnapshot.model_validate(row).job_posting_id == row["jobPostingId"]


def test_main_without_out_writes_nothing(tmp_path, capsys):
    raw = make_raw(tmp_path)
    local_load.main(["--raw", str(raw), "--day", DAY])
    assert "written" not in json.loads(capsys.readouterr().out)
    assert not (tmp_path / "normalized").exists()
