import json
import logging
import sys
import types

import pytest
from pydantic import BaseModel

from fakes import FakeLLM
from interview import llm
from interview.errors import AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, INVALID_INPUT, InterviewError


class Out(BaseModel):
    value: int


def call(fake):
    return llm.call_json(fake, system_prompt="SYS", user_prompt="USER", schema=Out, stage="test")


# ---------------------------------------------------------------- extract_json


@pytest.mark.parametrize("raw", [
    '{"value": 1}',
    '  {"value": 1}\n',
    '```json\n{"value": 1}\n```',
    '```\n{"value": 1}\n```',
    'Here is the result:\n```JSON\n{"value": 1}\n```\nDone.',
    'Result: {"value": 1} (end)',
])
def test_extract_json_variants(raw):
    assert llm.extract_json(raw) == {"value": 1}


@pytest.mark.parametrize("raw", ["", "no json here", '{"value": ', None, 123])
def test_extract_json_failures(raw):
    with pytest.raises(ValueError):
        llm.extract_json(raw)


# ---------------------------------------------------------------- call_json


def test_success_first_try():
    fake = FakeLLM(['{"value": 7}'])
    assert call(fake).value == 7
    assert len(fake.calls) == 1
    assert fake.calls[0] == {"system": "SYS", "user": "USER"}


def test_retry_once_then_success():
    fake = FakeLLM(["not json", '{"value": 8}'])
    assert call(fake).value == 8
    assert len(fake.calls) == 2
    assert fake.calls[0] == fake.calls[1]  # 같은 요청을 다시 보낸다


def test_schema_failure_twice_raises_ai_output_invalid():
    fake = FakeLLM(['{"value": "x"}', '{"other": 1}', '{"value": 9}'])
    with pytest.raises(InterviewError) as exc:
        call(fake)
    assert exc.value.code == AI_OUTPUT_INVALID and exc.value.retryable is True
    assert len(fake.calls) == 2  # 세 번째는 보내지 않는다


def test_service_exception_not_retried():
    fake = FakeLLM([TimeoutError("throttled"), '{"value": 1}'])
    with pytest.raises(InterviewError) as exc:
        call(fake)
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is True
    assert exc.value.__cause__ is None
    assert len(fake.calls) == 1


def test_truncated_output_retried_once_then_success():
    fake = FakeLLM([llm.OutputTruncated(), '{"value": 5}'])
    assert call(fake).value == 5
    assert len(fake.calls) == 2


def test_truncated_output_twice_raises_ai_output_invalid():
    fake = FakeLLM([llm.OutputTruncated(), llm.OutputTruncated(), '{"value": 5}'])
    with pytest.raises(InterviewError) as exc:
        call(fake)
    assert exc.value.code == AI_OUTPUT_INVALID and exc.value.retryable is True
    assert len(fake.calls) == 2


def test_interview_error_passes_through():
    original = InterviewError(INVALID_INPUT, "msg")
    with pytest.raises(InterviewError) as exc:
        call(FakeLLM([original]))
    assert exc.value is original


def test_logs_have_no_prompt_or_output(caplog):
    secret_out = "비밀출력" * 5
    fake = FakeLLM([secret_out, json.dumps({"value": 1, "note": secret_out})])
    with caplog.at_level(logging.INFO, logger="interview"):
        llm.call_json(fake, system_prompt="비밀시스템", user_prompt="비밀사용자", schema=Out, stage="test")
    assert "stage=test" in caplog.text and "AI_OUTPUT_INVALID" in caplog.text
    for secret in ("비밀출력", "비밀시스템", "비밀사용자"):
        assert secret not in caplog.text


# ---------------------------------------------------------------- StrandsLLMClient (가짜 strands 모듈)


@pytest.fixture
def reset_model():
    llm._reset_model()
    yield
    llm._reset_model()


