"""normalize.py: 원본 → 스냅샷·정책·기업.

공고 샘플(work24_*, alio_*)은 응답을 확인하기 전에 임시 매핑표에 맞춰 만든 가짜 데이터다.
정책(youthcenter_*), 강소기업(work24_gangso_*), 지역·직종 코드(work24_codes_*) 샘플은
2026-11-20 실제 응답에서 뽑았고 담당자·대표자 이름은 비웠다.
"""

from pathlib import Path

import pytest

from opportunity.ingest import codes
from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import (
    SkipRecord,
    compute_content_hash,
    normalize_alio,
    normalize_gangso,
    normalize_work24,
    normalize_youthcenter,
    parse_career,
    parse_closes,
    parse_education,
    parse_apply_period,
    parse_employment,
    parse_income,
    parse_policy_regions,
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
    Selection,
    SourceType,
    latest_from_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def work24_records():
    xml = (FIXTURES / "work24_list_p1.xml").read_bytes()
    records = as_list(walk(parse_body(xml), "wantedRoot.wanted"))
    page2 = as_list(walk(parse_body((FIXTURES / "work24_list_p2.xml").read_bytes()), "wantedRoot.wanted"))
    return records + page2


def youth_records() -> dict[str, dict]:
    parsed = parse_body((FIXTURES / "youthcenter_list_p1.json").read_bytes())
    return {r["plcyNo"]: r for r in walk(parsed, "result.youthPolicyList")}


def region_names() -> dict[str, str]:
    return codes.region_names((FIXTURES / "work24_codes_CMCD_1.xml").read_bytes())


def youth(plcy_no: str, *, as_of="2026-11-20", names=None, **override):
    return normalize_youthcenter({**youth_records()[plcy_no], **override}, as_of=as_of, region_names=names,
                                 first_sido="26")


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


# ---------------------------------------------------------------- 정책 (온통청년 실제 응답)
SAHA = "20261030005400214630"           # 사하일자리지원센터 운영: 부산 사하구, 특정 기간
BUSAN_HOUSING = "20260513005400213198"  # 부산 청년 중개보수 및 이사비 지원: 부산 16개 구·군, 선착순, 소득 기타
AI_HUB = "20260923005400113568"         # AI 거점대학: 전남광주·부산·대전, 상시
SUYEONG_CLOSED = "20260914005400213409" # 청년 사업자 임차료 지원사업: 수영구, 마감(추정), 소득 금액
NATIONAL = "20261021005400214232"       # 글로벌첨단전략산업 기술경영 전문인력: 16개 시·도
SEOUL_GU = "20261023005400214282"       # 청년1인가구 소셜다이닝: 서울 12개 구
CHEONGJU = "20261106005400214758"       # 청주시 자격증 응시료: 청주시 구 4곳
BUSAN_EMPLOYED = "20260513005400213204" # 부산 청년 일하는 기쁨카드: 중분류 재직자


def test_policy_id_source_and_verification():
    p = youth(SAHA)
    assert p.policy_id == f"ythc-{SAHA}" and p.youthcenter_id == SAHA
    assert p.verified is True and p.verified_by == "YOUTHCENTER_API" and p.source == PolicySource.YOUTHCENTER
    assert p.as_of == "2026-11-20" and p.verified_at == "2026-11-20T09:00:00+09:00"
    assert p.url == "https://saha.go.kr/job/main.do"  # aplyUrlAddr가 비면 refUrlAddr1


def test_policy_regions_from_zip_codes():
    names = region_names()
    saha = youth(SAHA)
    assert [(r.scope, r.sido, r.sigungu) for r in saha.regions] == [(RegionScope.SIGUNGU, "26", "26380")]
    assert youth(BUSAN_HOUSING).regions[0].scope == RegionScope.SIDO  # 부산 16개 구·군 전부
    seoul = youth(SEOUL_GU)
    assert [(r.scope, r.sido) for r in seoul.regions] == [(RegionScope.SIDO, "11")] and seoul.region_key() == "11"
    national = youth(NATIONAL)
    assert [r.scope for r in national.regions] == [RegionScope.NATIONAL] and national.region_key() == "00"
    multi = youth(AI_HUB)
    assert [(r.scope, r.sido) for r in multi.regions] == [
        (RegionScope.SIDO, "26"), (RegionScope.SIDO, "12"), (RegionScope.SIDO, "30")]  # 부산을 맨 앞에
    assert multi.region_key() == "26"
    # 청주시 구 4곳은 지역 표가 있으면 청주시 하나로 묶는다. 표가 없으면 시·도로 둔다
    assert [(r.scope, r.sigungu) for r in youth(CHEONGJU, names=names).regions] == [(RegionScope.SIGUNGU, "43110")]
    assert [(r.scope, r.sido) for r in youth(CHEONGJU).regions] == [(RegionScope.SIDO, "43")]


@pytest.mark.parametrize("raw,names,expected", [
    ("26380", None, [("SIGUNGU", "26", "26380")]),
    ("26380,26350", None, [("SIDO", "26", None)]),
    ("43110,43111,43113", None, [("SIGUNGU", "43", "43110")]),  # 시와 그 시의 구
    ("36110", "table", [("SIDO", "36", None)]),                 # 세종은 시·군·구가 하나뿐이다
    ("12110", None, [("SIGUNGU", "12", "12110")]),              # 2026년 전남광주 통합 코드
    ("11110,26380", "first", [("SIDO", "26", None), ("SIDO", "11", None)]),
    ("99999, abc", None, []),
    ("", None, []),
])
def test_parse_policy_regions(raw, names, expected):
    table = region_names() if names == "table" else None
    regions = parse_policy_regions(raw, region_names=table, first_sido="26")
    assert [(r.scope, r.sido, r.sigungu) for r in regions] == expected


def test_policy_without_region_is_skipped():
    with pytest.raises(SkipRecord) as caught:
        youth(SAHA, zipCd="")
    assert caught.value.reason == "missing_region"  # 지역을 모르면 전국 정책으로 만들지 않는다


def test_policy_age_uses_nonzero_values_only():
    assert (youth(SAHA).age_min, youth(SAHA).age_max) == (None, None)  # 0/0은 제한 없음
    housing = youth(BUSAN_HOUSING)
    assert (housing.age_min, housing.age_max) == (18, 39)
    assert (housing.eligibility.age_min, housing.eligibility.age_max) == (18, 39)
    national = youth(NATIONAL)  # 제한 여부가 N이어도 나이가 있으면 쓴다 (field_maps 주석의 분포 참고)
    assert youth_records()[NATIONAL]["sprtTrgtAgeLmtYn"] == "N" and (national.age_min, national.age_max) == (19, 39)


def test_policy_age_flag_rule_can_be_switched(monkeypatch):
    from opportunity.ingest import normalize
    monkeypatch.setattr(normalize, "AGE_ONLY_WHEN_LIMIT_FLAG_Y", True)
    assert (youth(NATIONAL).age_min, youth(NATIONAL).age_max) == (None, None)  # N이면 쓰지 않는다
    assert (youth(BUSAN_HOUSING).age_min, youth(BUSAN_HOUSING).age_max) == (18, 39)  # Y


def test_policy_apply_periods():
    saha = youth(SAHA)
    assert (saha.apply_start, saha.apply_end, saha.application.period_type) == (
        "2026-01-01", "2026-12-31", PeriodType.FIXED)
    always = youth(AI_HUB)
    assert (always.apply_start, always.apply_end, always.application.period_type) == (
        None, "9999-12-31", PeriodType.ALWAYS)
    closed = youth(SUYEONG_CLOSED)
    assert (closed.apply_start, closed.application.period_type) == (None, PeriodType.TBD)  # 날짜를 만들지 않는다


@pytest.mark.parametrize("text,code,biz,expected", [
    ("20261119 ~ 20261204", "0057001", ("", ""), ("2026-11-19", "2026-12-04", PeriodType.FIXED)),
    ("20260101 ~ 20261231\\N20270101 ~ 20271231", "0057001", ("", ""),
     ("2026-01-01", "2026-12-31", PeriodType.FIXED)),
    ("20250101 ~ 20251231\\N20260101 ~ 20261119", "0057001", ("", ""),
     ("2026-01-01", "2026-11-19", PeriodType.FIXED)),                       # 다 끝났으면 마지막 기간
    ("         ~         ", "0057001", ("", ""), (None, "9999-12-31", PeriodType.TBD)),
    ("", "0057002", ("20260101", "20261231"), ("2026-01-01", "9999-12-31", PeriodType.ALWAYS)),
    ("", "0057002", ("20250101", "20251231"), (None, "9999-12-31", PeriodType.TBD)),  # 사업이 끝난 상시
    ("", "0057002", ("", ""), (None, "9999-12-31", PeriodType.ALWAYS)),
    ("", "0057003", ("20260101", "20261231"), (None, "9999-12-31", PeriodType.TBD)),
    ("", "", ("", ""), (None, "9999-12-31", PeriodType.TBD)),
])
def test_parse_apply_period(text, code, biz, expected):
    assert parse_apply_period(text, code, biz[0], biz[1], "2026-11-20") == expected


def test_policy_selection_category_stage():
    housing = youth(BUSAN_HOUSING)
    assert housing.application.selection == Selection.FIRST_COME
    assert (housing.category, housing.stage) == ("HOUSING", PolicyStage.SETTLE)
    saha = youth(SAHA)
    assert saha.application.selection == Selection.REVIEW and (saha.category, saha.stage) == ("JOB", PolicyStage.PREPARE)
    hub = youth(AI_HUB)
    assert (hub.category, hub.stage) == ("교육･직업훈련", PolicyStage.PREPARE)  # 모르는 분류는 원문 그대로
    assert youth(BUSAN_EMPLOYED).stage == PolicyStage.EMPLOYED  # 중분류 재직자
    assert youth(SAHA, lclsfNm="교육,일자리").category == "JOB"
    assert youth(SAHA, lclsfNm="교육･직업훈련,교육･직업훈련").category == "교육･직업훈련"


def test_policy_income_conditions():
    housing = youth(BUSAN_HOUSING)  # 기타(추정 0043003): 원문 그대로
    assert housing.income_rule == "기준중위소득 120%이하(월 3,078천원 이하)"
    assert housing.eligibility.income.text == housing.income_rule
    assert housing.eligibility.income.max_monthly_income is None  # 글에서 숫자를 뽑지 않는다
    closed = youth(SUYEONG_CLOSED)  # 금액(추정 0043002)
    assert closed.income_rule == "소득 1~10,000만 원 · 공고문 확인"
    assert youth(SAHA).eligibility.income is None and youth(SAHA).income_rule is None  # 무관


@pytest.mark.parametrize("code,low,high,etc,expected", [
    ("0043001", "0", "0", "", None),
    ("0043001", "0", "0", "-", None),
    ("0043001", "0", "0", "중위소득 100% 이하", "중위소득 100% 이하"),
    ("0043002", "0", "5000", "", "소득 5,000만 원 이하 · 공고문 확인"),
    ("0043002", "2580", "5532", "", "소득 2,580~5,532만 원 · 공고문 확인"),
    ("0043002", "0", "0", "", "소득 조건 있음 · 공고문 확인"),
    ("0043002", "0", "5000", "청년 기준", "청년 기준 (소득 5,000만 원 이하 · 공고문 확인)"),
    ("0043003", "0", "0", "-", "소득 조건 있음 · 공고문 확인"),
    ("0043003", "0", "0", "중위소득 150% 이하", "중위소득 150% 이하"),
    ("", "", "", "", None),
])
def test_parse_income(code, low, high, etc, expected):
    rule = parse_income(code, low, high, etc)
    assert (rule.text if rule else None) == expected


def test_policy_free_text_conditions_and_amounts():
    housing = youth(BUSAN_HOUSING)
    checks = housing.eligibility.manual_checks
    assert len(checks) == 2 and checks[0].startswith("- ‘25. 1. 1.이후 부산시 전입")
    assert checks[1] == "참여 제한 대상: ※ 유사사업 수혜이력이 있는 자 등"
    assert youth(SAHA).eligibility.manual_checks == []  # 빈 값과 "해당 없음"은 넣지 않는다
    assert youth(SAHA, addAplyQlfcCndCn="해당 없음", ptcpPrpTrgtCn="-").eligibility.manual_checks == []
    assert housing.eligibility.employment is None  # jobCd 뜻을 몰라 제한을 만들지 않는다
    # 금액은 글에서 뽑지 않는다. 지원 내용 원문을 summary와 benefit에 둔다
    assert housing.amount_max is None and housing.benefit.public_share_max is None
    assert housing.summary.startswith("○ 지원내용 : 부동산 중개보수") and housing.benefit.text == housing.summary
    assert housing.checklist == ["제출 서류: 부동산임대차계약서, 중개보수 및 이사비 납부 영수증, 통장사본 등"]
    assert youth(SAHA, plcySprtCn="").summary.startswith(youth_records()[SAHA]["plcyExplnCn"].strip()[:10])


def test_policy_bad_or_missing_id_is_skipped():
    with pytest.raises(SkipRecord) as caught:
        youth(SAHA, plcyNo="2026#0004")
    assert caught.value.reason == "bad_id"
    with pytest.raises(SkipRecord) as caught:
        youth(SAHA, plcyNo="")
    assert caught.value.reason == "missing_id"
    with pytest.raises(SkipRecord) as caught:
        youth(SAHA, plcyNm=" ")
    assert caught.value.reason == "missing_title"


def test_fixtures_have_no_staff_names():
    for record in youth_records().values():
        assert record["sprvsnInstPicNm"] == "" and record["operInstPicNm"] == ""
    xml = (FIXTURES / "work24_gangso_region26000_p1.xml").read_bytes()
    assert all(not r.get("reperNm") for r in as_list(walk(parse_body(xml), "smallGiantsList.smallGiant")))


# ---------------------------------------------------------------- 강소기업
def gangso_records():
    xml = (FIXTURES / "work24_gangso_region26000_p1.xml").read_bytes()
    return as_list(walk(parse_body(xml), "smallGiantsList.smallGiant"))


def test_gangso_company_record():
    company = normalize_gangso(gangso_records()[0], as_of="2026-11-20")
    assert company.company_id == "biz-6088195805" and company.biz_no == "6088195805"
    assert (company.name, company.sido) == ("(주)이노폴", "26")
    assert company.industry == "화학물질 및 화학제품 제조업; 의약품 제외" and company.size == "상시근로자 79명"
    badge = company.highlights[0]
    assert (badge.type, badge.label, badge.source, badge.as_of) == (
        "GANGSO", "인재육성형중소기업", "고용노동부 청년일자리강소기업", "2024")
    assert company.source == "고용노동부 청년일자리강소기업" and company.as_of == "2026-11-20"


def test_gangso_without_year_has_no_badge_and_bad_rows_skip():
    record = gangso_records()[1]
    assert normalize_gangso({**record, "selYear": ""}, as_of="2026-11-20").highlights == []  # 기준일 없는 배지는 만들지 않는다
    with pytest.raises(SkipRecord) as caught:
        normalize_gangso({**record, "busiNo": ""}, as_of="2026-11-20")
    assert caught.value.reason == "missing_biz_no"
    with pytest.raises(SkipRecord) as caught:
        normalize_gangso({**record, "coNm": ""}, as_of="2026-11-20")
    assert caught.value.reason == "missing_name"


# ---------------------------------------------------------------- 공통코드
def test_region_code_table():
    names = region_names()
    assert names["26380"] == "부산 사하구" and names["26000"] == "부산" and names["12110"] == "전남광주 목포시"
    assert "00000" not in names  # 지역무관
    assert codes.sido_names(names) == {"11": "서울", "12": "전남광주", "26": "부산", "36": "세종", "43": "충북"}


def test_region_table_names_posting_labels():
    region = parse_region("26380", "", region_names=region_names())
    assert (region.sido, region.sigungu, region.label) == ("26", "26380", "부산 사하구")
    assert parse_region("12110", "", region_names=region_names()).label == "전남광주 목포시"
    assert parse_region("12110", "").label == "전남광주"  # 표가 없으면 시·도 이름만


def test_job_code_table():
    table = codes.job_codes((FIXTURES / "work24_codes_CMCD_2.xml").read_bytes())
    assert table["011100"] == {"name": "의회 의원", "middle": "행정·경영·금융·보험 관리직",
                               "major": "경영·사무·금융·보험"}
    assert len(table) == 3
