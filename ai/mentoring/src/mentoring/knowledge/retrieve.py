"""Bedrock Knowledge Base retrieval with source and manifest validation."""
from __future__ import annotations

import html
import json
import logging
from collections.abc import Iterable
from typing import Any

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from mentoring.config import require_env
from mentoring.errors import aws_service_error, invalid_input

from .models import KnowledgeConfig, KnowledgeHit, load_knowledge_config

logger = logging.getLogger("mentoring.knowledge")


class KnowledgeRetriever:
    """Retrieve only from the shared public KB; personal resumes must never be indexed here."""

    def __init__(
        self,
        client: Any,
        kb_id: str,
        config: KnowledgeConfig,
        *,
        allowed_document_ids: Iterable[str] | None = None,
    ) -> None:
        self._client = client
        self._kb_id = kb_id
        configured = config.allowed_document_ids if allowed_document_ids is None else allowed_document_ids
        self._allowed_document_ids = set(configured) if configured is not None else None
        self._config = config

    @classmethod
    def from_environment(
        cls,
        *,
        config: KnowledgeConfig | None = None,
        allowed_document_ids: Iterable[str] | None = None,
    ) -> "KnowledgeRetriever":
        values = config or load_knowledge_config()
        kb_id = require_env("KB_ID")
        region = require_env("AWS_REGION")
        import boto3

        client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=Config(
                connect_timeout=5,
                read_timeout=values.read_timeout_seconds,
                retries={"mode": "standard", "max_attempts": 2},
            ),
        )
        return cls(client, kb_id, values, allowed_document_ids=allowed_document_ids)

    def _request(self, query: str, job_role: str | None, k: int) -> dict:
        vector: dict[str, Any] = {"numberOfResults": k}
        if job_role:
            vector["filter"] = {
                "orAll": [
                    {"equals": {"key": "job_role", "value": job_role}},
                    {"equals": {"key": "job_role", "value": "공통"}},
                ]
            }
        return {
            "knowledgeBaseId": self._kb_id,
            "retrievalQuery": {"text": query},
            "retrievalConfiguration": {"vectorSearchConfiguration": vector},
        }

    def retrieve(
        self,
        query: str,
        *,
        job_role: str | None = None,
        k: int | None = None,
    ) -> list[KnowledgeHit]:
        normalized = query.strip() if isinstance(query, str) else ""
        if not self._config.query_min_chars <= len(normalized) <= self._config.query_max_chars:
            raise invalid_input(
                "검색어 길이를 확인해 주세요.",
                minChars=self._config.query_min_chars,
                maxChars=self._config.query_max_chars,
            )
        count = self._config.default_k if k is None else k
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= self._config.max_k:
            raise invalid_input("검색 결과 수를 확인해 주세요.", maxK=self._config.max_k)

        try:
            response = self._client.retrieve(**self._request(normalized, job_role, count))
        except (ClientError, BotoCoreError, TimeoutError) as error:
            raise aws_service_error("bedrock-kb") from error

        hits = []
        for result in response.get("retrievalResults", []):
            metadata = result.get("metadata") or {}
            document_id = metadata.get("document_id")
            source_url = metadata.get("source_url")
            collected_at = metadata.get("collected_at")
            if not document_id or not source_url or not collected_at:
                continue
            if self._allowed_document_ids is not None and document_id not in self._allowed_document_ids:
                continue
            content = result.get("content") or {}
            hits.append(
                KnowledgeHit(
                    document_id=str(document_id),
                    job_role=str(metadata["job_role"]) if metadata.get("job_role") else None,
                    job_family=str(metadata["job_family"]) if metadata.get("job_family") else None,
                    document_type=str(metadata["document_type"]) if metadata.get("document_type") else None,
                    source_url=str(source_url),
                    collected_at=str(collected_at),
                    verification_status=(
                        str(metadata["verification_status"])
                        if metadata.get("verification_status")
                        else None
                    ),
                    score=float(result["score"]) if result.get("score") is not None else None,
                    text=str(content.get("text", "")),
                )
            )
        logger.info(json.dumps({"event": "kb.retrieve", "queryLength": len(normalized), "resultCount": len(hits)}))
        return hits


def format_for_prompt(hits: list[KnowledgeHit]) -> str:
    """Wrap hits as untrusted ``<knowledge>`` data before passing them to an LLM.

    The shared KB contains no personal documents. Closing-tag imitations inside
    retrieved text are escaped and cannot end the data boundary.
    """
    blocks = []
    for hit in hits:
        attributes = {
            "document_id": hit.document_id,
            "source_url": hit.source_url,
            "collected_at": hit.collected_at,
        }
        rendered = " ".join(f'{key}="{html.escape(value, quote=True)}"' for key, value in attributes.items())
        blocks.append(f"<knowledge {rendered}>{html.escape(hit.text, quote=False)}</knowledge>")
    return "\n".join(blocks)
