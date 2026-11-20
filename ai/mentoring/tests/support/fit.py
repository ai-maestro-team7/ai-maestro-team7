"""직무 적합도 테스트 준비. 공고·NCS·KB·자격 판정을 모두 메모리 대역으로 둔다. 데이터는 모두 가상이다.
공고는 contracts `PostingForAnalysis.json`의 부산 데이터 분석 예시를 B 저장 형식(SNAP#)으로 옮긴 것이다 (D-37).
"""
from dataclasses import dataclass

from mentoring.fit.store import MemoryAnalysisStore, MemoryCatalog
from mentoring.models import CareerProfile, Certificate, Evidence, EvidenceLevel, FactStatus, Skill
from mentoring.reference.models import CompetencyUnit, JobProfile

from .factory import make_deps

USER = "user-a"
NCS_DATA = "20010105"  # 빅데이터분석


def busan_posting(**changes) -> dict:
    data = {
        "jobPostingId": "job-demo-busan-001", "snapshotId": "20261120-10c26293", "title": "데이터 분석 신입",
        "organization": "가상 데이터랩 부산", "job": {"name": "데이터 분석", "ncsCodes": [NCS_DATA]},
        "requirements": [
            {"requirementId": "req-1", "name": "SQL 데이터 추출", "kind": "REQUIRED_SKILL", "weight": 1.0,
             "sourceQuote": "SQL을 활용한 데이터 추출 및 가공 경험"},
            {"requirementId": "req-2", "name": "Python 분석", "kind": "REQUIRED_SKILL", "weight": 1.0,
             "sourceQuote": "Python 기반 데이터 분석 가능자"},
            {"requirementId": "req-3", "name": "시각화 도구", "kind": "PREFERRED_SKILL", "weight": 1.0,
             "sourceQuote": "Tableau 등 시각화 도구 사용 경험 우대"},
        ],
        "eligibilityRules": [{"ruleId": "rule-1", "type": "CERTIFICATE", "value": "ADsP",
                              "sourceQuote": "데이터분석 준전문가(ADsP) 소지자"}],
        "closesAt": "2026-12-04", "officialUrl": "https://example.com/postings/job-demo-busan-001",
        "checkedAt": "2026-11-20T04:30:00+09:00", "sourceType": "DEMO", "extractStatus": "DONE",
    }
    data.update(changes)
    return data


def profile(*, cert_status=FactStatus.VERIFIED, extra_skills=()) -> CareerProfile:
    evidence = [
        Evidence(evidence_id="ev-1", source_document_id="doc-1", page=1, start_char=0, end_char=10,
                 quoted_text="Python pandas로 결측치를 처리하고 정류장별 이용량을 집계했습니다."),
        Evidence(evidence_id="ev-2", source_document_id="doc-1", page=1, start_char=11, end_char=20,
                 quoted_text="분석 결과를 Tableau 대시보드로 만들어 발표했습니다."),
        Evidence(evidence_id="ev-3", source_document_id="doc-1", page=1, start_char=21, end_char=30,
                 quoted_text="교내 데이터 분석 동아리에서 SQL 스터디를 1년 동안 운영했습니다."),
        Evidence(evidence_id="ev-4", source_document_id="doc-1", page=1, start_char=31, end_char=40,
                 quoted_text="ADsP(데이터분석 준전문가) 취득"),
    ]
    skills = [
        Skill(skill_id="skill-1", name="데이터 전처리", evidence_level=EvidenceLevel.EVIDENCED,
              fact_status=FactStatus.VERIFIED, evidence_ids=["ev-1"]),
        Skill(skill_id="skill-2", name="데이터 시각화", evidence_level=EvidenceLevel.EVIDENCED,
              fact_status=FactStatus.NEEDS_CONFIRMATION, evidence_ids=["ev-2"]),
        Skill(skill_id="skill-3", name="SQL", evidence_level=EvidenceLevel.PARTIAL,
              fact_status=FactStatus.NEEDS_CONFIRMATION, evidence_ids=["ev-3"]),
        *extra_skills,
    ]
    return CareerProfile(profile_id="profile-1", profile_version=1, owner_user_id=USER, created_by="EXTRACTION",
                         skills=skills, evidence=evidence,
                         certificates=[Certificate(item_id="cert-1", name="ADsP", fact_status=cert_status,
                                                   evidence_ids=["ev-4"])],
                         created_at="2026-11-21T10:00:00+09:00")


