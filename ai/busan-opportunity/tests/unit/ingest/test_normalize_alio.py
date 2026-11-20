"""normalize.py: 잡알리오 채용공시 → 스냅샷.

샘플(alio_list_p1.json, alio_detail_307276.json)은 2026-11-20 실제 응답에서 뽑았다.
- 307201 영화진흥위원회 청년인턴 (부산 한 곳)
- 307268 동남권원자력의학원 의사직 상시 모집 (부산, 마감 2027-12-31)
- 307276 코레일테크 기간제 (부산을 포함한 15곳, 상세에 첨부 파일이 있다)
- 307281 국민체육진흥공단 무기계약직 (서울)
- 307285 한국수자원공사 체험형 인턴 (부산 없는 13곳)
- 306904 한국지식재산보호원 (해외, 마감 2026-11-20)
"""

import json
import re
from pathlib import Path

import pytest

from opportunity.ingest.http import parse_body, walk
from opportunity.ingest.normalize import (
    SkipRecord,
    alio_description,
    alio_documents,
    alio_url,
    compute_content_hash,
    normalize_alio,
    parse_alio_career,
    parse_alio_education,
    parse_alio_employment,
    parse_alio_job,
    parse_alio_region,
)
from opportunity.models import (
    CareerType,
    EducationLevel,
    EmploymentType,
    ExtractedBy,
    ExtractStatus,
    OrgType,
    PostingSource,
    SourceType,
    latest_from_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = "2026-11-20T10:00:00+09:00"
BUSAN = "26"


def records() -> dict[int, dict]:
    parsed = parse_body((FIXTURES / "alio_list_p1.json").read_bytes())
    return {r["recrutPblntSn"]: r for r in walk(parsed, "result")}


def detail_307276() -> dict:
    return json.loads((FIXTURES / "alio_detail_307276.json").read_text(encoding="utf-8"))["result"]


def alio(sn: int, **changes):
    return normalize_alio({**records()[sn], **changes}, as_of=AS_OF, first_sido=BUSAN)


def test_response_shape_matches_spec():
    from opportunity.ingest.field_maps import ALIO
    parsed = parse_body((FIXTURES / "alio_list_p1.json").read_bytes())
    assert walk(parsed, ALIO["list"]["total_path"]) == 6 and len(walk(parsed, ALIO["list"]["items_path"])) == 6
    assert ALIO["list"]["params"] == {"resultType": "json", "ongoingYn": "Y"}
    assert ALIO["detail"]["enabled"] is False  # 목록에 내용이 다 온다
    assert isinstance(walk(json.loads((FIXTURES / "alio_detail_307276.json").read_bytes()),
                           ALIO["detail"]["item_path"]), dict)  # 상세 result는 객체 하나다


def test_busan_intern_posting():
    snap = alio(307201)
    assert snap.job_posting_id == "alio-307201" and snap.source == PostingSource.ALIO
    assert snap.source_type == SourceType.OFFICIAL and snap.org_type == OrgType.PUBLIC_INSTITUTION
    assert snap.organization == "영화진흥위원회" and snap.company.name == "영화진흥위원회"
    assert snap.title.startswith("2027년 상반기 청년 체험형 인턴(일반)")
    assert snap.closes_at == "2026-12-03" and snap.rolling is False
    assert snap.work_region.model_dump(exclude={"overseas", "country"}) == {"sido": "26", "sigungu": None, "label": "부산", "unknown": False}
    assert snap.job.name == "경영.회계.사무 · 문화.예술.디자인.방송"
    assert (snap.job.code, snap.job.middle, snap.job.major) == (None, None, "경영.회계.사무")
    assert snap.job.ncs_codes == ["R600002", "R600008"]
    assert snap.employment_type == EmploymentType.INTERN
    assert snap.career_type == CareerType.NEW and snap.education_min == EducationLevel.NONE
    assert snap.salary.disclosed is False and snap.requirements == []
    assert snap.extract_status == ExtractStatus.PENDING
    assert snap.official_url.startswith("https://kofic.or.kr/")
    assert snap.checked_at == AS_OF


def test_eligibility_rules_use_api_values_as_quotes():
    rules = {r.type.value: r for r in alio(307268).eligibility_rules}
    assert rules["EDUCATION"].value == "BACHELOR" and rules["EDUCATION"].source_quote == "대졸(4년)"
    assert rules["CAREER"].value == {"type": "ANY"} and rules["CAREER"].source_quote == "신입+경력"
    experienced = {r.type.value: r for r in alio(306904).eligibility_rules}
    assert experienced["CAREER"].value == {"type": "EXPERIENCED"}  # 경력 연수는 지어내지 않는다
    assert experienced["EDUCATION"].value == "NONE" and experienced["EDUCATION"].source_quote == "학력무관,대졸(4년)"
    assert [r.rule_id for r in alio(307201).eligibility_rules] == ["rule-edu", "rule-career"]


def test_rolling_posting_keeps_original_deadline():
    snap = alio(307268)
    assert snap.rolling is True and snap.closes_at == "2027-12-31"  # 상시라도 원문 날짜를 둔다
    assert snap.employment_type == EmploymentType.FULL_TIME and snap.job.name == "보건.의료"
    far = alio(307201, pbancEndYmd="20280101")  # 1년 넘게 남은 마감
    assert far.rolling is True and far.closes_at == "2028-01-01"
    titled = alio(307201, recrutPbancTtl="영상의학과 전문의 상시 모집")
    assert titled.rolling is True and titled.closes_at == "2026-12-03"


def test_multi_region_with_busan_is_busan():
    snap = alio(307276)
    assert snap.work_region.sido == "26" and snap.work_region.label == "부산 외 14개 지역"
    assert snap.work_region.sigungu is None and snap.work_region.unknown is False
    assert snap.employment_type == EmploymentType.CONTRACT  # 비정규직
    assert snap.education_min == EducationLevel.NONE  # 학력무관,고졸 → 가장 낮은 것
    assert snap.job.name == "사업관리 · 경영.회계.사무 외 3" and len(snap.job.ncs_codes) == 5
    latest = latest_from_snapshot(snap, busan_sido=BUSAN, capital_sido=["11", "28", "41"])
    assert latest.is_busan is True and latest.is_capital_area is False


def test_multi_region_without_busan_uses_first_region():
    snap = alio(307285)
    assert snap.work_region.sido == "27" and snap.work_region.label == "대구 외 12개 지역"
    assert snap.employment_type == EmploymentType.INTERN and snap.job.name.endswith("외 7")


def test_capital_area_posting():
    snap = alio(307281)
    assert snap.work_region.sido == "11" and snap.work_region.label == "서울"
    assert snap.employment_type == EmploymentType.CONTRACT  # 무기계약직
    latest = latest_from_snapshot(snap, busan_sido=BUSAN, capital_sido=["11", "28", "41"])
    assert latest.is_capital_area is True and latest.is_busan is False


def test_overseas_is_unknown_not_busan():
    snap = alio(306904)
    assert snap.work_region.unknown is True and snap.work_region.sido is None
    assert "해외" in snap.work_region.label
    assert "workRegion" not in snap.extracted_by
    assert snap.closes_at == "2026-11-20"


@pytest.mark.parametrize("raw,first,expected", [
    ("부산", BUSAN, ("26", "부산", False)),
    ("서울,부산", BUSAN, ("26", "부산 외 1개 지역", False)),
    ("서울,부산", None, ("11", "서울 외 1개 지역", False)),
    ("광주,전남", BUSAN, ("29", "광주 외 1개 지역", False)),
    ("전남광주", BUSAN, ("12", "전남광주", False)),  # 2026년 통합 시·도
    ("부산,해외", BUSAN, ("26", "부산 외 1개 지역", False)),
    ("해외", BUSAN, (None, "해외 · 근무지 공고문 확인", True)),
    ("전국", BUSAN, (None, "전국 · 근무지 공고문 확인", True)),
    ("서울,전국", BUSAN, (None, "전국 · 근무지 공고문 확인", True)),
    ("", BUSAN, (None, "근무지 확인 필요", True)),
    ("부산,부산", BUSAN, ("26", "부산", False)),
])
def test_parse_alio_region(raw, first, expected):
    region = parse_alio_region(raw, first_sido=first)
    assert (region.sido, region.label, region.unknown) == expected and region.sigungu is None


@pytest.mark.parametrize("raw,expected", [
    ("정규직", EmploymentType.FULL_TIME),
    ("비정규직", EmploymentType.CONTRACT),
    ("무기계약직", EmploymentType.CONTRACT),
    ("무기계약직,비정규직", EmploymentType.CONTRACT),
    ("청년인턴(체험형)", EmploymentType.INTERN),
    ("청년인턴(채용형)", EmploymentType.INTERN),
    ("정규직,비정규직", EmploymentType.UNKNOWN),
    ("비정규직,청년인턴(체험형)", EmploymentType.UNKNOWN),
    ("", EmploymentType.UNKNOWN),
])
def test_parse_alio_employment(raw, expected):
    assert parse_alio_employment(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("신입", CareerType.NEW), ("경력", CareerType.EXPERIENCED), ("신입+경력", CareerType.ANY),
    ("", CareerType.UNKNOWN),
])
def test_parse_alio_career(raw, expected):
    assert parse_alio_career(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("학력무관", EducationLevel.NONE),
    ("고졸", EducationLevel.HIGH_SCHOOL),
    ("대졸(2~3년),대졸(4년)", EducationLevel.ASSOCIATE),
    ("대졸(4년),석사,박사", EducationLevel.BACHELOR),
    ("석사,박사", EducationLevel.MASTER),
    ("박사", EducationLevel.DOCTOR),
    ("학력무관,고졸,대졸(2~3년),대졸(4년),석사,박사", EducationLevel.NONE),
    ("", None),
])
def test_parse_alio_education(raw, expected):
    assert parse_alio_education(raw) == expected


