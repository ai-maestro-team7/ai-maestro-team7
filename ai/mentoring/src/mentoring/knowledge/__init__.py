"""Validated retrieval from the shared, non-personal mentoring Knowledge Base."""

from .models import KnowledgeConfig, KnowledgeHit, load_knowledge_config
from .retrieve import KnowledgeRetriever, format_for_prompt

__all__ = ["KnowledgeConfig", "KnowledgeHit", "KnowledgeRetriever", "format_for_prompt", "load_knowledge_config"]
