"""Bedrock Knowledge Base 검색 (`team07-opp-policy-kb`, S3 Vectors). Retrieve만 쓴다.

답은 우리 코드가 만든다 (`enrich/ask.py`). RetrieveAndGenerate는 쓰지 않는다.
문서 1건이 조각 1개라서 결과 한 줄이 정책 하나다. 메타데이터의 policyId를 doc_id로 쓴다.
"""

from ..ports import RetrievedDoc
from .dynamo import aws_errors

SERVICE = "bedrock-kb"
MAX_RESULTS = 100  # Retrieve의 numberOfResults 상한


class BedrockKbRetriever:
    def __init__(self, client=None, *, knowledge_base_id: str):
        if client is None:
            import boto3
            client = boto3.client("bedrock-agent-runtime")
        self.client = client
        self.knowledge_base_id = knowledge_base_id

    def retrieve(self, query: str, *, top_k: int, filter: dict | None = None) -> list[RetrievedDoc]:
        search: dict = {"numberOfResults": max(1, min(top_k, MAX_RESULTS))}
        if filter is not None:
            search["filter"] = filter
        with aws_errors(SERVICE):
            response = self.client.retrieve(knowledgeBaseId=self.knowledge_base_id, retrievalQuery={"text": query},
                                            retrievalConfiguration={"vectorSearchConfiguration": search})
        docs = []
        for row in response.get("retrievalResults", []):
            metadata = dict(row.get("metadata") or {})
            policy_id = metadata.get("policyId")
            if not policy_id:  # 우리 문서가 아니면 버린다
                continue
            location = (row.get("location") or {}).get("s3Location") or {}
            docs.append(RetrievedDoc(doc_id=str(policy_id), text=(row.get("content") or {}).get("text") or "",
                                     score=float(row.get("score") or 0.0), metadata=metadata,
                                     source_uri=location.get("uri")))
        return docs
