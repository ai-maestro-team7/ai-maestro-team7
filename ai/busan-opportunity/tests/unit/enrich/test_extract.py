"""요건 추출: 스키마 검사, 원문 대조, API 값 보존, 다시 시도."""

from unit.enrich import factories as f

from opportunity.enrich import prompts
from opportunity.enrich.extract import extract_requirements, parse_output, quote_in_source
from opportunity.models.enums import (
    CareerType,
    EducationLevel,
    ExtractedBy,
    ExtractStatus,
    RemoteWork,
    RequirementKind,
    RuleType,
)
from opportunity.models.posting import EligibilityRule
from opportunity.store.memory import ScriptedLlm


def run(deps, snap, *replies):
    deps.llm = ScriptedLlm(list(replies))
    return extract_requirements(deps, snap)


def test_extract_fills_requirements_and_rules(deps):
    result = run(deps, f.snapshot(), f.extract_reply())
    snap = result.snapshot
    assert result.status == ExtractStatus.DONE and snap.extract_status == ExtractStatus.DONE
    assert [(r.name, r.kind) for r in snap.requirements] == [("SQL", RequirementKind.REQUIRED_SKILL),
                                                             ("ADsP", RequirementKind.PREFERRED_SKILL)]
    assert snap.requirements[0].source_quote == "[필수] SQL 활용 가능자"
    rules = {r.type: r for r in snap.eligibility_rules}
    assert rules[RuleType.EDUCATION].value == "BACHELOR"
    assert rules[RuleType.CAREER].value == {"type": "NEW"}
    assert rules[RuleType.CERTIFICATE].value == "정보처리기사"
    assert rules[RuleType.MAJOR].value == ["통계학"]
    assert all(r.source_quote for r in snap.eligibility_rules)
    assert snap.education_min == EducationLevel.BACHELOR and snap.career_type == CareerType.NEW
    assert snap.remote_work == RemoteWork.HYBRID
    assert snap.selection_steps == ["서류전형", "면접전형"] and snap.documents == ["이력서", "자기소개서"]
    for name in ("requirements", "eligibilityRules", "educationMin", "careerType", "remoteWork", "selectionSteps",
                 "documents"):
        assert snap.extracted_by[name] == ExtractedBy.LLM


def test_extract_wraps_posting_in_tag(deps):
    run(deps, f.snapshot(), f.extract_reply())
    system, user = deps.llm.calls[0]
    assert prompts.DATA_RULE in system
    assert user.count("<posting>") == 1 and user.count("</posting>") == 1
    body = user.split("<posting>")[1].split("</posting>")[0]
    assert "[필수] SQL 활용 가능자" in body and "데이터 분석 신입" in body


def test_extract_drops_items_whose_quote_is_not_in_source(deps):
    reply = f.extract_reply(
        required=[{"name": "SQL", "quote": "[필수] SQL 활용 가능자"},
                  {"name": "Kubernetes", "quote": "Kubernetes 운영 경험 필수"}],
        certificates=[{"name": "SQLD", "quote": "SQLD 필수"}],
        educationMin={"value": "MASTER", "quote": "석사 이상"},
    )
    result = run(deps, f.snapshot(), reply)
    snap = result.snapshot
    assert [r.name for r in snap.requirements if r.kind == RequirementKind.REQUIRED_SKILL] == ["SQL"]
    assert all(r.value != "SQLD" for r in snap.eligibility_rules)
    assert snap.education_min is None
    assert all(r.type != RuleType.EDUCATION for r in snap.eligibility_rules)
    assert {"Kubernetes", "SQLD", "educationMin"} <= set(result.dropped)
    assert all(quote_in_source(r.source_quote, f.DESCRIPTION) for r in snap.requirements)


def test_quote_check_ignores_only_whitespace():
    source = "학력: 학사 이상\n신입 지원 가능"
    assert quote_in_source("학력:  학사 이상", source)
    assert not quote_in_source("학력: 학사이상 우대", source)
    assert not quote_in_source("", source) and not quote_in_source(None, source)


