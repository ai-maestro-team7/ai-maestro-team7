"""파트 경계를 넘는 계약에 이름이 정확히 `score`인 필드가 없어야 한다 (R3.11)."""
import pytest

from team07_contracts.export_schemas import build_schemas


def find_score_fields(contract_name: str, schema: dict) -> list[str]:
    """중첩 properties·items·$defs를 따라가며 이름이 정확히 score인 속성 경로를 돌려준다."""
    found: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, child in (node.get("properties") or {}).items():
                child_path = f"{path}.{key}" if path else key
                if key == "score":
                    found.append(f"{contract_name}:{child_path}")
                walk(child, child_path)
            for key, child in node.items():
                if key == "properties":
                    continue
                if key == "items":
                    walk(child, f"{path}[]")
                elif key == "$defs":
                    for def_name, d in child.items():
                        walk(d, f"$defs.{def_name}")
                elif isinstance(child, (dict, list)):
                    walk(child, path)
        elif isinstance(node, list):
            for child in node:
                walk(child, path)

    walk(schema, "")
    return found


def test_find_score_fields_examples():
    schema = {"properties": {"fitScore": {}, "items": {"type": "array", "items": {"properties": {"score": {}}}}},
              "$defs": {"X": {"properties": {"matchScore": {}, "score": {}}}}}
    assert find_score_fields("T", schema) == ["T:items[].score", "T:$defs.X.score"]
    assert find_score_fields("T", {"properties": {"fitScore": {}, "totalScore": {}}}) == []


@pytest.mark.parametrize("name,schema", sorted(build_schemas().items()))
def test_no_bare_score_field(name, schema):
    assert find_score_fields(name, schema) == []
