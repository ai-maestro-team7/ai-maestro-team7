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
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

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


def _failure_kind(exc: Exception) -> str:
    """출력 검사가 실패한 종류. 로그용이라 값은 넣지 않고 필드 이름만 넣는다.

    schema:필드,필드 = 스키마 검사 실패 · json = JSON으로 읽지 못함 · no_json = JSON이 없음(빈 출력 포함) · check = 스키마 밖 검사 실패
    """
    if isinstance(exc, ValidationError):
        fields = sorted({".".join(str(part) for part in e["loc"]) or "(root)"
                         for e in exc.errors(include_input=False, include_url=False)})
        return "schema:" + ",".join(fields)
    if isinstance(exc, json.JSONDecodeError):
        return "json"
    if str(exc) in ("not text", "no json object"):
        return "no_json"
    return "check"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class ToolLLMClient(Protocol):
    """툴을 골라 부르는 에이전트 실행 (report design §6.3). tools는 타입 힌트·설명이 있는 일반 함수다."""

    def run_with_tools(self, *, system_prompt: str, user_prompt: str, tools: list[Callable[..., Any]],
                       limits: dict[str, int], max_tokens: int | None = None) -> str: ...


def _call_with_retry(invoke: Callable[[], str], *, schema: type[S], stage: str,
                     check: Callable[[S], None] | None = None,
                     before_attempt: Callable[[], None] | None = None) -> S:
    """출력 검사와 재시도 규칙 (C §7). check는 스키마 밖의 검사이고, ValueError를 던지면 출력 실패로 본다.

    before_attempt는 시도마다 맨 처음에 불린다 (예: 툴 호출 상한을 시도마다 새로 세기).
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if before_attempt is not None:
            before_attempt()
        started = time.monotonic()
        try:
            raw = invoke()
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
            if check is not None:
                check(parsed)
        except (ValueError, ValidationError) as exc:
            # 왜 어긋났는지 알 수 있게 종류와 필드 이름, 출력 길이만 남긴다. 출력 내용은 남기지 않는다 (#121)
            logger.warning("stage=%s attempt=%d errorCode=%s kind=%s outputChars=%d durationMs=%d",
                           stage, attempt, AI_OUTPUT_INVALID, _failure_kind(exc),
                           len(raw) if isinstance(raw, str) else -1, _ms(started))
            continue
        logger.info("stage=%s attempt=%d durationMs=%d", stage, attempt, _ms(started))
        return parsed
    raise InterviewError(AI_OUTPUT_INVALID, AI_OUTPUT_MESSAGE)


def call_json(llm: LLMClient, *, system_prompt: str, user_prompt: str, schema: type[S], stage: str,
              check: Callable[[S], None] | None = None) -> S:
    return _call_with_retry(lambda: llm.complete(system_prompt=system_prompt, user_prompt=user_prompt),
                            schema=schema, stage=stage, check=check)


def call_json_with_tools(llm: ToolLLMClient, *, system_prompt: str, user_prompt: str,
                         tools: list[Callable[..., Any]], limits: dict[str, int], schema: type[S], stage: str,
                         check: Callable[[S], None] | None = None,
                         before_attempt: Callable[[], None] | None = None,
                         max_tokens: int | None = None) -> S:
    """call_json과 같은 규칙으로, 툴을 쓰는 에이전트의 마지막 답을 검사한다.

    limits(턴·토큰)는 strands가 에이전트 실행마다 새로 센다. 툴 쪽 상한은 before_attempt로 시도마다 새로 센다.
    max_tokens(호출당 출력 상한)를 주지 않으면 클라이언트 기본값(피드백 값)을 쓴다. 주지 않을 때는 인자를 넘기지 않아
    max_tokens를 모르는 클라이언트도 그대로 쓸 수 있다.
    """
    extra = {} if max_tokens is None else {"max_tokens": max_tokens}
    return _call_with_retry(lambda: llm.run_with_tools(system_prompt=system_prompt, user_prompt=user_prompt,
                                                       tools=tools, limits=limits, **extra),
                            schema=schema, stage=stage, check=check, before_attempt=before_attempt)


# ---------------------------------------------------------------- Strands


_models: dict[int, Any] = {}  # max_tokens별로 프로세스에서 한 번 만든다 (AGENTS.md "노션 허브 자료")


def _get_model(max_tokens: int | None = None):
    limit = settings.max_tokens() if max_tokens is None else max_tokens
    if limit not in _models:
        model_id = settings.model_id()  # 없으면 여기서 설정 오류
        try:
            from strands.models import BedrockModel
        except ImportError:
            raise InterviewError(AWS_SERVICE_ERROR, settings.CONFIG_ERROR_MESSAGE, retryable=False) from None
        kwargs = {"model_id": model_id, "region_name": settings.region(), "max_tokens": limit}
        thinking = settings.thinking_off(model_id)
        if thinking is not None:
            # strands BedrockConfig.additional_request_fields → Converse additionalModelRequestFields
            kwargs["additional_request_fields"] = {"thinking": thinking}
        _models[limit] = BedrockModel(**kwargs)
    return _models[limit]


def _reset_model() -> None:
    """테스트용. 만들어 둔 모델 클라이언트를 버린다."""
    _models.clear()


def _raise_truncated_or_reraise(exc: Exception):
    if type(exc).__name__ in _MAX_TOKENS_EXCEPTION_NAMES:
        raise OutputTruncated() from None
    raise exc


class StrandsLLMClient:
    """면접관 에이전트. 호출마다 새 Agent로 부른다 (세션끼리 대화가 섞이지 않게)."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """도구 없이 한 번 판단 (질문 생성, 꼬리질문 판단, 내용 평가)."""
        model = _get_model()
        from strands import Agent

        agent = Agent(model=model, system_prompt=system_prompt, tools=[], callback_handler=None)
        try:
            return str(agent(user_prompt))
        except Exception as exc:  # noqa: BLE001
            _raise_truncated_or_reraise(exc)

    def run_with_tools(self, *, system_prompt: str, user_prompt: str, tools: list[Callable[..., Any]],
                       limits: dict[str, int], max_tokens: int | None = None) -> str:
        """툴을 골라 부르는 에이전트 (피드백 report 결정 7, 꼬리질문 판단 #109).

        strands 1.65 Agent.__call__(limits=…)는 상한에 닿으면 예외 없이 다음 턴 경계에서 멈춘다.
        그때 마지막 답에 JSON이 없으면 호출한 쪽의 출력 검사가 실패로 본다.
        max_tokens가 없으면 피드백 값(INTERVIEW_FEEDBACK_MAX_TOKENS)을 쓴다.
        """
        model = _get_model(settings.feedback_max_tokens() if max_tokens is None else max_tokens)
        from strands import Agent, tool

        agent = Agent(model=model, system_prompt=system_prompt, tools=[tool(f) for f in tools],
                      callback_handler=None)
        started = time.monotonic()
        try:
            result = agent(user_prompt, limits=dict(limits))
        except Exception as exc:  # noqa: BLE001
            _raise_truncated_or_reraise(exc)
        logger.info("stage=agent stopReason=%s durationMs=%d", getattr(result, "stop_reason", None), _ms(started))
        return str(result)


def default_client() -> LLMClient:
    return StrandsLLMClient()
