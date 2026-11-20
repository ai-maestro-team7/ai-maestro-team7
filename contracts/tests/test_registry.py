"""계약 목록 메타데이터와 커밋된 JSON Schema 검사 (R7.7, R8.9, R9.4, R10.1, R10.4, R11.7)."""
import re

import pytest
from conftest import SCHEMAS

from team07_contracts import CONTRACTS, Part
from team07_contracts.export_schemas import build_schemas, render


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_meta(name):
    meta = CONTRACTS[name]
    assert meta.name == name
    assert re.fullmatch(r"\d+\.\d+", meta.schema_version)
    assert isinstance(meta.owner, Part)
    assert meta.consumers and all(isinstance(p, Part) for p in meta.consumers)
    assert meta.owner not in meta.consumers
    assert meta.sources


def test_owners_match_design():
    owners = {name: meta.owner for name, meta in CONTRACTS.items()}
    assert owners["CommonProfile"] is Part.BACKEND
    assert owners["PostingForAnalysis"] is Part.B
    assert owners["CareerProfileSummary"] is Part.A
    assert Part.C in CONTRACTS["CareerProfileSummary"].consumers  # A → C 단방향 (R9.4)


@pytest.mark.parametrize("name,schema", sorted(build_schemas().items()))
def test_committed_schema_is_up_to_date(name, schema):
    path = SCHEMAS / f"{name}.schema.json"
    assert path.exists(), f"{path.name}이 없어요. python -m team07_contracts.export_schemas 를 실행하세요"
    assert path.read_text(encoding="utf-8") == render(schema), (
        f"{path.name}이 모델과 달라요. python -m team07_contracts.export_schemas 를 다시 실행하세요")


def test_no_stray_schema_files():
    assert {p.name for p in SCHEMAS.glob("*.schema.json")} == {f"{n}.schema.json" for n in CONTRACTS}