GOOD_LINKS = {"links": [
    {"requirementId": "req-1", "skillIds": ["skill-3"], "evidenceIds": ["ev-3"]},
    {"requirementId": "req-2", "skillIds": ["skill-1"], "evidenceIds": ["ev-1"]},
    {"requirementId": "req-3", "skillIds": ["skill-2"], "evidenceIds": ["ev-2"]},
]}
SUMMARY = {"summary": "SQL과 Python 분석 경험이 공고 요건과 연결돼요. SQL은 본인 역할을 더 적어 주시면 좋아요."}


class FakeNcs:
    def __init__(self):
        self.profiles = {NCS_DATA: JobProfile(ncs_code=NCS_DATA, name="빅데이터분석")}
        self.units = {NCS_DATA: [
            CompetencyUnit(ncs_code=NCS_DATA, unit_code="2001010501_23v2", name="빅데이터 분석 기획"),
            CompetencyUnit(ncs_code=NCS_DATA, unit_code="2001010502_23v2", name="빅데이터 처리"),
        ]}

    def get_job_profile(self, ncs_code):
        return self.profiles.get(ncs_code)

    def list_units(self, ncs_code):
        return list(self.units.get(ncs_code, []))


@dataclass
class Hit:
    document_id: str
    job_role: str | None
    document_type: str | None
    source_url: str
    collected_at: str
    text: str


class FakeKnowledge:
    def __init__(self, hits=None, error=None):
        self.hits = hits if hits is not None else [
            Hit("job_profile_20010105_빅데이터분석", "빅데이터분석", "ncs_job_profile",
                "https://www.data.go.kr/data/15175388/fileData.do", "2026-11-20", "빅데이터분석은 데이터를 수집·처리한다."),
            Hit("team_career_mentoring_methodology_v1", "공통", "career_mentoring_methodology",
                "https://example.com/method", "2026-11-20", "경험은 STAR로 정리한다."),
        ]
        self.error = error
        self.calls = []

    def retrieve(self, query, *, job_role=None, k=None):
        self.calls.append({"query": query, "jobRole": job_role, "k": k})
        if self.error:
            raise self.error
        return list(self.hits)


_EDU = {"NONE": 0, "HIGH_SCHOOL": 1, "ASSOCIATE": 2, "BACHELOR": 3, "MASTER": 4, "DOCTOR": 5}


def fake_eligibility(profile, rules):
    """db-schema §3.2 규칙의 테스트 대역. 실제 함수는 backend/eligibility.py이고 A는 import하지 않는다."""
    conditions = []
    for rule in rules:
        if rule["type"] == "CERTIFICATE":
            name = rule["value"]
            if name in profile.get("certificates", []):
                result = "MET"
            elif name in profile.get("confirmedMissingCertificates", []):
                result = "NOT_MET"
            else:
                result = "UNKNOWN"
        elif rule["type"] == "EDUCATION":
            have = _EDU.get(profile.get("educationLevel"))
            result = "UNKNOWN" if have is None else ("MET" if have >= _EDU[rule["value"]] else "NOT_MET")
        else:
            result = "UNKNOWN"
        conditions.append({"ruleId": rule["ruleId"], "type": rule["type"], "result": result,
                           "reason": f"{rule['type']} {result}", "sourceQuote": rule.get("sourceQuote")})
    results = {c["result"] for c in conditions}
    status = ("INELIGIBLE" if "NOT_MET" in results else
              "NEEDS_VERIFICATION" if not conditions or "UNKNOWN" in results else "ELIGIBLE")
    return {"status": status, "conditions": conditions, "ruleVersion": "elig-test"}


def fit_deps(responses=None, *, career=None, posting=None, basic=None, knowledge="default", eligibility=fake_eligibility):
    from mentoring.llm.mock import MockLlm

    deps = make_deps()
    deps.llm = MockLlm(responses or [GOOD_LINKS, SUMMARY], model_id="mock-fit")
    deps.analyses = MemoryAnalysisStore()
    deps.catalog = MemoryCatalog()
    deps.ncs = FakeNcs()
    deps.knowledge = FakeKnowledge() if knowledge == "default" else knowledge
    deps.eligibility = eligibility
    deps.users.put_profile_version(career or profile(), expected_version=None)
    deps.catalog.put_posting(posting or busan_posting())
    if basic is not False:  # False면 기본 프로필이 없는 사용자
        deps.analyses.put_basic_profile(USER, basic or {"educationLevel": "BACHELOR", "major": "통계학",
                                                        "careerYears": 0})
    return deps
