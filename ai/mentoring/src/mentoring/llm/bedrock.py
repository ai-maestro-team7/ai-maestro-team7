"""Bedrock Converse implementation of the mentoring LLM port.

Claude Haiku 5.5는 따로 말하지 않으면 답하기 전에 생각(adaptive thinking)을 하고, 그 토큰이 maxTokens에 같이 잡힌다.
JSON을 뽑는 작업에서는 생각이 길어지면 답이 중간에 잘려 형식 검사에서 떨어지므로(AI_OUTPUT_INVALID) 생각을 끈다.
생각을 끌 수 없는 모델(예: Sonnet 5.5, Opus 5.5)이면 한 번 거절당한 뒤 그 설정 없이 다시 부르고, 이후로는 보내지 않는다.
temperature 같은 표본 설정은 보내지 않는다 (Claude 5 계열은 기본값이 아니면 거부한다).
"""
from typing import Any

from botocore.exceptions import ClientError

THINKING_OFF = {"thinking": {"type": "disabled"}}


def _rejects_thinking(error: ClientError) -> bool:
    info = error.response.get("Error", {})
    return info.get("Code") == "ValidationException" and "thinking" in str(info.get("Message", "")).lower()


class BedrockLlm:
    def __init__(self, client: Any, model_id: str, *, thinking_off: bool = True) -> None:
        self._client = client
        self.model_id = model_id
        self._thinking_off = thinking_off

    def request(self, system: str, user: str, *, max_tokens: int) -> dict:
        req = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if self._thinking_off:
            req["additionalModelRequestFields"] = THINKING_OFF
        return req

    def invoke(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        try:
            response = self._client.converse(**self.request(system, user, max_tokens=max_tokens))
        except ClientError as error:
            if not (self._thinking_off and _rejects_thinking(error)):
                raise
            self._thinking_off = False
            response = self._client.converse(**self.request(system, user, max_tokens=max_tokens))
        content = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(part.get("text", "") for part in content)
