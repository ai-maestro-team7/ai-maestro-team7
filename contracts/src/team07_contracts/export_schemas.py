"""계약 모델에서 JSON Schema를 만든다 (R11.7, 프론트·비 Python 소비자용).

    PYTHONPATH=contracts/src python -m team07_contracts.export_schemas [--out contracts/schemas]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .registry import CONTRACTS

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "schemas"


def build_schemas() -> dict[str, dict]:
    out = {}
    for name, meta in CONTRACTS.items():
        schema = meta.model.model_json_schema(by_alias=True, mode="validation")
        schema["title"] = name
        schema["x-schemaVersion"] = meta.schema_version
        schema["x-owner"] = meta.owner.value
        schema["x-consumers"] = [p.value for p in meta.consumers]
        schema["x-sources"] = list(meta.sources)
        out[name] = schema
    return out


def render(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, schema in build_schemas().items():
        (args.out / f"{name}.schema.json").write_text(render(schema), encoding="utf-8")
        print(f"{name}.schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
