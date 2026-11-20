"""첨삭·학습 경로 테스트 준비 (#113). 적합도 분석까지 끝낸 상태를 만들고, 자격·시험일정 대역을 더한다. 데이터는 모두 가상이다."""
import json
from datetime import timedelta

from mentoring.reference.models import Qualification, QualificationLink
from mentoring.store.results import MemoryExamSchedules, MemoryResultStore

from .factory import FIXED_NOW, run_pending
from .fit import USER, FakeNcs, fit_deps

BASE = "/api/v1/mentoring"
QUAL = "G521"  # 가상 데이터에서 쓰는 자격 코드


class FakeNcsWithQualifications(FakeNcs):
    """능력단위–자격 연계와 자격 정보(META). 같은 (능력단위, 자격, 구분)이 두 번 들어 있다 (UT-13)."""

    def list_qualification_links(self, unit_code):
        links = {
            "2001010501_23v2": [("G521", "선택"), ("G521", "선택"), ("X999", "선택")],
            "2001010502_23v2": [("G521", "필수")],
        }
        return [QualificationLink(unit_code=unit_code, qualification_code=q, name=f"자격 {q}", unit_type=t)
                for q, t in links.get(unit_code, [])]

    def get_qualification(self, code):
        if code != QUAL:  # X999는 자격 정보가 없다 → 후보에서 빠진다
            return None
        return Qualification(qualification_code=QUAL, name="사회조사분석사2급", exam_agency="가상 시행기관",
                             source_url="https://www.data.go.kr/data/example", collected_at="2026-11-20")


def exam_rows():
    past = {"description": "제1회", "docRegStartDt": "20260301", "docExamStartDt": "20260320", "docPassDt": "20260410",
            "pracPassDt": "20260520"}
    upcoming = {"description": "제4회", "docRegStartDt": "20261124", "docRegEndDt": "20261127",
                "docExamStartDt": "20261205", "docPassDt": "20261215", "pracExamStartDt": "20261212",
                "pracPassDt": "20261223"}
    return [past, upcoming]


def flow_deps(responses, *, exams="default", **kwargs):
    deps = fit_deps(responses, **kwargs)
    deps.ncs = FakeNcsWithQualifications()
    deps.results = MemoryResultStore()
    if exams == "default":
        exams = MemoryExamSchedules()
        exams.put(QUAL, FIXED_NOW.year, exam_rows(), collected_at="2026-11-21T06:00:00+09:00",
                  expires_at=int((FIXED_NOW + timedelta(days=1)).timestamp()))
    deps.exams = exams
    return deps


def call(rest_handler, deps, method, path, body=None, *, user_id=USER, headers=None):
    event = {
        "version": "2.0", "routeKey": "$default", "rawPath": BASE + path, "rawQueryString": "",
        "headers": {"content-type": "application/json", **(headers or {})},
        "requestContext": {"requestId": "req-test", "stage": "$default",
                           "http": {"method": method, "path": BASE + path, "protocol": "HTTP/1.1",
                                    "sourceIp": "127.0.0.1", "userAgent": "pytest"}},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else None, "isBase64Encoded": False,
    }
    response = rest_handler.handle(event, deps, user_id)
    return response["statusCode"], json.loads(response["body"])


def completed_analysis(rest_handler, deps, body=None) -> str:
    status, created = call(rest_handler, deps, "POST", "/analyses",
                           body or {"profileId": "profile-1", "jobPostingId": "job-demo-busan-001"})
    assert status == 202, created
    run_pending(deps)
    return created["analysisId"]
