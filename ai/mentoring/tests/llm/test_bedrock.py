import boto3
import pytest
from botocore.stub import Stubber

from mentoring.llm.bedrock import THINKING_OFF, BedrockLlm

RESPONSE = {
    "output": {"message": {"role": "assistant", "content": [{"text": "첫째"}, {"text": "둘째"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
    "metrics": {"latencyMs": 1},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    return boto3.client("bedrock-runtime", region_name="ap-northeast-2")


def request(with_thinking_off: bool) -> dict:
    req = {
        "modelId": "global.test-model",
        "system": [{"text": "system"}],
        "messages": [{"role": "user", "content": [{"text": "user"}]}],
        "inferenceConfig": {"maxTokens": 200},
    }
    if with_thinking_off:
        req["additionalModelRequestFields"] = THINKING_OFF
    return req


def test_bedrock_converse_request_turns_thinking_off(client):
    """생각 토큰이 maxTokens를 먹어 JSON이 잘리지 않게 생각을 끈다. temperature는 보내지 않는다."""
    with Stubber(client) as stubber:
        stubber.add_response("converse", RESPONSE, request(True))
        assert BedrockLlm(client, "global.test-model").invoke("system", "user", max_tokens=200) == "첫째둘째"


def test_model_that_rejects_thinking_off_is_called_again_without_it(client):
    llm = BedrockLlm(client, "global.test-model")
    with Stubber(client) as stubber:
        stubber.add_client_error("converse", service_error_code="ValidationException",
                                 service_message="thinking.type: disabled is not supported for this model",
                                 expected_params=request(True))
        stubber.add_response("converse", RESPONSE, request(False))
        stubber.add_response("converse", RESPONSE, request(False))  # 다음 호출부터는 보내지 않는다
        assert llm.invoke("system", "user", max_tokens=200) == "첫째둘째"
        assert llm.invoke("system", "user", max_tokens=200) == "첫째둘째"


def test_other_validation_errors_are_not_retried(client):
    with Stubber(client) as stubber:
        stubber.add_client_error("converse", service_error_code="ValidationException",
                                 service_message="messages: too long", expected_params=request(True))
        with pytest.raises(Exception):
            BedrockLlm(client, "global.test-model").invoke("system", "user", max_tokens=200)
