"""normalize.py: 원본 → 스냅샷·정책. 샘플 응답은 field_maps.py의 임시 매핑표에 맞춘 가짜 데이터다."""

from pathlib import Path

import pytest

from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import (
    SkipRecord,
    compute_content_hash,
    normalize_alio,
    normalize_work24,
    normalize_youthcenter,
    parse_career,
    parse_closes,
    parse_education,
    parse_employment,
    parse_region,
    parse_salary,
)
from opportunity.models import (
    CareerType,
    EducationLevel,
    EmploymentType,
    ExtractedBy,
    OrgType,
    PeriodType,
    PolicySource,
    PolicyStage,
    PostingSource,
    RegionScope,
    SourceType,
    latest_from_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def work24_records():
    xml = (FIXTURES / "work24_list_p1.xml").read_bytes()
    records = as_list(walk(parse_body(xml), "wantedRoot.wanted"))
    page2 = as_list(walk(parse_body((FIXTURES / "work24_list_p2.xml").read_bytes()), "wantedRoot.wanted"))
    return records + page2


def youth_records():
    parsed = parse_body((FIXTURES / "youthcenter_list_p1.json").read_bytes())
    return walk(parsed, "result.youthPolicyList")


def test_work24_busan_posting(as_of):
    snap = normalize_work24(work24_records()[0], as_of=as_of)
    assert snap.job_posting_id == "wk24-K000000001"
    assert snap.source == PostingSource.WORK24 and snap.source_type == SourceType.OFFICIAL
    assert snap.org_type == OrgType.PRIVATE and snap.organization == "(주)가상데이터"
    assert snap.work_region.sido == "26" and snap.work_region.label == "부산 해운대구"
    assert not snap.work_region.unknown
    assert (snap.salary.disclosed, snap.salary.min, snap.salary.max, snap.salary.unit) == (
        True, 3000, 4000, "MANWON_YEAR")
    assert snap.closes_at == "2026-12-15" and snap.rolling is False
    assert snap.career_type == CareerType.NEW and snap.education_min == EducationLevel.BACHELOR
    assert snap.employment_type == EmploymentType.FULL_TIME
    assert snap.checked_at == "2026-11-21T10:00:00+09:00"
    assert snap.official_url == "https://example.invalid/wk24/K000000001"
    assert snap.extract_status == "PENDING" and snap.requirements == [] and snap.badges == []
    assert snap.job.name == snap.title  # 직종 이름이 없으면 제목을 쓴다
    assert snap.job.code == "024101"


def test_snapshot_id_and_hash_format(as_of):
    snap = normalize_work24(work24_records()[0], as_of=as_of)
    assert len(snap.content_hash) == 64 and int(snap.content_hash, 16) >= 0
    assert snap.snapshot_id == f"20261121-{snap.content_hash[:8]}" and "#" not in snap.snapshot_id


def test_hash_ignores_collection_time_but_not_content(as_of):
    record = work24_records()[0]
    morning = normalize_work24(record, as_of="2026-11-21T04:00:00+09:00")
    evening = normalize_work24(record, as_of="2026-11-21T23:00:00+09:00")
    next_day = normalize_work24(record, as_of="2026-11-22T04:00:00+09:00")
    assert morning.content_hash == evening.content_hash == next_day.content_hash
    assert morning.snapshot_id == evening.snapshot_id and morning.snapshot_id != next_day.snapshot_id
    changed = normalize_work24({**record, "closeDt": "2026-12-20"}, as_of=as_of)
    assert changed.content_hash != morning.content_hash
    assert compute_content_hash(morning) == morning.content_hash


def test_company_rule_and_until_hired(as_of):
    """"회사내규"는 disclosed=false, "채용시까지"는 rolling=true이고 closesAt은 9999-12-31이다."""
    snap = normalize_work24(work24_records()[1], as_of=as_of)
    assert snap.salary.disclosed is False and snap.salary.min is None and snap.salary.max is None
    assert snap.rolling is True and snap.closes_at == "9999-12-31"
    assert snap.work_region.sido == "11" and snap.career_type == CareerType.ANY
    assert snap.education_min == EducationLevel.NONE


def test_missing_workplace_is_unknown_not_busan(config, as_of):
    snap = normalize_work24(work24_records()[2], as_of=as_of)
    assert snap.work_region.unknown is True and snap.work_region.sido is None
    assert snap.work_region.label == "근무지 확인 필요"
    latest = latest_from_snapshot(snap, busan_sido=config.data.busan_sido, capital_sido=config.data.capital_area_sido)
    assert latest.is_busan is False and latest.is_capital_area is False
    assert snap.salary.min == 3000 and snap.salary.max == 3000  # 월급 250만 원 x 12
    assert snap.employment_type == EmploymentType.CONTRACT


def test_api_filled_fields_are_recorded(as_of):
    snap = normalize_work24(work24_records()[0], as_of=as_of)
    assert snap.extracted_by["workRegion"] == ExtractedBy.API and snap.extracted_by["salary"] == ExtractedBy.API
    assert "jobDescription" not in snap.extracted_by  # 목록에는 설명이 없다
    unknown = normalize_work24(work24_records()[2], as_of=as_of)
    assert "workRegion" not in unknown.extracted_by


def test_detail_fills_description_steps_documents(as_of):
    detail = walk(parse_body((FIXTURES / "work24_detail_K000000001.xml").read_bytes()), "wantedDtl.wantedInfo")
    snap = normalize_work24(work24_records()[0], as_of=as_of, detail=detail)
    assert snap.job_description.startswith("데이터 분석과 SQL")
    assert snap.selection_steps == ["서류전형", "면접"] and snap.documents == ["이력서", "자기소개서"]
    assert snap.extracted_by["jobDescription"] == ExtractedBy.API


def test_job_codes_table_fills_middle_and_major(as_of):
    codes = {"024101": {"name": "데이터 분석가", "middle": "데이터", "major": "데이터·IT"}}
    snap = normalize_work24(work24_records()[0], as_of=as_of, job_codes=codes)
    assert (snap.job.name, snap.job.middle, snap.job.major) == ("데이터 분석가", "데이터", "데이터·IT")


def test_bad_or_missing_fields_skip_the_record(as_of):
    record = work24_records()[0]
    with pytest.raises(SkipRecord) as caught:
        normalize_work24({**record, "wantedAuthNo": "K#1"}, as_of=as_of)
    assert caught.value.reason == "bad_id"
    with pytest.raises(SkipRecord) as caught:
        normalize_work24({**record, "wantedAuthNo": ""}, as_of=as_of)
    assert caught.value.reason == "missing_id"
    with pytest.raises(SkipRecord) as caught:
        normalize_work24({**record, "closeDt": ""}, as_of=as_of)
    assert caught.value.reason == "no_deadline"  # 마감을 모르면 상시 채용으로 만들지 않는다
    with pytest.raises(SkipRecord) as caught:
        normalize_work24({**record, "title": ""}, as_of=as_of)
    assert caught.value.reason == "missing_title"


def test_alio_postings(as_of):
    parsed = parse_body((FIXTURES / "alio_list_p1.json").read_bytes())
    rows = walk(parsed, ("result",))
    first = normalize_alio(rows[0], as_of=as_of)
    assert first.job_posting_id == "alio-2026001" and first.source == PostingSource.ALIO
    assert first.org_type == OrgType.PUBLIC_INSTITUTION and first.work_region.sido == "26"
    assert first.education_min == EducationLevel.NONE and first.salary.disclosed is False
    multi = normalize_alio(rows[1], as_of=as_of)
    assert multi.work_region.unknown is True and "여러 곳" in multi.work_region.label
    assert multi.employment_type == EmploymentType.UNKNOWN  # 정규직과 계약직이 함께 적혀 있다
    with pytest.raises(SkipRecord):
        normalize_alio(rows[2], as_of=as_of)


@pytest.mark.parametrize("raw,kind,expected", [
    ("3,000만원 ~ 4,000만원", "연봉", (True, 3000, 4000)),
    ("연 3000만원 이상", "", (True, 3000, None)),
    ("250만원", "월급", (True, 3000, 3000)),
    ("2,800,000원", "월급", (True, 3360, 3360)),
    ("", "회사내규", (False, None, None)),
    ("협의", "", (False, None, None)),
    ("10,030원", "시급", (False, None, None)),   # 시급은 연봉으로 바꾸지 않는다
    ("3000만원", "", (False, None, None)),        # 연봉인지 월급인지 모른다
    ("주 40시간 근무", "연봉", (False, None, None)),
    ("기본 2000만원 + 성과 1000만원 + 수당 500만원", "연봉", (False, None, None)),
    ("3000 ~ 4000", "연봉", (True, 3000, 4000)),
])
def test_parse_salary(raw, kind, expected):
    salary = parse_salary(raw, kind)
    assert (salary.disclosed, salary.min, salary.max) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-12-15", ("2026-12-15", False)),
    ("20261215", ("2026-12-15", False)),
    ("2026.12.15 18:00", ("2026-12-15", False)),
    ("채용시까지", ("9999-12-31", True)),
    ("상시 채용", ("9999-12-31", True)),
    ("2026-13-45", (None, False)),
    ("", (None, False)),
])
def test_parse_closes(raw, expected):
    assert parse_closes(raw) == expected


