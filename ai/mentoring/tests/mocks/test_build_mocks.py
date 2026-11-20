import json
import re
from pathlib import Path

from mocks.build_mocks import HERE, build, write


def _json_files(root: Path) -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.json"))}


def _assert_camel(value):
    if isinstance(value, dict):
        for key, child in value.items():
            assert "_" not in key
            _assert_camel(child)
    elif isinstance(value, list):
        for child in value:
            _assert_camel(child)


def test_generated_files_are_current_and_deterministic(tmp_path):
    write(tmp_path)
    first = _json_files(tmp_path)
    assert first == _json_files(HERE)
    write(tmp_path)
    assert _json_files(tmp_path) == first
    assert set(first) == {f"{name}.json" for name in build()}


def test_responses_use_camel_keys_and_common_error_shape():
    fixtures = build()
    for fixture in fixtures.values():
        _assert_camel(fixture["response"]["body"])
    errors = [value["response"]["body"]["error"] for name, value in fixtures.items() if name.startswith("ERROR_")]
    assert errors
    for error in errors:
        assert set(error) == {"code", "message", "requestId", "retryable", "details"}


def test_mock_artifacts_do_not_contain_contact_or_person_name_shapes():
    text = "\n".join(_json_files(HERE).values())
    assert not re.search(r"01[016789]-\d{3,4}-\d{4}", text)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    assert "가상 지원자" not in text


def test_required_flow_examples_exist():
    fixtures = build()
    assert fixtures["POST_documents_text"]["response"]["status"] == 202
    assert fixtures["GET_documents_id_EXTRACTED"]["response"]["body"]["extractionStatus"] == "EXTRACTED"
    assert fixtures["GET_documents_id_COMPLETED"]["response"]["body"]["extractionStatus"] == "COMPLETED"
    assert fixtures["GET_documents_id_REQUIRES_USER_REVIEW"]["response"]["body"]["extractionStatus"] == "REQUIRES_USER_REVIEW"
    assert fixtures["GET_profiles_me"]["response"]["status"] == 200
    assert fixtures["POST_profiles_id_confirm"]["response"]["status"] == 201
    assert {fixtures[name]["response"]["status"] for name in fixtures if name.startswith("ERROR_")} == {400, 404, 409, 501}
