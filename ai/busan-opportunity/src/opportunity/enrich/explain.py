"""공고 설명 문장 (GET /postings/{id}/explanation).

담당 워크트리: enrich. 명세: 개발계획서2 §4.2 B-04, §4.7. 테스트: T-19.
"""

import hashlib
import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, ValidationError

from ..core import clock, copy_rules, posting_detail
from ..core.context import load_context
from ..deps import Deps
from ..models.api import ExplanationResponse
from ..models.errors import ai_output_invalid, aws_service_error
from ..models.user_state import ExplanationCache
from . import prompts

# 금지 문구나 사실에 없는 숫자가 나오면 한 번만 다시 만든다. 처음 + 다시 = 2
MAX_ATTEMPTS = 2


class ExplainOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sentences: list[str]


def facts_hash(facts: list[str]) -> str:
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def check_sentences(sentences: list[str], facts: list[str], expected: int) -> list[str]:
    """문제 목록. 비어 있으면 통과다: 문장 수, 사실에 없는 숫자, 금지 문구."""
    problems: list[str] = []
    if len(sentences) != expected or any(not s.strip() for s in sentences):
        problems.append("SENTENCE_COUNT")
    allowed = set().union(*(copy_rules.numbers_in(f) for f in facts)) if facts else set()
    for sentence in sentences:
        if copy_rules.numbers_in(sentence) - allowed:
            problems.append("NUMBER_NOT_IN_FACTS")
        if copy_rules.find_forbidden(sentence):
            problems.append("FORBIDDEN_COPY")
    return problems


def _parse(reply: str) -> list[str] | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return [s.strip() for s in ExplainOutput.model_validate(json.loads(reply[start:end + 1])).sentences]
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def _cached(deps: Deps, user_id: str, job_posting_id: str, digest: str, as_of: datetime) -> list[str] | None:
    cache = deps.users.get_explanation(user_id, job_posting_id)
    if cache is None or cache.facts_hash != digest:
        return None
    if clock.hours_between(cache.created_at, as_of) >= deps.config.explanation.cache_hours:
        return None
    return cache.sentences


def explain_posting(deps: Deps, user_id: str, job_posting_id: str, *,
                    as_of: str | date | datetime | None = None) -> ExplanationResponse:
    """사실 목록으로 설명 문장을 만든다 (explanation.sentences개). `OPP#EXPL#`에 cacheHours 동안 캐시한다.

    문장의 숫자는 사실 목록에 있는 것만 쓰고, 금지 문구가 있으면 다시 만든다 (T-19).
    한 번 다시 시도해도 실패하면 AI_OUTPUT_INVALID.
    사실 목록은 공고 상세(`core.posting_detail.get_posting`)의 facts를 쓴다. 피드 카드와 같은 사실이다.
    캐시는 사실 목록 해시가 같을 때만 쓴다. LLM이 없으면 AWS_SERVICE_ERROR.
    """
    ctx = load_context(deps, user_id, as_of)
    facts = list(posting_detail.get_posting(deps, user_id, job_posting_id, as_of=ctx.as_of).facts)
    digest = facts_hash(facts)
    hit = _cached(deps, user_id, job_posting_id, digest, ctx.as_of)
    if hit is not None:
        return ExplanationResponse(job_posting_id=job_posting_id, sentences=hit, facts=facts, cached=True)
    if deps.llm is None:
        raise aws_service_error("bedrock")

    expected = deps.config.explanation.sentences
    system, user = prompts.explain_system(expected), prompts.explain_user(facts)
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = deps.llm.invoke(system, user)
        except Exception as e:
            raise aws_service_error("bedrock") from e
        sentences = _parse(reply)
        if sentences is None or check_sentences(sentences, facts, expected):
            continue
        cache = ExplanationCache(job_posting_id=job_posting_id, sentences=sentences, facts_hash=digest,
                                 created_at=clock.iso(ctx.as_of))
        deps.users.put_explanation(user_id, cache, deps.config.explanation.cache_hours)
        return ExplanationResponse(job_posting_id=job_posting_id, sentences=sentences, facts=facts, cached=False)
    raise ai_output_invalid()