def test_parse_region_code_and_text():
    by_code = parse_region("2635010100", "부산광역시 해운대구 센텀로")
    assert (by_code.sido, by_code.sigungu, by_code.label) == ("26", "26350", "부산 해운대구")
    sido_only = parse_region("26000", "")
    assert (sido_only.sido, sido_only.sigungu, sido_only.label) == ("26", None, "부산")
    assert parse_region("", "경기도 성남시 분당구 판교로").label == "경기 성남시 분당구"
    assert parse_region("", "(48058) 부산광역시 해운대구 1, 5층").sido == "26"
    assert parse_region("99999", "").unknown is True
    assert parse_region("", "해운대구").unknown is True  # 시·도를 알 수 없다


def test_parse_conditions():
    assert parse_education("고졸, 대졸(4년)") == EducationLevel.HIGH_SCHOOL
    assert parse_education("초대졸(2~3년)") == EducationLevel.ASSOCIATE
    assert parse_education("석사") == EducationLevel.MASTER and parse_education("") is None
    assert parse_career("신입/경력") == CareerType.ANY and parse_career("경력 3년 이상") == CareerType.EXPERIENCED
    assert parse_career("") == CareerType.UNKNOWN
    assert parse_employment("정규직") == EmploymentType.FULL_TIME
    assert parse_employment("체험형 인턴") == EmploymentType.INTERN
    assert parse_employment("무기계약직") == EmploymentType.UNKNOWN


