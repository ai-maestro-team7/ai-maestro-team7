"""MockLLM: 정해 둔 응답을 차례로 돌려준다 (개발계획서1 §10.3).
응답은 문자열, dict(JSON으로 바꿈), 또는 (system, user)를 받아 문자열을 돌려주는 함수다.
마지막 응답을 다 쓰면 마지막 것을 계속 돌려준다. 받은 요청은 `calls`에 남긴다 (테스트에서 프롬프트 확인용).
"""
import json
from collections.abc import Callable


class MockLlm:
    def __init__(self, responses: list[str | dict | Callable[[str, str], str]], *, model_id: str = "mock-llm"):
        if not responses:
            raise ValueError("응답이 하나 이상 필요하다")
        self.responses = list(responses)
        self.model_id = model_id
        self.calls: list[dict] = []

    def invoke(self, system: str, user: str, *, max_tokens: int) -> str:
        self.calls.append({"system": system, "user": user, "maxTokens": max_tokens})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        response = self.responses[index]
        if callable(response):
            return response(system, user)
        if isinstance(response, dict):
            return json.dumps(response, ensure_ascii=False)
        return response
