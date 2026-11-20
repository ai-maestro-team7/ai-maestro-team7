"""Bedrock Knowledge Base 검색의 Recall@K를 사람이 수동 측정하는 도구."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RecallMiss(_Model):
    query_id: str
    expected: str
    got: list[str]


class RecallReport(_Model):
    hits: int = Field(ge=0)
    total: int = Field(ge=0)
    recall: float = Field(ge=0.0, le=1.0)
    empty: int = Field(ge=0)
    misses: list[RecallMiss]


def _document_id(result: dict[str, Any]) -> str | None:
    metadata = result.get("metadata") or {}
    for key in ("document_id", "documentId"):
        if metadata.get(key):
            return str(metadata[key])
    location = result.get("location") or {}
    uri = (location.get("s3Location") or {}).get("uri")
    if uri:
        return Path(str(uri)).name
    return None


def _filter(job_role: str) -> dict[str, Any]:
    return {
        "orAll": [
            {"equals": {"key": "job_role", "value": job_role}},
            {"equals": {"key": "job_role", "value": "공통"}},
        ]
    }


def recall_at_k(
    client: Any,
    kb_id: str,
    queries: list[dict[str, Any]],
    k: int,
    use_role_filter: bool,
) -> RecallReport:
    """검증 질문별 기대 문서가 상위 K 결과에 있는 비율을 계산한다."""

    if not kb_id:
        raise ValueError("kb_id가 필요합니다.")
    if k < 1:
        raise ValueError("k는 1 이상이어야 합니다.")

    hits = 0
    empty = 0
    misses: list[RecallMiss] = []
    for query in queries:
        query_id = str(query["query_id"])
        expected = str(query["expected_document_id"])
        vector: dict[str, Any] = {"numberOfResults": k}
        if use_role_filter:
            vector["filter"] = _filter(str(query["expected_job_role"]))
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": str(query["query"])},
            retrievalConfiguration={"vectorSearchConfiguration": vector},
        )
        results = response.get("retrievalResults", [])[:k]
        got = [identifier for result in results if (identifier := _document_id(result)) is not None]
        if not results:
            empty += 1
        if expected in got:
            hits += 1
        else:
            misses.append(RecallMiss(query_id=query_id, expected=expected, got=got))
    total = len(queries)
    return RecallReport(
        hits=hits,
        total=total,
        recall=hits / total if total else 0.0,
        empty=empty,
        misses=misses,
    )


def _load_queries(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Knowledge Base 검색 Recall@K를 수동 측정합니다.")
    parser.add_argument("--queries", required=True, help="validation/sample_queries.jsonl 경로")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--role-filter", action="store_true")
    args = parser.parse_args()

    kb_id = os.environ.get("KB_ID")
    region = os.environ.get("AWS_REGION")
    if not kb_id:
        parser.error("KB_ID 환경변수가 필요합니다.")
    if not region:
        parser.error("AWS_REGION 환경변수가 필요합니다.")

    import boto3

    client = boto3.client("bedrock-agent-runtime", region_name=region)
    report = recall_at_k(client, kb_id, _load_queries(args.queries), args.k, args.role_filter)
    print(report.model_dump_json(by_alias=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
