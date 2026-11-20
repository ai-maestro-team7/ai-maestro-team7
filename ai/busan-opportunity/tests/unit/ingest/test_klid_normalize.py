"""normalize.py: 지방공공기관 채용정보 → 스냅샷.

샘플(klid_sido_*.xml)은 2026-11-20 실제 응답에서 뽑았다. 전화번호·접수 방법(담당자 메일)·홍보 글 칸은 "-"로 지웠다.
- 80978 부산도시공사 전문계약직(변호사), 5000만원 이상, 부산진구
- 81144 부산환경공단 기간제, 지역 제한(LOCAL_YN=Y), 마감 2026-11-20
- 81373 부산남구문화재단 기간제, 모집예정
- 81061 서초문화재단 비상임 이사, 무급, 모집 분야 "기타"
- 78134 서울의료원 기간제 전문의, 1억원 이상
- 81418 전라남도사회서비스원, 마감 9999-09-09, 주소가 옛 이름 "전라남도"
- 007005는 "데이터 없음"(resultCode=3) 응답이다
"""

from pathlib import Path

import pytest

from opportunity.ingest.field_maps import KLID
from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import (
    SkipRecord,
    normalize_klid,
    normalize_postings,
    parse_klid_region,
    parse_klid_salary,
)
from opportunity.models import (
    CareerType,
    EmploymentType,
    ExtractedBy,
    ExtractStatus,
    OrgType,
    PostingSource,
    SourceType,
)
from opportunity.models.posting import latest_from_snapshot

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = "2026-11-20T04:30:00+09:00"
# 실제 지역 표(CMCD_1)에서 필요한 줄만 옮겼다
REGION_NAMES = {
    "26000": "부산", "26230": "부산 부산진구", "26260": "부산 동래구", "26290": "부산 남구", "26710": "부산 기장군",
    "11000": "서울", "11650": "서울 서초구", "11260": "서울 중랑구",
    "12000": "전남광주", "12110": "전남광주 목포시", "12810": "전남광주 무안군",
    "36110": "세종",
    "41000": "경기", "41110": "경기 수원시", "41111": "경기 수원시 장안구",
}


def records(*codes: str) -> dict[str, dict]:
    out = {}
    for code in codes or ("007001", "007002", "007013"):
        parsed = parse_body((FIXTURES / f"klid_sido_{code}.xml").read_bytes())
        for item in as_list(walk(parsed, KLID["list"]["items_path"])):
            out[item["NO"]] = item
    return out


@pytest.fixture
def rows():
    return records()


def norm(record, **kwargs):
    return normalize_klid(record, as_of=AS_OF, region_names=REGION_NAMES, **kwargs)


def test_lawyer_posting_in_busan(rows):
    snap = norm(rows["80978"])
    assert snap.job_posting_id == "klid-80978" and snap.snapshot_id.startswith("20261120-")
    assert (snap.source, snap.source_type, snap.org_type) == (PostingSource.KLID, SourceType.OFFICIAL,
                                                               OrgType.LOCAL_PUBLIC)
    assert snap.organization == "부산도시공사" and snap.title == "전문계약직(변호사) 모집공고"
    assert snap.official_url == "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80978"
    assert snap.closes_at == "2026-11-25" and snap.rolling is False
    assert (snap.work_region.sido, snap.work_region.sigungu, snap.work_region.label) == ("26", "26230",
                                                                                          "부산 부산진구")
    assert snap.salary.disclosed and (snap.salary.min, snap.salary.max) == (5000, None)
    assert snap.career_type == CareerType.EXPERIENCED and snap.employment_type == EmploymentType.CONTRACT
    assert snap.job.name == "경영·회계·사무" and snap.job.code is None and snap.job.major is None
    assert snap.education_min is None
    assert snap.documents == []  # 제출 서류 칸이 "공고문 참조"뿐이다
    assert snap.extract_status == ExtractStatus.PENDING and snap.requirements == []
    assert snap.extracted_by["salary"] == ExtractedBy.API and "educationMin" not in snap.extracted_by


