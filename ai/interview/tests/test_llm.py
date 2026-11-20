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


@pytest.fixture
def isolated_aws_env(monkeypatch, tmp_path):
    """실제 AWS 설정·로그인과 분리한다. botocore가 ~/.aws와 aws login 캐시를 읽지 않게 한다.

    가짜 키는 실제 자격 증명이 아니다. 이 테스트는 요청을 만들기만 하고 보내지 않는다.
    """
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_CA_BUNDLE", "AWS_ROLE_ARN",
                 "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                 "AWS_CONTAINER_CREDENTIALS_FULL_URI"):
        monkeypatch.delenv(name, raising=False)
    config_file = tmp_path / "config"
    credentials_file = tmp_path / "credentials"
    config_file.write_text("", encoding="utf-8")
    credentials_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials_file))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.mark.parametrize("env_value, expected", [(None, 1024), ("2048", 2048)])
def test_real_bedrock_model_sends_max_tokens(monkeypatch, reset_model, isolated_aws_env, env_value, expected):
    # 설치된 strands-agents로 요청을 만들어 inferenceConfig.maxTokens에 설정 값이 들어가는지 본다.
    # 매개변수 이름이 바뀌면 strands가 키를 거절하거나 모델 기본값을 보내므로 여기서 잡힌다. 네트워크는 쓰지 않는다.
    pytest.importorskip("strands.models")
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    if env_value is None:
        monkeypatch.delenv("INTERVIEW_MAX_TOKENS", raising=False)
    else:
        monkeypatch.setenv("INTERVIEW_MAX_TOKENS", env_value)
    model = llm._get_model()
    assert model.get_config()["max_tokens"] == expected
    request = model.format_request([{"role": "user", "content": [{"text": "hi"}]}])
    assert request["inferenceConfig"]["maxTokens"] == expected


@pytest.mark.parametrize("model_id, thinking", [
    ("global.anthropic.claude-haiku-5-5", {"type": "disabled"}),
    ("global.anthropic.claude-sonnet-5-5", {"type": "between_tools"}),
])
def test_real_bedrock_model_sends_thinking_off(monkeypatch, reset_model, isolated_aws_env, model_id, thinking):
    # 생각 토큰이 max_tokens를 다 써서 JSON이 잘리던 문제 (#58). 설치된 strands로 만든 요청에 끄는 값이 들어가는지 본다
    pytest.importorskip("strands.models")
    monkeypatch.setenv("MODEL_ID", model_id)
    request = llm._get_model().format_request([{"role": "user", "content": [{"text": "hi"}]}])
    assert request["additionalModelRequestFields"] == {"thinking": thinking}
    assert "output_config" not in request["additionalModelRequestFields"]  # effort는 모델 기본값(high 이하)


def test_real_bedrock_model_unknown_model_sends_no_thinking(monkeypatch, reset_model, isolated_aws_env):
    pytest.importorskip("strands.models")
    monkeypatch.setenv("MODEL_ID", "test-model")
    request = llm._get_model().format_request([{"role": "user", "content": [{"text": "hi"}]}])
    assert "additionalModelRequestFields" not in request


def test_strands_client_passes_thinking_off_to_model(monkeypatch, reset_model, fake_strands):
    monkeypatch.setenv("MODEL_ID", "global.anthropic.claude-haiku-5-5")
    monkeypatch.delenv("INTERVIEW_MAX_TOKENS", raising=False)
    llm.StrandsLLMClient().complete(system_prompt="S", user_prompt="U")
    assert fake_strands["models"][0]["additional_request_fields"] == {"thinking": {"type": "disabled"}}
    assert fake_strands["models"][0]["max_tokens"] == 1024


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


# ---------------------------------------------------------------- 툴 사용 에이전트 (피드백 C-2)


@pytest.fixture
def fake_tool_strands(monkeypatch):
    record = {"models": [], "agents": [], "calls": [], "wrapped": []}

    class BedrockModel:
        def __init__(self, **kwargs):
            record["models"].append(kwargs)

    class Result:
        stop_reason = "end_turn"

        def __str__(self):
            return '{"value": 5}'

    class Agent:
        def __init__(self, **kwargs):
            record["agents"].append(kwargs)

        def __call__(self, prompt, **kwargs):
            record["calls"].append({"prompt": prompt, **kwargs})
            return Result()

    def tool(fn):
        record["wrapped"].append(fn.__name__)
        return ("wrapped", fn)

    strands = types.ModuleType("strands")
    strands.Agent, strands.tool = Agent, tool
    models = types.ModuleType("strands.models")
    models.BedrockModel = BedrockModel
    strands.models = models
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.models", models)
    return record