def test_extract_keeps_api_values(deps):
    api_rule = EligibilityRule(rule_id="rule-edu", type=RuleType.EDUCATION, value="ASSOCIATE", source_quote="API")
    snap = f.snapshot(remote=RemoteWork.NONE, rules=[api_rule],
                      extracted_by={"closesAt": ExtractedBy.API, "workRegion": ExtractedBy.API,
                                    "salary": ExtractedBy.API, "remoteWork": ExtractedBy.API,
                                    "educationMin": ExtractedBy.API})
    snap = snap.model_copy(update={"education_min": EducationLevel.ASSOCIATE})
    out = run(deps, snap, f.extract_reply()).snapshot
    assert out.closes_at == snap.closes_at and out.work_region == snap.work_region and out.salary == snap.salary
    assert out.remote_work == RemoteWork.NONE and out.education_min == EducationLevel.ASSOCIATE
    assert [r.value for r in out.eligibility_rules if r.type == RuleType.EDUCATION] == ["ASSOCIATE"]
    for name in ("closesAt", "workRegion", "salary", "remoteWork", "educationMin"):
        assert out.extracted_by[name] == ExtractedBy.API
    assert out.extracted_by["requirements"] == ExtractedBy.LLM  # API가 주지 않은 값은 채운다


def test_extract_keeps_api_rules_when_rules_owned_by_api(deps):
    rules = [EligibilityRule(rule_id="rule-api", type=RuleType.OTHER, value="API", source_quote="API")]
    snap = f.snapshot(rules=rules, extracted_by={"eligibilityRules": ExtractedBy.API})
    out = run(deps, snap, f.extract_reply()).snapshot
    assert out.eligibility_rules == rules and out.extracted_by["eligibilityRules"] == ExtractedBy.API


def test_extract_retries_once_then_succeeds(deps):
    result = run(deps, f.snapshot(), "요건은 다음과 같다", f.extract_reply())
    assert result.status == ExtractStatus.DONE and result.attempts == 2 and len(deps.llm.calls) == 2


def test_extract_fails_after_two_bad_replies(deps):
    bad_schema = f.extract_reply(educationMin={"value": "PHD", "quote": "학력: 학사 이상"})
    result = run(deps, f.snapshot(), "not json", bad_schema, f.extract_reply())
    assert result.status == ExtractStatus.FAILED and result.snapshot.extract_status == ExtractStatus.FAILED
    assert len(deps.llm.calls) == 2  # 세 번째는 부르지 않는다
    assert result.snapshot.requirements == []


def test_extract_counts_llm_error_as_failure(deps):
    class Broken:
        def invoke(self, system, user, *, max_tokens=1024):
            raise RuntimeError("throttled")

    deps.llm = Broken()
    assert extract_requirements(deps, f.snapshot()).status == ExtractStatus.FAILED


def test_extract_without_llm_does_nothing(deps):
    deps.llm = None
    snap = f.snapshot()
    assert extract_requirements(deps, snap).snapshot == snap


def test_parse_output_accepts_code_fence():
    out = parse_output("```json\n" + f.extract_reply() + "\n```")
    assert out.required[0].name == "SQL"


def test_career_experienced_min_years(deps):
    text = "경력 3년 이상"
    snap = f.snapshot(description=text)
    reply = f.extract_reply(required=[], preferred=[], certificates=[], majors=None, educationMin=None,
                            remoteWork=None, selectionSteps=[], documents=[],
                            careerType={"value": "EXPERIENCED", "minYears": 3, "quote": text})
    out = run(deps, snap, reply).snapshot
    assert [r.value for r in out.eligibility_rules] == [{"type": "EXPERIENCED", "minYears": 3}]
    assert out.career_type == CareerType.EXPERIENCED and out.requirements == []
