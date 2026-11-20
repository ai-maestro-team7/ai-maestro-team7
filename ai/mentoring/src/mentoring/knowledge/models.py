"""Knowledge Base configuration and validated retrieval results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from mentoring.models.base import MentoringModel


class KnowledgeConfig(MentoringModel):
    config_version: str
    query_min_chars: int = Field(ge=1)
    query_max_chars: int = Field(ge=1)
    default_k: int = Field(ge=1)
    max_k: int = Field(ge=1)
    read_timeout_seconds: int = Field(ge=1)
    allowed_document_ids: list[str] | None = None

    @model_validator(mode="after")
    def _ranges(self):
        if self.query_min_chars > self.query_max_chars:
            raise ValueError("queryMinChars must not exceed queryMaxChars")
        if self.default_k > self.max_k:
            raise ValueError("defaultK must not exceed maxK")
        return self


class KnowledgeHit(MentoringModel):
    document_id: str
    job_role: str | None = None
    job_family: str | None = None
    document_type: str | None = None
    source_url: str
    collected_at: str
    verification_status: str | None = None
    score: float | None = None
    text: str


def load_knowledge_config(
    *,
    path: Path | None = None,
    data: dict[str, Any] | None = None,
) -> KnowledgeConfig:
    if data is None:
        source = path or Path(__file__).with_name("knowledge_config.json")
        data = json.loads(source.read_text(encoding="utf-8"))
    return KnowledgeConfig.model_validate(data)