def _a_tool(question_id: str) -> dict:
    """테스트용 툴."""
    return {"questionId": question_id}


def test_run_with_tools_passes_tools_limits_and_feedback_max_tokens(monkeypatch, reset_model, fake_tool_strands):
    monkeypatch.setenv("MODEL_ID", "global.anthropic.claude-haiku-5-5")
    monkeypatch.delenv("INTERVIEW_MAX_TOKENS", raising=False)
    monkeypatch.delenv("INTERVIEW_FEEDBACK_MAX_TOKENS", raising=False)
    client = llm.StrandsLLMClient()
    out = client.run_with_tools(system_prompt="S", user_prompt="U", tools=[_a_tool], limits={"turns": 6})
    assert out == '{"value": 5}'
    assert fake_tool_strands["wrapped"] == ["_a_tool"]
    agent = fake_tool_strands["agents"][0]
    assert agent["tools"] == [("wrapped", _a_tool)] and agent["callback_handler"] is None
    assert fake_tool_strands["calls"] == [{"prompt": "U", "limits": {"turns": 6}}]
    # 피드백은 2048, 다른 호출은 1024로 모델을 따로 만든다. 생각 끄기는 둘 다
    client.complete(system_prompt="S", user_prompt="U")
    assert [m["max_tokens"] for m in fake_tool_strands["models"]] == [2048, 1024]
    assert all(m["additional_request_fields"] == {"thinking": {"type": "disabled"}} for m in fake_tool_strands["models"])


def test_run_with_tools_max_tokens_becomes_output_truncated(monkeypatch, reset_model, fake_tool_strands):
    monkeypatch.setenv("MODEL_ID", "test-model")

    def boom(self, prompt, **kwargs):
        raise MaxTokensReachedException("max")

    monkeypatch.setattr(sys.modules["strands"].Agent, "__call__", boom)
    with pytest.raises(llm.OutputTruncated):
        llm.StrandsLLMClient().run_with_tools(system_prompt="S", user_prompt="U", tools=[], limits={})


def test_call_json_with_tools_retry_and_check():
    class FakeTools:
        def __init__(self, outputs):
            self.outputs, self.seen = list(outputs), []

        def run_with_tools(self, **kwargs):
            self.seen.append(kwargs)
            return self.outputs.pop(0)

    def check(parsed):
        if parsed.value != 2:
            raise ValueError("not 2")

    fake = FakeTools(['{"value": 1}', '{"value": 2}'])
    out = llm.call_json_with_tools(fake, system_prompt="S", user_prompt="U", tools=[_a_tool], limits={"turns": 1},
                                   schema=Out, stage="t", check=check)
    assert out.value == 2 and len(fake.seen) == 2
    assert fake.seen[0]["tools"] == [_a_tool] and fake.seen[0]["limits"] == {"turns": 1}
    with pytest.raises(InterviewError) as exc:
        llm.call_json_with_tools(FakeTools(['{"value": 1}', '{"value": 1}']), system_prompt="S", user_prompt="U",
                                 tools=[], limits={}, schema=Out, stage="t", check=check)
    assert exc.value.code == AI_OUTPUT_INVALID


def test_real_strands_tool_wraps_feedback_tools():
    # 설치된 strands가 우리 툴(타입 힌트 + docstring)을 툴로 감쌀 수 있는지. 네트워크 없음
    strands = pytest.importorskip("strands")
    from interview import feedback

    usage = feedback.ToolUsage(12)

    class _Ctx:  # 툴 정의만 확인하므로 데이터는 쓰지 않는다
        question_ids = ["q1"]
        resume_text = ""

        def bundle(self, question_id):
            return None

    names = []
    for fn in feedback.make_feedback_tools(_Ctx(), usage):
        wrapped = strands.tool(fn)
        spec = wrapped.tool_spec
        names.append(spec["name"])
        assert spec["description"] and "question_id" in json.dumps(spec["inputSchema"]) or spec["name"] == "find_resume_passages"
    assert sorted(names) == ["find_resume_passages", "get_answer_text", "get_confirmed_scores", "get_delivery_metrics"]


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
