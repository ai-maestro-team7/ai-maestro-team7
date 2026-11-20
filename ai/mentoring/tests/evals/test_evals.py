from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).parents[2] / "evals" / "data" / "resumes"


def _load_resume_cases() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(DATA.glob("*.json"))]


def test_resume_answer_set_has_12_valid_virtual_cases() -> None:
    cases = _load_resume_cases()

    assert len(cases) == 12
    assert len({case["resumeId"] for case in cases}) == 12
    assert sum(case["ncsCode"] == "20010105" for case in cases) == 6
    assert {case["ncsCode"] for case in cases if case["ncsCode"] != "20010105"} == {
        "02020201",
        "02030201",
        "02010301",
        "06010201",
        "15040102",
        "12030102",
    }
    for case in cases:
        assert case["documentType"] == "RESUME"
        assert "가상 지원자" in case["text"]
        assert "010-0000-XXXX" in case["text"]
        assert re.search(r"[a-z0-9-]+@example\.com", case["text"])
        assert case["expectedSkills"]
        for skill in case["expectedSkills"]:
            assert skill["quote"] in case["text"]
            assert skill["evidenceLevel"] in {"EVIDENCED", "PARTIAL", "SELF_REPORTED"}


def test_resume_files_are_plain_json_objects() -> None:
    for path in DATA.glob("*.json"):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
