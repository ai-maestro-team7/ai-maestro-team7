"""프론트에 넘긴 가짜 응답이 응답 모델과 맞는지 확인한다. 모델을 바꾸면 mocks도 다시 만든다."""

import importlib.util
import json
from pathlib import Path

MOCKS = Path(__file__).parents[2] / "mocks"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_mocks", MOCKS / "build_mocks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mock_files_match_models():
    built = load_builder().build()
    assert built
    for name, body in built.items():
        on_disk = json.loads((MOCKS / f"{name}.json").read_text(encoding="utf-8"))
        assert on_disk == body, f"{name}.json을 다시 만들어야 한다 (python mocks/build_mocks.py)"


def test_mock_keys_are_camel_case():
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert "_" not in key or key.isupper(), key
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in MOCKS.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
