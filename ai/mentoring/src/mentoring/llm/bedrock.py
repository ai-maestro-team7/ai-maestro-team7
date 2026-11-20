"""Bedrock Converse implementation of the mentoring LLM port."""
from typing import Any


class BedrockLlm:
    def __init__(self, client: Any, model_id: str) -> None:
        self._client = client
        self.model_id = model_id

    def request(self, system: str, user: str, *, max_tokens: int) -> dict:
        return {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": max_tokens},
        }

    def invoke(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        response = self._client.converse(**self.request(system, user, max_tokens=max_tokens))
        content = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(part.get("text", "") for part in content)
