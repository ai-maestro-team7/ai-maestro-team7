"""normalize.py: 해외취업 모집공고 → 스냅샷.

샘플(worldjob_p1.xml, worldjob_p2.xml)은 2026-11-20 실제 응답에서 뽑았다. 응답에 담당자·연락처 칸은 없다.
- p1: KOTRA 베트남(옷감과 사람들), KOTRA 미국(Sebang), 한국산업인력공단 독일(엔클로니)
- p2: 파크하얏트부산 국내 박람회 공고. 똑같은 행이 두 번 온다 (나라 "대한민국", 비자·언어 빈 값)
"""

from pathlib import Path

import pytest

from opportunity.core.copy_rules import OVERSEAS_LABEL
from opportunity.ingest.field_maps import WORLDJOB
from opportunity.ingest.http import as_list, parse_body, walk
from opportunity.ingest.normalize import (
    SkipRecord,
    normalize_postings,
    normalize_worldjob,
    parse_worldjob_region,
    worldjob_id,
)
from opportunity.models import (
    CareerType,
    EmploymentType,
    ExtractStatus,
    OrgType,
    PostingSource,
    SourceType,
)
from opportunity.models.posting import latest_from_snapshot

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = "2026-11-20T04:30:00+09:00"


@pytest.fixture
def rows() -> list[dict]:
    out = []
    for page in (1, 2):
        parsed = parse_body((FIXTURES / f"worldjob_p{page}.xml").read_bytes())
        out.extend(as_list(walk(parsed, WORLDJOB["list"]["items_path"])))
    return out


def by_org(rows, name):
    return next(r for r in rows if r["entNm"] == name)


def test_overseas_posting(rows):
    snap = normalize_worldjob(by_org(rows, "CLOTH AND PEOPLE VINA"), as_of=AS_OF)
    assert snap.job_posting_id.startswith("wj-") and len(snap.job_posting_id) == len("wj-") + 16
    assert (snap.source, snap.source_type, snap.org_type) == (PostingSource.WORLDJOB, SourceType.OFFICIAL,
                                                               OrgType.PRIVATE)
    assert snap.title == "[KOTRA] 베트남, 옷감과 사람들, 원부자재 및 영업부 (1명)"
    region = snap.work_region
    assert (region.overseas, region.country, region.sido, region.unknown) == (True, "베트남", None, False)
    assert region.label == OVERSEAS_LABEL.format(country="베트남")
    assert snap.job.name == "영업관리 사무원" and snap.career_type == CareerType.EXPERIENCED
    assert snap.closes_at == "2026-12-03" and snap.rolling is False
    assert snap.salary.disclosed is False and snap.official_url is None  # 응답에 급여·원문 링크가 없다
    assert snap.employment_type == EmploymentType.UNKNOWN
    assert snap.extract_status == ExtractStatus.PENDING
    assert "officialUrl" not in snap.extracted_by and "salary" not in snap.extracted_by


def test_description_keeps_conditions_as_text(rows):
    text = normalize_worldjob(by_org(rows, "엔클로니"), as_of=AS_OF).job_description
    assert text == ("[모집 개요]\n업종: 그외 기타 특수목적용 기계 제조업\n언어 조건: 독일어(필수) 상, 한국어(필수) 상\n"
                    "비자: 취업비자\n모집 인원: 1명\n공고 출처 기관: 한국산업인력공단")


def test_domestic_fair_posting_is_not_overseas(rows):
    snap = normalize_worldjob(by_org(rows, "호텔아이파크(주)부산"), as_of=AS_OF)
    assert snap.work_region.overseas is False and snap.work_region.unknown is True  # 시·도를 지어내지 않는다
    assert "비자" not in snap.job_description and "공고 출처 기관" not in snap.job_description  # 빈 값·해당사항 없음


def test_flags_are_not_busan_or_capital(rows, config):
    snap = normalize_worldjob(by_org(rows, "엔클로니"), as_of=AS_OF)
    latest = latest_from_snapshot(snap, busan_sido=config.data.busan_sido, capital_sido=config.data.capital_area_sido)
    assert (latest.is_overseas, latest.is_busan, latest.is_capital_area) == (True, False, False)


def test_identical_rows_collapse_to_one(rows):
    batch = normalize_postings(rows, normalize_worldjob, as_of=AS_OF)
    assert len(batch.snapshots) == 4 and batch.duplicates == 1 and batch.skipped == {}


def test_id_survives_deadline_extension(rows):
    row = by_org(rows, "엔클로니")
    a = normalize_worldjob(row, as_of=AS_OF)
    b = normalize_worldjob({**row, "rctntcEndDe": "2026-12-31", "rctntcNmprCo": "3"}, as_of=AS_OF)
    assert a.job_posting_id == b.job_posting_id and a.content_hash != b.content_hash
    c = normalize_worldjob(row, as_of="2026-11-21T04:30:00+09:00")
    assert c.content_hash == a.content_hash
    other = normalize_worldjob({**row, "rctntcSj": "다른 공고"}, as_of=AS_OF)
    assert other.job_posting_id != a.job_posting_id
    assert worldjob_id(row) == a.job_posting_id.removeprefix("wj-")


@pytest.mark.parametrize(("field", "reason"), [("rctntcSj", "missing_title"), ("entNm", "missing_organization"),
                                               ("rctntcEndDe", "no_deadline")])
def test_missing_values_are_skipped(rows, field, reason):
    with pytest.raises(SkipRecord) as e:
        normalize_worldjob({**rows[0], field: ""}, as_of=AS_OF)
    assert e.value.reason == reason


def test_parse_region_edges():
    assert parse_worldjob_region("").unknown is True
    assert parse_worldjob_region("대한민국").overseas is False
    assert parse_worldjob_region(" 일본 ").country == "일본"
