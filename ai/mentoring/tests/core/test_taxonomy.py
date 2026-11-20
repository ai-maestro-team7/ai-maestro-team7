"""역량 표준 분류 (#104): 역량 이름은 자유, NCS 능력단위·직업기초능력 코드는 넘긴 목록에서만. 데이터는 모두 가상이다."""
import json

from mentoring.core.taxonomy import desired_ncs_codes, load_taxonomy
from mentoring.fit.store import MemoryAnalysisStore
from mentoring.llm.mock import MockLlm
from support.data import DATA_ANALYST_RESUME, QUOTE_PANDAS, QUOTE_SQL, QUOTE_TABLEAU
from support.factory import make_deps, run_pending
from support.fit import NCS_DATA, FakeNcs

USER = "user-tax"
UNIT_PROCESS = "2001010502_23v2"  # FakeNcs: 빅데이터 처리


def output():
    return {
        "skills": [
            {"name": "Python pandas 데이터 전처리", "evidenceLevel": "EVIDENCED", "ncsUnitCode": UNIT_PROCESS,
             "basicSkillId": "010", "quotes": [{"quotedText": QUOTE_PANDAS}]},
            {"name": "Tableau 대시보드", "evidenceLevel": "EVIDENCED", "ncsUnitCode": "9999999999_99v9",
             "basicSkillId": "999", "quotes": [{"quotedText": QUOTE_TABLEAU}]},
            {"name": "SQL 스터디 운영", "evidenceLevel": "PARTIAL", "ncsUnitCode": None, "basicSkillId": "003",
             "quotes": [{"quotedText": QUOTE_SQL}]},
        ],
        "projects": [], "experiences": [], "certificates": [], "needsConfirmation": [],
    }


def deps_with(basic_profile):
    deps = make_deps([output()], reference=None)
    deps.ncs = FakeNcs()
    deps.analyses = MemoryAnalysisStore()
    if basic_profile is not None:
        deps.analyses.put_basic_profile(USER, basic_profile)
    return deps


def extract(deps):
    from mentoring.core.documents import create_text_document
    from mentoring.models import TextDocumentRequest

    create_text_document(deps, USER, TextDocumentRequest.model_validate({"text": DATA_ANALYST_RESUME}))
    run_pending(deps)
    pointer = deps.users.get_profile_pointer(USER)
    return deps.users.get_profile_version(USER, pointer.latest_profile_id, pointer.latest_version)


def test_codes_are_kept_only_when_in_the_given_lists():
    deps = deps_with({"desiredJobs": [{"ncsCode": NCS_DATA, "name": "데이터 분석"}]})
    profile = extract(deps)
    skills = {s.name: s for s in profile.skills}
    assert skills["Python pandas 데이터 전처리"].ncs_unit_code == UNIT_PROCESS
    assert skills["Python pandas 데이터 전처리"].basic_skill_id == "010"
    assert skills["Tableau 대시보드"].ncs_unit_code is None and skills["Tableau 대시보드"].basic_skill_id is None
    assert skills["SQL 스터디 운영"].basic_skill_id == "003"
    assert profile.prompt_version == "profile-extract-v2"

    prompt = deps.llm.calls[0]["user"]
    lists = json.loads(prompt.split("<taxonomy>\n", 1)[1].split("\n</taxonomy>", 1)[0])
    assert [u["code"] for u in lists["ncsUnits"]] == ["2001010501_23v2", UNIT_PROCESS]
    assert {b["id"] for b in lists["basicSkills"]} == {"003", "010"}


def test_without_desired_job_only_basic_skills_are_offered():
    deps = deps_with(None)
    profile = extract(deps)
    prompt = deps.llm.calls[0]["user"]
    lists = json.loads(prompt.split("<taxonomy>\n", 1)[1].split("\n</taxonomy>", 1)[0])
    assert lists["ncsUnits"] == [] and len(lists["basicSkills"]) == 2
    # 능력단위 후보를 주지 않았고 기준 데이터 검사도 없으니(reference=None) 코드는 붙지 않는다
    assert all(s.ncs_unit_code is None for s in profile.skills)
    assert {s.basic_skill_id for s in profile.skills} == {"010", None, "003"}


def test_taxonomy_failure_does_not_stop_extraction():
    deps = deps_with({"desiredJobs": [{"ncsCode": NCS_DATA}]})

    def broken(_code):
        raise RuntimeError("reference down")

    deps.ncs.get_job_profile = broken
    profile = extract(deps)
    assert len(profile.skills) == 3 and all(s.basic_skill_id is None for s in profile.skills)


def test_desired_codes_are_validated_and_limited():
    jobs = {"desiredJobs": [{"ncsCode": "20010105"}, {"ncsCode": "bad"}, {"ncsCode": "20010105"},
                            {"ncsCode": "02020201"}, {"ncsCode": "13010101"}, {"ncsCode": "01010101"}]}
    assert desired_ncs_codes(jobs, 3) == ["20010105", "02020201", "13010101"]
    assert desired_ncs_codes(None, 3) == []
    assert load_taxonomy(make_deps(), USER).units == []  # Deps.ncs가 없으면 빈 목록
