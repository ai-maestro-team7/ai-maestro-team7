import pytest

from interview import settings, versions
from interview.errors import AWS_SERVICE_ERROR, InterviewError


def test_model_id_required(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(InterviewError) as exc:
        settings.model_id()
    assert exc.value.code == AWS_SERVICE_ERROR
    assert exc.value.retryable is False


def test_model_id_blank_is_missing(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "   ")
    with pytest.raises(InterviewError):
        settings.model_id()


def test_model_id_read_at_call_time(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model-a")
    assert settings.model_id() == "test-model-a"
    monkeypatch.setenv("MODEL_ID", "test-model-b")
    assert settings.model_id() == "test-model-b"


def test_region_default_and_override(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert settings.region() == "ap-northeast-2"
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    assert settings.region() == "us-east-1"


def test_max_tokens_default_and_override(monkeypatch):
    monkeypatch.delenv("INTERVIEW_MAX_TOKENS", raising=False)
    assert settings.max_tokens() == 1024
    monkeypatch.setenv("INTERVIEW_MAX_TOKENS", "2048")
    assert settings.max_tokens() == 2048


@pytest.mark.parametrize("raw", ["0", "-5", "abc"])
def test_max_tokens_invalid(monkeypatch, raw):
    monkeypatch.setenv("INTERVIEW_MAX_TOKENS", raw)
    with pytest.raises(InterviewError) as exc:
        settings.max_tokens()
    assert exc.value.retryable is False


@pytest.mark.parametrize("model_id, expected", [
    ("global.anthropic.claude-haiku-5-5", {"type": "disabled"}),
    ("anthropic.claude-haiku-5-5", {"type": "disabled"}),
    ("global.anthropic.claude-sonnet-5-5", {"type": "between_tools"}),
    ("global.anthropic.claude-opus-5-5", None),
    ("test-model", None),
])
def test_thinking_off_by_model(model_id, expected):
    assert settings.thinking_off(model_id) == expected


def test_thinking_off_returns_copy():
    settings.thinking_off("global.anthropic.claude-haiku-5-5")["type"] = "adaptive"
    assert settings.thinking_off("global.anthropic.claude-haiku-5-5") == {"type": "disabled"}


def test_versions():
    assert versions.SCORING_VERSION == "v2.0"  # 4차(#108) 분석 제외 기준 추가
    assert versions.PROMPT_VERSION == "A-v2/B-v1"
