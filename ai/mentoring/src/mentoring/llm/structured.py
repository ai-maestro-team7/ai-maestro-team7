"""고정 JSON 스키마로 모델을 부르는 도우미 (tech.md "LLM 출력은 고정 JSON 스키마로 받고 Pydantic으로 검사").
형식이 맞지 않으면 정해진 횟수만큼 다시 묻고, 그래도 안 되면 `AI_OUTPUT_INVALID`(재시도 가능)를 낸다. 조용히 통과시키지 않는다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from ..errors import MentoringError, ai_output_invalid, aws_service_error

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_json(raw, model: type[BaseModel]):
    if not isinstance(raw, str):
        return None
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return model.model_validate(json.loads(text[start:end + 1]))
    except (ValueError, ValidationError):
        return None


def invoke(deps, system: str, user: str, max_tokens: int) -> str:
    try:
        return deps.llm.invoke(system, user, max_tokens=max_tokens)
    except MentoringError:
        raise
    except Exception:  # noqa: BLE001 - Bedrock 오류 종류와 관계없이 다시 시도할 수 있는 오류로 남긴다
        raise aws_service_error("bedrock") from None


def call_structured(deps, system: str, build_user: Callable[[list[str] | None], str], model: type[BaseModel], *,
                    max_tokens: int, retries: int, on_schema_failure: Callable[[int], None] | None = None):
    """(결과, 호출 수). 형식 실패가 retries를 넘으면 AI_OUTPUT_INVALID."""
    problems = None
    calls = 0
    while True:
        calls += 1
        output = parse_json(invoke(deps, system, build_user(problems), max_tokens), model)
        if output is not None:
            return output, calls
        if on_schema_failure:
            on_schema_failure(calls)
        if calls > retries:
            raise ai_output_invalid()
        problems = ["출력이 정해진 JSON 형식과 맞지 않았다"]


def safe_tag(text: str, tag: str) -> str:
    """닫는 태그를 흉내 낸 글을 무력화한다 (외부 텍스트는 태그로 감싸 데이터로만)."""
    return text.replace(f"</{tag}>", f"</ {tag}>")