def test_youthcenter_policies(as_of):
    national, busan, seoul, bad = youth_records()
    p1 = normalize_youthcenter(national, as_of=as_of)
    assert p1.policy_id == "ythc-20260100000001" and p1.youthcenter_id == "20260100000001"
    assert p1.verified is True and p1.verified_by == "YOUTHCENTER_API" and p1.source == PolicySource.YOUTHCENTER
    assert p1.regions[0].scope == RegionScope.NATIONAL and p1.region_key() == "00"
    assert (p1.age_min, p1.age_max) == (19, 34) and p1.category == "JOB" and p1.stage == PolicyStage.PREPARE
    assert (p1.apply_start, p1.apply_end) == ("2026-11-01", "2026-11-30")
    assert p1.application.period_type == PeriodType.FIXED and p1.as_of == "2026-11-21"
    assert p1.eligibility.income is None  # "무관"
    assert p1.benefit.text == "월 50만 원 지원" and p1.url == "https://example.invalid/policy/1"

    p2 = normalize_youthcenter(busan, as_of=as_of)
    assert p2.regions[0].scope == RegionScope.SIDO and p2.region_key() == "26"
    assert (p2.age_min, p2.age_max) == (None, None)  # 0은 제한 없음
    assert p2.application.period_type == PeriodType.ALWAYS and p2.apply_end == "9999-12-31"
    assert p2.category == "HOUSING" and p2.stage == PolicyStage.SETTLE
    assert p2.income_rule == "연소득 중위소득 150% 이하" and p2.eligibility.manual_checks == ["부산 거주 6개월 이상"]
    assert p2.url == "https://example.invalid/policy/2"

    p3 = normalize_youthcenter(seoul, as_of=as_of)
    assert [(r.scope, r.sigungu) for r in p3.regions] == [
        (RegionScope.SIGUNGU, "11680"), (RegionScope.SIGUNGU, "11650")]
    assert p3.region_key() == "11" and p3.application.period_type == PeriodType.TBD

    with pytest.raises(SkipRecord) as caught:
        normalize_youthcenter(bad, as_of=as_of)
    assert caught.value.reason == "bad_id"
