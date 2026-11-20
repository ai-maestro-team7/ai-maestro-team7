"""실제 Bedrock 확인 (tasks 10.1·10.2, Requirement 14.6). 기본 실행에서는 건너뛴다.

켜는 방법: aws login 뒤 RUN_BEDROCK=1, MODEL_ID를 넣고 이 파일만 -s로 실행한다.
결과 문장은 커밋하지 않는다. 질문이 샘플 자소서 내용을 반영하는지 사람이 눈으로 확인한다.

SHOW_RAW=1을 더 넣으면 max_tokens에서 잘린 응답의 길이와 앞 500자를 표준 출력에 찍는다.
원인 확인용이라 이 파일에서만 한다. 패키지 코드(llm.py)와 운영 로그에는 원문을 남기지 않는다.
"""

import os

import pytest

from conftest import sample_json, sample_text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BEDROCK") != "1" or not os.environ.get("MODEL_ID", "").strip(),
    reason="실제 Bedrock 호출은 RUN_BEDROCK=1과 MODEL_ID가 있을 때만",
)

RAW_PREVIEW_CHARS = 500


def _message_text(message) -> str:
    """Strands 메시지({"role", "content": [{"text": ...}, ...]})에서 텍스트 블록만 이어 붙인다."""
    if not isinstance(message, dict):
        return ""
    return "".join(block.get("text", "") for block in message.get("content", []) if isinstance(block, dict))


class _ShowRawClient:
    """StrandsLLMClient와 같은 호출을 하되, 잘린 응답을 화면에 찍는다.

    strands-agents는 MaxTokensReachedException을 던지기 전에 잘린 응답을 agent.messages에 넣는다
    (strands/types/exceptions.py 설명). 그 메시지를 읽은 뒤 llm.OutputTruncated로 바꿔 던져서
    call_json의 재시도·오류 처리는 운영과 같게 둔다.
    """

    def __init__(self):
        self.attempt = 0

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        from strands import Agent

        from interview import llm

        self.attempt += 1
        agent = Agent(model=llm._get_model(), system_prompt=system_prompt, tools=[], callback_handler=None)
        try:
            return str(agent(user_prompt))
        except Exception as exc:
            if type(exc).__name__ not in llm._MAX_TOKENS_EXCEPTION_NAMES:
                raise
            last = agent.messages[-1] if agent.messages else None
            role = last.get("role") if isinstance(last, dict) else None
            text = _message_text(last) if role == "assistant" else ""
            blocks = [next(iter(b), "?") for b in last.get("content", []) if isinstance(b, dict)] if role else []
            usage = agent.event_loop_metrics.accumulated_usage
            print(f"\n[SHOW_RAW] attempt={self.attempt} maxTokens reached, role={role}, length={len(text)}")
            # text 외 블록(예: reasoningContent)도 출력 토큰을 쓴다. 블록 종류와 실제 출력 토큰 수를 같이 본다
            print(f"[SHOW_RAW] blocks={blocks} outputTokens={usage.get('outputTokens')} "
                  f"maxTokens={llm._get_model().get_config().get('max_tokens')}")
            print(text[:RAW_PREVIEW_CHARS] if text else "(잘린 assistant 메시지 없음)")
            raise llm.OutputTruncated() from None


def test_generate_questions_with_real_model():
    from interview.questions import generate_questions

    client = _ShowRawClient() if os.environ.get("SHOW_RAW") == "1" else None
    questions = generate_questions("데이터 분석", sample_text("resume_data_analysis.txt"), "MIXED",
                                   sample_json("profile_data_analysis.json"), llm=client)
    assert [q["questionId"] for q in questions] == ["q1", "q2", "q3"]
    print()
    for q in questions:
        print(f"{q['questionId']} [{q['questionType']}] {q['question']}")