def test_parse_alio_job():
    assert parse_alio_job("보건.의료", "R600006", "제목").name == "보건.의료"
    many = parse_alio_job("사업관리,경영.회계.사무,건설", "R600001,R600002,R600014", "제목")
    assert many.name == "사업관리 · 경영.회계.사무 외 1" and many.ncs_codes == ["R600001", "R600002", "R600014"]
    assert parse_alio_job("", "", "제목").name == "제목" and parse_alio_job("", "", "제목").major is None


@pytest.mark.parametrize("raw,expected", [
    ("https://www.kwater.or.kr", "https://www.kwater.or.kr"),
    ("\thttps://a.example/x ", "https://a.example/x"),
    ("www.ex.co.kr", "https://www.ex.co.kr"),
    ("없음.", None), (".", None), ("com", None), ("해당없음", None), ("", None),
])
def test_alio_url(raw, expected):
    assert alio_url(raw) == expected


def test_description_joins_sections_with_headings():
    text = alio_description("1. 자격\r\n2. 결격 없음", "가점 5%", "장애인", "서류 → 면접")
    assert text == "[지원 자격]\n1. 자격\n2. 결격 없음\n\n[우대]\n우대 대상: 장애인\n가점 5%\n\n[전형 절차]\n서류 → 면접"
    same = alio_description("자격", "장애인: 5점 가점", "장애인", "")  # 우대 대상이 우대 내용에 들어 있다
    assert same == "[지원 자격]\n자격\n\n[우대]\n장애인: 5점 가점"
    assert alio_description("", "-", "", "") is None