def test_licenses_stay_as_text_not_rules(rows):
    snap = norm(rows["80978"])
    assert "[자격·면허]\n변호사" in snap.job_description
    assert [r.type.value for r in snap.eligibility_rules] == ["CAREER"]  # 자격증은 조건으로 만들지 않는다
    assert snap.eligibility_rules[0].source_quote == "경력"


def test_description_has_overview_from_api_text(rows):
    text = norm(rows["78134"]).job_description
    assert text.startswith("[모집 개요]\n기관 구분: 지방출연기관")
    for line in ("모집 분야: 보건·의료", "고용 형태: 기간제", "연봉(원문): 1억원 이상", "모집 기간: 2026-07-28 ~ 2026-12-31"):
        assert line in text
    assert "[자격·면허]\n의사면허증" in text
    assert "[전형 절차]\n서류전형(55점/적격여부 확인)" in text
    assert "null" not in text and "\n-" not in text


def test_local_limit_goes_to_description_only(rows):
    snap = norm(rows["81144"])
    assert "[지역 제한]\n지역 제한: 부산광역시 (부산광역시 산하 지방공기업)" in snap.job_description
    assert snap.regional_talent is None
    assert all(r.type.value != "REGION" for r in snap.eligibility_rules)
    assert snap.documents[:3] == ["이력서", "자기소개서", "주민등록 초본"]
    assert snap.extracted_by["documents"] == ExtractedBy.API


def test_upcoming_posting_is_kept(rows):
    snap = norm(rows["81373"])
    assert snap.career_type == CareerType.ANY
    assert "모집 기간: 2026-12-01 ~ 2026-12-08" in snap.job_description
    assert snap.work_region.label == "부산 남구"


def test_unpaid_board_member(rows):
    snap = norm(rows["81061"])
    assert snap.employment_type == EmploymentType.UNKNOWN  # 비상임
    assert snap.salary.disclosed is False and "연봉(원문): 무급" in snap.job_description
    assert snap.job.name == snap.title  # 모집 분야가 "기타"면 제목을 쓴다
    assert "job" not in snap.extracted_by
    assert (snap.work_region.sido, snap.work_region.sigungu) == ("11", "11650")  # "서울시 서초구"


def test_far_deadline_is_rolling_and_old_sido_name_is_merged(rows):
    snap = norm(rows["81418"])
    assert snap.closes_at == "9999-09-09" and snap.rolling is True
    assert (snap.work_region.sido, snap.work_region.sigungu, snap.work_region.label) == ("12", "12810",
                                                                                          "전남광주 무안군")


def test_busan_flags_come_from_work_region(rows, config):
    busan = latest_from_snapshot(norm(rows["80978"]), busan_sido=config.data.busan_sido,
                                 capital_sido=config.data.capital_area_sido)
    seoul = latest_from_snapshot(norm(rows["81061"]), busan_sido=config.data.busan_sido,
                                 capital_sido=config.data.capital_area_sido)
    assert (busan.is_busan, busan.is_capital_area, busan.is_overseas) == (True, False, False)
    assert (seoul.is_busan, seoul.is_capital_area) == (False, True)


def test_content_hash_ignores_check_time(rows):
    a = normalize_klid(rows["80978"], as_of="2026-11-20T04:30:00+09:00", region_names=REGION_NAMES)
    b = normalize_klid(rows["80978"], as_of="2026-11-21T04:30:00+09:00", region_names=REGION_NAMES)
    assert a.content_hash == b.content_hash and a.checked_at != b.checked_at
    changed = norm({**rows["80978"], "UPD_DATE": "2026-11-21"})  # 쓰지 않는 칸은 해시에 들어가지 않는다
    assert changed.content_hash == a.content_hash
    extended = norm({**rows["80978"], "PUB_END_DATE": "2026-11-30"})
    assert extended.job_posting_id == a.job_posting_id and extended.content_hash != a.content_hash


def test_without_region_table_uses_address_words(rows):
    snap = normalize_klid(rows["80978"], as_of=AS_OF)
    assert (snap.work_region.sido, snap.work_region.sigungu, snap.work_region.label) == ("26", None,
                                                                                          "부산 부산진구")


