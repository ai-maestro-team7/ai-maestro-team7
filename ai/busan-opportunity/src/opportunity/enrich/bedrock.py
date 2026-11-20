"""Bedrock 구현. `ports.Llm`, `ports.Embedder`를 채운다.

모델 ID는 환경변수 `MODEL_ID`, `EMBEDDING_MODEL_ID`에서만 읽는다. boto3 클라이언트는 생성자에서 한 번 만든다.
테스트는 client를 주입해 요청 본문만 확인한다. 실제로 부르지 않는다.
"""

import json

from botocore.exceptions import ClientError

from ..config import OpportunityConfig, get_config, require_env

INPUT_TYPES = {"document": "search_document", "query": "search_query"}


def _client(client, config: OpportunityConfig):
    if client is not None:
        return client
    import boto3  # Lambda 런타임에 있다. 테스트는 client를 넣으므로 여기까지 오지 않는다

    return boto3.client("bedrock-runtime", region_name=config.region)


class BedrockLlm:
    """Converse API. temperature는 보내지 않는다: 서울 리전의 Claude 5.5는 이 값을 받지 않는다
    (`temperature` is deprecated for this model, 2026-11-20 확인). 답의 흔들림은 코드 검증으로 막는다."""

    def __init__(self, client=None, *, config: OpportunityConfig | None = None, model_id: str | None = None):
        self.config = config or get_config()
        self.model_id = model_id or require_env("MODEL_ID")
        self.client = _client(client, self.config)
        self._thinking_off = True

    # 생각 과정(reasoning)을 끈다. 켜 두면 생각에 maxTokens를 다 써서 답 없이 끝나는 일이 생긴다
    # (stopReason=max_tokens, 답 글 없음. 2026-11-20 배포본에서 확인). 우리 호출은 짧은 추출·설명이라 필요 없다.
    NO_THINKING = {"thinking": {"type": "disabled"}}

    def request(self, system: str, user: str, *, max_tokens: int, thinking_off: bool = True) -> dict:
        request = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if thinking_off:
            request["additionalModelRequestFields"] = dict(self.NO_THINKING)
        return request

    def invoke(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        try:
            response = self.client.converse(**self.request(system, user, max_tokens=max_tokens,
                                                           thinking_off=self._thinking_off))
        except ClientError as e:
            # 이 설정을 받지 않는 모델이면 한 번만 설정 없이 다시 부르고, 그 뒤로는 넣지 않는다
            if not (self._thinking_off and e.response.get("Error", {}).get("Code") == "ValidationException"):
                raise
            self._thinking_off = False
            response = self.client.converse(**self.request(system, user, max_tokens=max_tokens, thinking_off=False))
        content = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(part.get("text", "") for part in content)


class BedrockEmbedder:
    """Cohere Embed v4 (`cohere.embed-v4:0`). 차원은 설정 `models.embedDim`을 따른다."""

    def __init__(self, client=None, *, config: OpportunityConfig | None = None, model_id: str | None = None):
        self.config = config or get_config()
        self.model_id = model_id or require_env("EMBEDDING_MODEL_ID")
        self.client = _client(client, self.config)

    def body(self, text: str, kind: str) -> dict:
        if kind not in INPUT_TYPES:
            raise ValueError(f"kind는 document 또는 query여야 한다: {kind}")
        return {
            "texts": [text],
            "input_type": INPUT_TYPES[kind],
            "embedding_types": ["float"],
            "output_dimension": self.config.models.embed_dim,
        }

    def embed(self, text: str, *, kind: str = "document") -> list[float]:
        response = self.client.invoke_model(modelId=self.model_id, body=json.dumps(self.body(text, kind)),
                                            contentType="application/json", accept="application/json")
        raw = response["body"]
        payload = json.loads(raw.read() if hasattr(raw, "read") else raw)
        embeddings = payload["embeddings"]
        vector = embeddings["float"][0] if isinstance(embeddings, dict) else embeddings[0]
        if len(vector) != self.config.models.embed_dim:
            raise ValueError(f"임베딩 차원이 설정과 다르다: {len(vector)}")
        return [float(x) for x in vector]