def test_description_from_real_record_is_api_owned():
    snap = alio(307201)
    assert snap.job_description.startswith("[지원 자격]\n- 만 34세 이하인 자")
    assert "\n\n[우대]\n우대 대상: 취업지원대상자, 장애인\n" in snap.job_description
    assert "[전형 절차]\n- 전형절차: 서류전형 → 면접전형" in snap.job_description
    assert "\r" not in snap.job_description
    owned = {k for k, v in snap.extracted_by.items() if v == ExtractedBy.API}
    assert owned == {"title", "organization", "closesAt", "workRegion", "job", "employmentType", "careerType",
                     "educationMin", "jobDescription", "officialUrl"}
    assert "salary" not in snap.extracted_by and "requirements" not in snap.extracted_by
    # 판정 규칙은 보강이 자격증·전공 조건을 더할 수 있게 비워 둔다. 학력·경력 규칙은 위 두 필드의 주인을 보고 남는다
    assert "eligibilityRules" not in snap.extracted_by


def test_detail_adds_documents_from_file_names():
    record = records()[307276]
    assert record["files"] == [] and record["steps"] == []  # 목록에는 비어 온다
    snap = normalize_alio(record, as_of=AS_OF, detail=detail_307276(), first_sido=BUSAN)
    assert snap.documents == ["2027년 제1차 현장기간제 사원 채용공고",
                              "2027년 제1차 현장기간제 사원 채용공고 입사지원서(양식)",
                              "2027년 제1차 현장기간제 사원 채용공고 결격사유 등 기타 붙임자료"]
    assert snap.extracted_by["documents"] == ExtractedBy.API
    assert snap.selection_steps == []  # steps에는 단계 이름이 없다
    assert alio_documents([{"atchFileNm": "2. 지원서.hwp", "sortNo": 2}, {"atchFileNm": "1) 공고문.pdf", "sortNo": 1}],
                          "atchFileNm") == ["공고문", "지원서"]


def test_hash_ignores_daily_values():
    record = records()[307201]
    base = normalize_alio(record, as_of=AS_OF, first_sido=BUSAN)
    tomorrow = normalize_alio({**record, "decimalDay": record["decimalDay"] - 1}, as_of="2026-11-21T04:30:00+09:00",
                              first_sido=BUSAN)
    assert base.content_hash == tomorrow.content_hash == compute_content_hash(base)
    assert base.snapshot_id == f"20261120-{base.content_hash[:8]}"
    changed = normalize_alio({**record, "pbancEndYmd": "20261210"}, as_of=AS_OF, first_sido=BUSAN)
    assert changed.content_hash != base.content_hash


def test_bad_or_missing_fields_skip_the_record():
    for changes, reason in (({"recrutPblntSn": None}, "missing_id"), ({"recrutPblntSn": "30#1"}, "bad_id"),
                            ({"recrutPbancTtl": " "}, "missing_title"), ({"instNm": ""}, "missing_organization"),
                            ({"pbancEndYmd": ""}, "no_deadline")):
        with pytest.raises(SkipRecord) as caught:
            alio(307201, **changes)
        assert caught.value.reason == reason


def test_fixtures_have_no_phone_numbers_or_emails():
    blob = (FIXTURES / "alio_list_p1.json").read_text(encoding="utf-8")
    blob += (FIXTURES / "alio_detail_307276.json").read_text(encoding="utf-8")
    assert not re.search(r"0\d{1,2}\s*[-)]\s*\d{3,4}\s*-\s*\d{4}", blob)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)
