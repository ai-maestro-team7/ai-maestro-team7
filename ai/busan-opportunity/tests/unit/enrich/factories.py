"""enrich 테스트용 공고·LLM 답 만들기. 공용 데모 데이터는 고치지 않고 여기서 deps에 더 넣는다."""

import json

from opportunity.models.enums import (
    ExtractStatus,
    OrgType,
    PostingSource,
    RemoteWork,
    SourceType,
)
from opportunity.models.posting import (
    Company,
    Job,
    PostingSnapshot,
    Salary,
    WorkRegion,
    latest_from_snapshot,
)

HAEUNDAE = ("26", "26350", "부산 해운대구")
GANGNAM = ("11", "11680", "서울 강남구")
DATA_JOB = ("D0101", "D01", "D", "데이터 분석가")

DESCRIPTION = "\n".join([
    "데이터 분석 업무를 맡는다.",
    "[필수] SQL 활용 가능자",
    "[우대] ADsP 자격 보유자",
    "학력: 학사 이상",
    "신입 지원 가능",
    "정보처리기사 자격증 필수",
    "통계학 전공자만 지원 가능",
    "전형: 서류전형 → 면접전형",
    "제출 서류: 이력서, 자기소개서",
    "재택 근무 주 2회 가능",
])


def snapshot(pid="wk24-TEST0001", *, title="데이터 분석 신입", description=DESCRIPTION, region=HAEUNDAE,
             org="(주)테스트데이터", company_id=None, biz_no=None, status=ExtractStatus.PENDING,
             extracted_by=None, closes="2026-12-31", salary=(3400, 3800), remote=RemoteWork.UNKNOWN,
             org_type=OrgType.PRIVATE, job=DATA_JOB, requirements=None, rules=None) -> PostingSnapshot:
    sido, sigungu, label = region
    code, middle, major, name = job
    return PostingSnapshot(
        job_posting_id=pid, snapshot_id=f"20261121-{pid[-4:]}", title=title, organization=org, company_id=company_id,
        job_description=description, requirements=requirements or [], eligibility_rules=rules or [],
        closes_at=closes, official_url=f"https://example.invalid/{pid}", source_type=SourceType.DEMO,
        checked_at="2026-11-21T04:40:00+09:00", source=PostingSource.WORK24,
        company=Company(name=org, biz_no=biz_no, hq_sido=sido), org_type=org_type,
        work_region=WorkRegion(sido=sido, sigungu=sigungu, label=label, unknown=sido is None),
        job=Job(code=code, middle=middle, major=major, name=name),
        salary=Salary(disclosed=True, min=salary[0], max=salary[1]) if salary else Salary(), remote_work=remote,
        extract_status=status, extracted_by=extracted_by or {}, content_hash=f"test-{pid}",
    )


def store(deps, snap: PostingSnapshot) -> PostingSnapshot:
    """스냅샷과 LATEST를 카탈로그에 넣는다."""
    deps.catalog.put_snapshot(snap)
    deps.catalog.put_latest(latest_from_snapshot(snap, busan_sido=deps.config.data.busan_sido,
                                                 capital_sido=deps.config.data.capital_area_sido))
    return snap


def stored(deps, pid: str) -> PostingSnapshot:
    latest = deps.catalog.get_latest(pid)
    return deps.catalog.get_snapshot(pid, latest.snapshot_id)


def extract_reply(**overrides) -> str:
    """DESCRIPTION에 맞는 정상 답. overrides로 항목을 바꾼다."""
    body = {
        "required": [{"name": "SQL", "quote": "[필수] SQL 활용 가능자"}],
        "preferred": [{"name": "ADsP", "quote": "[우대] ADsP 자격 보유자"}],
        "certificates": [{"name": "정보처리기사", "quote": "정보처리기사 자격증 필수"}],
        "majors": {"values": ["통계학"], "quote": "통계학 전공자만 지원 가능"},
        "educationMin": {"value": "BACHELOR", "quote": "학력: 학사 이상"},
        "careerType": {"value": "NEW", "minYears": None, "quote": "신입 지원 가능"},
        "remoteWork": {"value": "HYBRID", "quote": "재택 근무 주 2회 가능"},
        "selectionSteps": [{"name": "서류전형", "quote": "전형: 서류전형 → 면접전형"},
                           {"name": "면접전형", "quote": "전형: 서류전형 → 면접전형"}],
        "documents": [{"name": "이력서", "quote": "제출 서류: 이력서, 자기소개서"},
                      {"name": "자기소개서", "quote": "제출 서류: 이력서, 자기소개서"}],
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False)


def explain_reply(*sentences: str) -> str:
    return json.dumps({"sentences": list(sentences)}, ensure_ascii=False)
