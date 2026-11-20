"""LLM 계층 (design §6).

- LLMClient 인터페이스 뒤에 Strands 호출을 둔다. 테스트는 가짜 클라이언트를 넘긴다.
- 출력은 고정 JSON으로 받아 Pydantic으로 검사하고, 실패하면 한 번만 다시 보낸다 (C §7).
- 로그에는 단계, 시도 횟수, 처리 시간, 오류 코드만 남긴다. 프롬프트와 모델 출력은 남기지 않는다.

strands-agents 1.65.0에서 확인한 것:
- Agent(callback_handler=...)의 기본값은 모델 출력을 표준 출력에 찍는 처리기다. None을 넘겨 끈다.
- str(AgentResult)는 텍스트 블록을 줄바꿈으로 이어 붙인다. extract_json이 앞뒤 공백을 지운다.
"""

import json
import logging
import re
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from . import settings
from .errors import AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, InterviewError

logger = logging.getLogger("interview")

MAX_ATTEMPTS = 2  # 처음 1번 + 재시도 1번 (C §7 "재시도 후 실패 시 AI_OUTPUT_INVALID")

AI_OUTPUT_MESSAGE = "AI 응답을 확인하지 못했어요. 다시 시도해 주세요."
SERVICE_MESSAGE = "AI 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요."

S = TypeVar("S", bound=BaseModel)


class OutputTruncated(Exception):
    """모델 출력이 max_tokens에서 잘렸다. 호출은 성공했으니 서비스 오류가 아니라 출력 문제로 본다."""


# strands-agents가 출력이 max_tokens에 닿았을 때 던지는 예외 이름.
# 클래스를 import하지 않고 이름으로 비교해 SDK 내부 모듈 경로에 묶이지 않게 한다.
_MAX_TOKENS_EXCEPTION_NAMES = frozenset({"MaxTokensReachedException"})


class LLMClient(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...


# ---------------------------------------------------------------- JSON 받기


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(raw: object) -> object:
    """모델 출력에서 JSON을 꺼낸다. 코드 블록이 있으면 안쪽을, 없으면 첫 { 부터 마지막 } 까지."""
    if not isinstance(raw, str):
        raise ValueError("not text")
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            raise ValueError("no json object")
        text = text[start:end + 1]
    return json.loads(text)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def call_json(llm: LLMClient, *, system_prompt: str, user_prompt: str, schema: type[S], stage: str) -> S:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            raw = llm.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        except InterviewError:
            raise
        except OutputTruncated:
            # 잘린 출력은 스키마 검사 실패와 같게 다룬다: 한 번 다시 보내고, 또 잘리면 AI_OUTPUT_INVALID
            logger.warning("stage=%s attempt=%d errorCode=%s reason=maxTokens durationMs=%d",
                           stage, attempt, AI_OUTPUT_INVALID, _ms(started))
            continue
        except Exception as exc:  # noqa: BLE001 — 권한, 한도 초과, 네트워크, SDK 오류
            logger.warning("stage=%s attempt=%d errorCode=%s errorType=%s durationMs=%d",
                           stage, attempt, AWS_SERVICE_ERROR, type(exc).__name__, _ms(started))
            raise InterviewError(AWS_SERVICE_ERROR, SERVICE_MESSAGE) from None
        try:
            parsed = schema.model_validate(extract_json(raw))
        except (ValueError, ValidationError):
            logger.warning("stage=%s attempt=%d errorCode=%s durationMs=%d",
                           stage, attempt, AI_OUTPUT_INVALID, _ms(started))
            continue
        logger.info("stage=%s attempt=%d durationMs=%d", stage, attempt, _ms(started))
        return parsed
    raise InterviewError(AI_OUTPUT_INVALID, AI_OUTPUT_MESSAGE)


# ---------------------------------------------------------------- Strands


_model = None  # 프로세스에서 한 번 만든다 (AGENTS.md "노션 허브 자료")


def _get_model():
    global _model
    if _model is None:
        model_id = settings.model_id()  # 없으면 여기서 설정 오류
        try:
            from strands.models import BedrockModel
        except ImportError:
            raise InterviewError(AWS_SERVICE_ERROR, settings.CONFIG_ERROR_MESSAGE, retryable=False) from None
        _model = BedrockModel(model_id=model_id, region_name=settings.region(), max_tokens=settings.max_tokens())
    return _model


def _reset_model() -> None:
    """테스트용. 만들어 둔 모델 클라이언트를 버린다."""
    global _model
    _model = None


class StrandsLLMClient:
    """면접관 에이전트. 도구 없이, 호출마다 새 Agent로 부른다 (세션끼리 대화가 섞이지 않게)."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        model = _get_model()
        from strands import Agent

        agent = Agent(model=model, system_prompt=system_prompt, tools=[], callback_handler=None)
        try:
            return str(agent(user_prompt))
        except Exception as exc:
            if type(exc).__name__ in _MAX_TOKENS_EXCEPTION_NAMES:
                raise OutputTruncated() from None
            raise


def default_client() -> LLMClient:
    return StrandsLLMClient()
