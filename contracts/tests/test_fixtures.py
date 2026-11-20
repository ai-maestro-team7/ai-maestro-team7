"""Fixture_Set 검사 (R9.9, R10.7, R11.1~11.5, R11.8~11.11)."""
import re

import pytest
from conftest import FIXTURES, load_fixture

from team07_contracts import (CONTRACTS, COMMON_STATUSES, ERROR_CODES, STATUS_EXTENSIONS, ContractValidationError,
                              Part, PostingForAnalysis, dump, to_interview_job_context, to_job_requirement_view,
                              validate)

CONVERTERS = {"JobRequirementView": to_job_requirement_view, "InterviewJobContext": to_interview_job_context}
NAMES = sorted(CONTRACTS)


def _examples(kind):
    for contract in NAMES:
        doc = load_fixture(kind, contract)
        for example in doc["examples"]:
            yield pytest.param(contract, doc, example, id=f"{kind}/{contract}/{example['name']}")


def _validate(contract, doc, example):
    part = (example.get("context") or {}).get("part")
    return validate(contract, example["data"], schema_version=doc["schemaVersion"], part=part)


@pytest.mark.parametrize("contract", NAMES)
def test_each_contract_has_valid_and_invalid_file(contract):
    for kind in ("valid", "invalid"):
        doc = load_fixture(kind, contract)
        assert doc["contract"] == contract, f"{kind}/{contract}.json: contract 이름이 달라요"
        assert doc["schemaVersion"] == CONTRACTS[contract].schema_version, (
            f"{kind}/{contract}.json: schemaVersion {doc['schemaVersion']} != 현재 {CONTRACTS[contract].schema_version}")
        assert doc["examples"], f"{kind}/{contract}.json: 예시가 없어요"


@pytest.mark.parametrize("contract,doc,example", list(_examples("valid")))
def test_valid_examples_pass_and_round_trip(contract, doc, example):
    path = f"fixtures/valid/{contract}.json#{example['name']}"
    try:
        model = _validate(contract, doc, example)
    except ContractValidationError as exc:
        pytest.fail(f"{path} [{contract}] 기대: 통과, 실제: 거부 {exc.fields}")
    assert dump(model) == example["data"], f"{path} [{contract}] 직렬화 결과가 원래 예시와 달라요"


@pytest.mark.parametrize("contract,doc,example", [p for p in _examples("valid") if "derivedFrom" in p.values[2]])
def test_derived_examples_match_converter(contract, doc, example):
    source_contract, source_name = example["derivedFrom"].split("/", 1)
    source = next(e for e in load_fixture("valid", source_contract)["examples"] if e["name"] == source_name)
    actual = dump(CONVERTERS[contract](PostingForAnalysis.model_validate(source["data"])))
    assert actual == example["data"], (
        f"fixtures/valid/{contract}.json#{example['name']} [{contract}] 기대: {example['derivedFrom']} 변환 결과와 같음, 실제: 다름")


@pytest.mark.parametrize("contract,doc,example", list(_examples("invalid")))
def test_invalid_examples_rejected_with_expected_fields(contract, doc, example):
    path = f"fixtures/invalid/{contract}.json#{example['name']}"
    expected = set(example["expectedErrorFields"])
    stage = example["stage"]
    try:
        if stage == "validate":
            _validate(contract, doc, example)
        else:
            source = validate(example["sourceContract"], example["data"], schema_version="1.0")
            {"to_interview_job_context": to_interview_job_context, "to_job_requirement_view": to_job_requirement_view}[stage](source)
    except ContractValidationError as exc:
        missing = expected - set(exc.fields)
        assert not missing, f"{path} [{contract}] 기대 오류 필드: {sorted(expected)}, 실제: {exc.fields}"
        return
    pytest.fail(f"{path} [{contract}] 기대: {sorted(expected)} 오류로 거부, 실제: 통과")


def test_no_long_digit_runs_in_fixtures():
    """12자리 이상 연속 숫자는 계정 ID 검사와 헷갈리므로 넣지 않는다 (R11.11)."""
    long_digits = re.compile(r"\d{12,}")
    for path in sorted(FIXTURES.rglob("*.json")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not long_digits.search(line), f"{path.relative_to(FIXTURES)}:{no} 12자리 이상 연속 숫자"


def test_no_personal_data_shapes_in_fixtures():
    """이메일·전화번호·주민등록번호 모양 문자열이 없다 (R11.6)."""
    patterns = [re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), re.compile(r"01[016789]-?\d{3,4}-?\d{4}"),
                re.compile(r"\d{6}-[1-4]\d{6}")]
    for path in sorted(FIXTURES.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        for p in patterns:
            assert not p.search(text), f"{path.relative_to(FIXTURES)}: 개인정보 모양 문자열 ({p.pattern})"


# ---------------------------------------------------------------- 구성 확인


def _valid(contract):
    return load_fixture("valid", contract)["examples"]


def test_error_example_for_every_code():
    codes = {e["data"]["error"]["code"] for e in _valid("ErrorEnvelope")}
    assert codes == set(ERROR_CODES)


def test_async_example_for_every_status_and_extension():
    seen_status, seen_stage = set(), set()
    for e in _valid("AsyncTaskStatus"):
        seen_status.add(e["data"]["status"])
        if "stage" in e["data"]:
            seen_stage.add(e["data"]["stage"])
        if e["data"]["status"] == "FAILED":
            assert "error" in e["data"]
    extra = {s for spec in STATUS_EXTENSIONS.values() for s in spec.extra_statuses}
    assert set(COMMON_STATUSES) | extra <= seen_status
    assert STATUS_EXTENSIONS[Part.C].field_extensions["stage"] <= seen_stage
    assert any(e["data"].get("report", "absent") is None for e in _valid("AsyncTaskStatus"))


def test_three_personas():
    names = {e["name"] for e in _valid("CommonProfile")}
    assert {"persona-1-seoul-weighing", "persona-2-stay-busan", "persona-3-public-institution"} <= names


def test_postings_cover_busan_and_capital_area():
    postings = [e["data"] for e in _valid("PostingForAnalysis")]
    sidos = {p["workRegion"].get("sido") for p in postings}
    assert "26" in sidos and sidos & {"11", "41", "28"}
    for p in postings:
        assert p["sourceType"] == "DEMO" and "가상" in p["organization"]
    assert any(p["workRegion"]["unknown"] for p in postings)
    assert any(p["isExpired"] for p in postings)


def test_career_summary_examples():
    examples = {e["name"]: e["data"] for e in _valid("CareerProfileSummary")}
    plain = examples["c-spec-example"]
    assert "profileId" not in plain and "profileVersion" not in plain
    tracked = examples["c-spec-example-with-profile"]
    assert tracked["profileId"] == "profile-demo" and tracked["profileVersion"] == 1
    demo = examples["data-analysis-demo"]
    assert all(demo[k] for k in ("projects", "skills", "needsConfirmation"))
