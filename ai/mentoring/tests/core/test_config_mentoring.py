"""설정 읽기 (Requirement 1 기준 5)."""
import json

import pytest

from mentoring.config import CONFIG_PATH, MissingEnvError, load_config, require_env


def test_default_config_loads():
    config = load_config()
    assert config.document.text_min_chars == 1000 and config.document.text_max_chars == 30000
    assert config.extraction.schema_retries == 1 and config.extraction.fact_retries == 1


def test_invalid_config_is_rejected():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["document"]["textMinChars"] = 50000
    with pytest.raises(ValueError):
        load_config(data=data)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["extraction"]["schemaRetries"] = 9
    with pytest.raises(ValueError):
        load_config(data=data)


def test_require_env_has_no_fallback(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(MissingEnvError, match="MODEL_ID"):
        require_env("MODEL_ID")
    monkeypatch.setenv("MODEL_ID", "x")
    assert require_env("MODEL_ID") == "x"