@pytest.fixture
def fake_strands(monkeypatch):
    record = {"models": [], "agents": [], "prompts": []}

    class BedrockModel:
        def __init__(self, **kwargs):
            record["models"].append(kwargs)

    class Agent:
        def __init__(self, **kwargs):
            record["agents"].append(kwargs)

        def __call__(self, prompt):
            record["prompts"].append(prompt)
            return "  {\"value\": 3}\n"

    strands = types.ModuleType("strands")
    strands.Agent = Agent
    models = types.ModuleType("strands.models")
    models.BedrockModel = BedrockModel
    strands.models = models
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.models", models)
    return record


def test_strands_client_builds_model_once_and_agent_per_call(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("INTERVIEW_MAX_TOKENS", "512")
    client = llm.StrandsLLMClient()
    assert client.complete(system_prompt="S1", user_prompt="U1").strip() == '{"value": 3}'
    client.complete(system_prompt="S2", user_prompt="U2")
    assert fake_strands["models"] == [{"model_id": "test-model", "region_name": "ap-northeast-2", "max_tokens": 512}]
    assert len(fake_strands["agents"]) == 2
    for kwargs, system in zip(fake_strands["agents"], ["S1", "S2"]):
        assert kwargs["system_prompt"] == system
        assert kwargs["tools"] == []
        assert kwargs["callback_handler"] is None
    assert fake_strands["prompts"] == ["U1", "U2"]


def test_strands_client_through_call_json(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    assert llm.call_json(llm.default_client(), system_prompt="S", user_prompt="U", schema=Out, stage="t").value == 3


class MaxTokensReachedException(Exception):
    """strands-agents 예외와 같은 이름의 가짜. 이름으로 구분하는지 본다."""


def _agent_raising(monkeypatch, fake_strands, errors):
    # errors를 순서대로 던지고, 다 쓰면 정상 JSON을 준다
    remaining = list(errors)

    def __call__(self, prompt):
        fake_strands["prompts"].append(prompt)
        if remaining:
            raise remaining.pop(0)
        return '{"value": 4}'

    monkeypatch.setattr(sys.modules["strands"].Agent, "__call__", __call__)


def test_strands_max_tokens_becomes_output_truncated(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    _agent_raising(monkeypatch, fake_strands, [MaxTokensReachedException("max tokens")])
    with pytest.raises(llm.OutputTruncated):
        llm.StrandsLLMClient().complete(system_prompt="S", user_prompt="U")


def test_strands_max_tokens_retried_then_ai_output_invalid(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    _agent_raising(monkeypatch, fake_strands, [MaxTokensReachedException("a"), MaxTokensReachedException("b")])
    with pytest.raises(InterviewError) as exc:
        llm.call_json(llm.default_client(), system_prompt="S", user_prompt="U", schema=Out, stage="t")
    assert exc.value.code == AI_OUTPUT_INVALID and exc.value.retryable is True
    assert fake_strands["prompts"] == ["U", "U"]


def test_strands_max_tokens_once_then_success(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    _agent_raising(monkeypatch, fake_strands, [MaxTokensReachedException("a")])
    result = llm.call_json(llm.default_client(), system_prompt="S", user_prompt="U", schema=Out, stage="t")
    assert result.value == 4 and len(fake_strands["prompts"]) == 2


def test_strands_other_errors_stay_aws_service_error(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")
    _agent_raising(monkeypatch, fake_strands, [RuntimeError("throttled")])
    with pytest.raises(InterviewError) as exc:
        llm.call_json(llm.default_client(), system_prompt="S", user_prompt="U", schema=Out, stage="t")
    assert exc.value.code == AWS_SERVICE_ERROR
    assert len(fake_strands["prompts"]) == 1


def test_strands_client_without_model_id(monkeypatch, reset_model, fake_strands):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(InterviewError) as exc:
        llm.StrandsLLMClient().complete(system_prompt="S", user_prompt="U")
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False
    assert fake_strands["models"] == []


def test_strands_missing_package(monkeypatch, reset_model):
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setitem(sys.modules, "strands", None)
    monkeypatch.setitem(sys.modules, "strands.models", None)
    with pytest.raises(InterviewError) as exc:
        llm.StrandsLLMClient().complete(system_prompt="S", user_prompt="U")
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False
