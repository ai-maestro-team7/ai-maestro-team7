import json
import sys
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTRACTS_DIR / "src"))  # PYTHONPATH 없이도 실행되게

FIXTURES = CONTRACTS_DIR / "fixtures"
SCHEMAS = CONTRACTS_DIR / "schemas"


def load_fixture(kind: str, contract: str) -> dict:
    return json.loads((FIXTURES / kind / f"{contract}.json").read_text(encoding="utf-8"))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
