"""Bedrock 구현. `ports.Llm`, `ports.Embedder`를 채운다.

모델 ID는 환경변수 `MODEL_ID`, `EMBEDDING_MODEL_ID`에서만 읽는다. boto3 클라이언트는 생성자에서 한 번 만든다.
테스트는 client를 주입해 요청 본문만 확인한다. 실제로 부르지 않는다.
"""

import json

from ..config import OpportunityConfig, get_config, require_env

INPUT_TYPES = {"document": "search_document", "query": "search_query"}


def _client(client, config: OpportunityConfig):
    if client is not None:
        return client
    import boto3  # Lambda 런타임에 있다. 테스트는 client를 넣으므로 여기까지 오지 않는다

    return boto3.client("bedrock-runtime", region_name=config.region)


class BedrockLlm:
    """Converse API. temperature 0으로 같은 입력에 같은 답이 나오게 한다."""

    def __init__(self, client=None, *, config: OpportunityConfig | None = None, model_id: str | None = None):
        self.config = config or get_config()
        self.model_id = model_id or require_env("MODEL_ID")
        self.client = _client(client, self.config)

    def request(self, system: str, user: str, *, max_tokens: int) -> dict:
        return {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
        }

    def invoke(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        response = self.client.converse(**self.request(system, user, max_tokens=max_tokens))
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
