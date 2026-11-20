"""S3 Vectors 구현. 버킷 `OPP_VECTOR_BUCKET`, 인덱스 `OPP_VECTOR_INDEX` (`team07-opp-vectors`/`postings-v1`).

필터 메타데이터: isBusan, sido, jobMajor, active, deadline(YYYYMMDD 숫자). `title`은 필터 불가 메타데이터다.
거리는 코사인 distance라서 similarity = 1 - distance로 바꾼다.
"""

from collections.abc import Sequence

from ..config import require_env
from ..ports import VectorHit
from .dynamo import aws_errors

SERVICE = "s3vectors"
MAX_TOP_K = 100  # S3 Vectors가 질의 한 번에 돌려주는 최대 개수


class S3VectorIndex:
    def __init__(self, client=None, bucket: str | None = None, index: str | None = None):
        if client is None:
            import boto3
            client = boto3.client(SERVICE)
        self.client = client
        self.bucket = bucket or require_env("OPP_VECTOR_BUCKET")
        self.index = index or require_env("OPP_VECTOR_INDEX")

    def _target(self) -> dict:
        return {"vectorBucketName": self.bucket, "indexName": self.index}

    def query(self, vector: Sequence[float], *, top_k: int, filter: dict | None = None) -> list[VectorHit]:
        params: dict = {**self._target(), "queryVector": {"float32": [float(x) for x in vector]},
                        "topK": min(top_k, MAX_TOP_K), "returnMetadata": True, "returnDistance": True}
        if filter:
            params["filter"] = filter
        with aws_errors(SERVICE):
            response = self.client.query_vectors(**params)
        hits = [VectorHit(row["key"], _similarity(row.get("distance")), dict(row.get("metadata") or {}))
                for row in response.get("vectors", [])]
        return sorted(hits, key=lambda h: (-h.similarity, h.key))

    def put(self, key: str, vector: Sequence[float], metadata: dict) -> None:
        row = {"key": key, "data": {"float32": [float(x) for x in vector]},
               "metadata": {k: v for k, v in metadata.items() if v is not None}}
        with aws_errors(SERVICE):
            self.client.put_vectors(**self._target(), vectors=[row])

    def get(self, key: str) -> list[float] | None:
        with aws_errors(SERVICE):
            response = self.client.get_vectors(**self._target(), keys=[key], returnData=True)
        rows = response.get("vectors", [])
        return [float(x) for x in rows[0]["data"]["float32"]] if rows else None

    def delete(self, key: str) -> None:
        with aws_errors(SERVICE):
            self.client.delete_vectors(**self._target(), keys=[key])


def _similarity(distance: float | None) -> float:
    """코사인 distance(0~2)를 유사도 0~1로 바꾼다. distance가 없으면 0."""
    if distance is None:
        return 0.0
    return min(1.0, max(0.0, 1.0 - float(distance)))