@pytest.mark.parametrize(("status", "kept"), [("모집중", True), ("모집예정", True), ("모집마감", False),
                                              ("채용완료", False), ("null", False)])
def test_only_open_or_upcoming_status(rows, status, kept):
    record = {**rows["80978"], "STATUS": status}
    if kept:
        assert norm(record).job_posting_id == "klid-80978"
    else:
        with pytest.raises(SkipRecord) as e:
            norm(record)
        assert e.value.reason == "closed_status"


@pytest.mark.parametrize(("field", "reason"), [("ENT_TITLE", "missing_title"), ("ENT_NAME", "missing_organization"),
                                               ("PUB_END_DATE", "no_deadline")])
def test_missing_values_are_skipped(rows, field, reason):
    with pytest.raises(SkipRecord) as e:
        norm({**rows["80978"], field: "null"})
    assert e.value.reason == reason


def test_missing_number_uses_content_hash(rows):
    a = norm({**rows["80978"], "NO": "null"})
    b = norm({**rows["80978"], "NO": "null"})
    assert a.job_posting_id.startswith("klid-h") and len(a.job_posting_id) == len("klid-h") + 16
    assert a.job_posting_id == b.job_posting_id


def test_same_number_with_other_content_is_rehashed(rows):
    clash = {**rows["81144"], "NO": "80978"}
    batch = normalize_postings([rows["80978"], clash, rows["80978"]], normalize_klid, rehash_on_collision=True,
                               as_of=AS_OF, region_names=REGION_NAMES)
    assert batch.rehashed == 1 and batch.duplicates == 1
    assert "klid-80978" in batch.snapshots and len(batch.snapshots) == 2
    other = next(s for i, s in batch.snapshots.items() if i != "klid-80978")
    assert other.job_posting_id.startswith("klid-h") and other.organization == "부산환경공단"


@pytest.mark.parametrize(("raw", "expected"), [
    ("3200만원 이상", (True, 3200, None)),
    ("1200만원 이하", (True, None, 1200)),
    ("1억원 이상", (True, 10000, None)),
    ("1,500만원 이상", (True, 1500, None)),
    ("무급", (False, None, None)),
    ("회사내규", (False, None, None)),
    ("", (False, None, None)),
    ("월 250만원", (False, None, None)),  # 구간 글이 아니면 만들지 않는다
])
def test_parse_salary(raw, expected):
    salary = parse_klid_salary(raw)
    assert (salary.disclosed, salary.min, salary.max) == expected


def test_parse_region_edges():
    assert parse_klid_region("어딘가", "부산광역시 남구", region_names=REGION_NAMES).unknown is True
    # 주소가 다른 시·도면 시·군·구를 찾지 않는다
    other = parse_klid_region("부산광역시", "경기도 수원시 장안구", region_names=REGION_NAMES)
    assert (other.sido, other.sigungu, other.label) == ("26", None, "부산")
    # 우편번호 앞머리를 떼고, 두 낱말 이름을 먼저 맞춘다
    two = parse_klid_region("경기도", "(16200) 경기도 수원시 장안구 수성로", region_names=REGION_NAMES)
    assert (two.sigungu, two.label) == ("41111", "경기 수원시 장안구")
    # 시·도 없이 시·군·구로 시작하는 주소
    bare = parse_klid_region("부산광역시", "기장군 정관읍", region_names=REGION_NAMES)
    assert bare.sigungu == "26710"
    # 시·군·구가 하나뿐인 세종
    sejong = parse_klid_region("세종특별자치시", "세종특별자치시 나성로 33", region_names=REGION_NAMES)
    assert (sejong.sido, sejong.sigungu, sejong.label) == ("36", "36110", "세종")
    # 표에 없는 구 이름은 주소 낱말로만 붙인다
    renamed = parse_klid_region("부산광역시", "부산광역시 가상구 어딘가로 1", region_names=REGION_NAMES)
    assert (renamed.sigungu, renamed.label) == (None, "부산 가상구")
    assert parse_klid_region("부산광역시", "", region_names=REGION_NAMES).label == "부산"
