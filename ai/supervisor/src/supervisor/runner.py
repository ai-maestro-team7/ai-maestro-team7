"""Strands 실행기 (D-38). 모델 클라이언트는 프로세스에서 한 번 만들고, Agent는 턴마다 새로 만든다.

strands-agents 1.65.0에서 확인한 것:
- Agent(messages=…)로 지난 대화를 넣는다. user로 시작하고 번갈아 와야 한다.
- agent(prompt, structured_output_model=…, limits=…)는 도구를 쓴 뒤 마지막 답을 Pydantic 모델로 돌려준다
  (AgentResult.structured_output). 맞추지 못하면 예외를 던진다.
- callback_handler 기본값은 모델 출력을 표준 출력에 찍는다. None으로 끈다 (답변 원문을 로그에 남기지 않는다).
"""

import logging
from collections.abc import Callable
from typing import Any

from .config import SupervisorConfig
from .errors import OutputInvalid
from .models import ChatReply

logger = logging.getLogger("supervisor")

# 모델 출력·스키마 문제로 보는 예외 이름. SDK 내부 모듈 경로에 묶이지 않게 이름으로 비교한다
_OUTPUT_EXCEPTIONS = frozenset({"StructuredOutputException", "MaxTokensReachedException", "ValidationError"})


class StrandsRunner:
    def __init__(self, *, model_id: str, region: str, config: SupervisorConfig):
        self.model_id, self.region, self.config = model_id, region, config
        self._model = None

    def _get_model(self):
        if self._model is None:
            from strands.models import BedrockModel

            kwargs: dict[str, Any] = {"model_id": self.model_id, "region_name": self.region,
                                      "max_tokens": self.config.max_tokens, "temperature": 0}
            thinking = self.config.thinking_for(self.model_id)
            if thinking is not None:
                kwargs["additional_request_fields"] = {"thinking": thinking}
                kwargs.pop("temperature")  # 생각 설정과 temperature를 같이 보내면 거절하는 모델이 있다
            self._model = BedrockModel(**kwargs)
        return self._model

    def run(self, *, system_prompt: str, history: list[dict], message: str, tools: list[Callable[..., Any]],
            max_turns: int) -> ChatReply:
        from strands import Agent, tool

        messages = [{"role": h["role"], "content": [{"text": h["text"]}]} for h in history]
        agent = Agent(model=self._get_model(), system_prompt=system_prompt, messages=messages,
                      tools=[tool(f) for f in tools], callback_handler=None)
        try:
            result = agent(message, structured_output_model=ChatReply, limits={"turns": max_turns})
        except Exception as error:
            if type(error).__name__ in _OUTPUT_EXCEPTIONS:
                raise OutputInvalid(type(error).__name__) from None
            raise
        output = getattr(result, "structured_output", None)
        if not isinstance(output, ChatReply):
            raise OutputInvalid("NO_STRUCTURED_OUTPUT")
        logger.info("stage=chat.agent stopReason=%s", getattr(result, "stop_reason", None))
        return output
