import boto3
from botocore.stub import Stubber

from mentoring.llm.bedrock import BedrockLlm


def test_bedrock_converse_request(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    client = boto3.client("bedrock-runtime", region_name="ap-northeast-2")
    expected = {
        "modelId": "global.test-model",
        "system": [{"text": "system"}],
        "messages": [{"role": "user", "content": [{"text": "user"}]}],
        "inferenceConfig": {"maxTokens": 200},
    }
    response = {
        "output": {"message": {"role": "assistant", "content": [{"text": "첫째"}, {"text": "둘째"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
        "metrics": {"latencyMs": 1},
    }
    with Stubber(client) as stubber:
        stubber.add_response("converse", response, expected)
        assert BedrockLlm(client, "global.test-model").invoke("system", "user", max_tokens=200) == "첫째둘째"
