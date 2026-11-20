"""실제 Bedrock 확인 (1차 tasks 10.1·10.2, 3차 report tasks 5). 기본 실행에서는 건너뛴다.

켜는 방법: aws login 뒤 RUN_BEDROCK=1, MODEL_ID를 넣고 이 파일만 -s로 실행한다 (botocore[crt] 포함).
결과 문장은 커밋하지 않는다. 질문·피드백이 샘플 자소서·답변을 반영하는지 사람이 눈으로 확인한다.
REPORT_RUNS=2를 넣으면 같은 Session으로 리포트를 두 번 만들어 C-1 점수 차이를 본다.

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


# ---------------------------------------------------------------- 리포트 (3차, report tasks 5)

# 샘플 질문(session_after_start.json)에 맞춘 가상 답변. 실제 사람 답변이 아니다
_Q2_ANSWER = ("서로 다른 출처의 데이터를 합칠 때는 먼저 날짜와 지역 같은 기준 열의 형식을 맞춥니다. "
              "누락 값은 바로 지우지 않고 어떤 행에서 빠졌는지 확인한 뒤, 분석에 영향이 크면 원 자료를 다시 확인했습니다. "
              "공공데이터 프로젝트에서는 기상 자료에 빠진 날이 있어 해당 날짜를 표시해 두고 분석에서 따로 봤습니다.")
_Q3_ANSWER = ("먼저 분석 과정에서 실수가 없었는지 데이터 처리 순서를 다시 확인하겠습니다. "
              "문제가 없다면 결과를 팀에 그대로 공유하고, 예상과 다른 이유를 설명할 수 있는 근거를 함께 정리하겠습니다. "
              "필요하면 기간을 나눠 다시 분석해 결과가 일관적인지 보겠습니다.")


def _manual_session():
    from interview.config import load_scoring_config
    from interview.delivery import measure_delivery
    from interview.models import Word
    from interview.voice import parse_transcript

    start = sample_json("session_after_start.json")["session"]
    tr = parse_transcript(sample_json("transcribe/result_normal.json"))
    metrics = measure_delivery(tr["text"], [Word(**w) for w in tr["words"]], load_scoring_config().delivery)
    delivery = metrics.model_dump(by_alias=True, mode="json")
    texts = [sample_json("answers/normal_q1.json")["transcription"]["text"], _Q2_ANSWER, _Q3_ANSWER]
    answers = [{"answerId": f"a-{q['questionId']}-1", "questionId": q["questionId"], "isFollowUp": False,
                "question": q["question"], "answerText": text, "evaluable": True, "reason": None,
                "timeLimitReached": False, "delivery": delivery}
               for q, text in zip(start["questions"], texts)]
    return dict(start, answers=answers, currentIndex=3, currentQuestion=None)


def test_generate_report_with_real_model(caplog):
    """REPORT_RUNS(기본 1)번 리포트를 만들고 점수·시간·툴 호출을 찍는다. 2번이면 C-1 점수 흔들림을 본다."""
    import logging
    import time

    import interview

    runs = int(os.environ.get("REPORT_RUNS", "1"))
    session = _manual_session()
    for n in range(1, runs + 1):
        caplog.clear()
        started = time.monotonic()
        with caplog.at_level(logging.INFO, logger="interview"):
            report = interview.generate_report(session, [])
        seconds = time.monotonic() - started
        tool_lines = [r.getMessage() for r in caplog.records if "stage=write_feedback toolCalls=" in r.getMessage()]
        stop_lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("stage=agent stopReason=")]
        print(f"\n[REPORT] run={n} seconds={seconds:.1f} totalScore={report['totalScore']} grade={report['grade']} "
              f"weightBasis={report['weightBasis']}")
        print(f"[REPORT] areas={report['areas']}")
        print(f"[REPORT] contentScores={[q['contentScore'] for q in report['questions']]}")
        print(f"[REPORT] {tool_lines[-1] if tool_lines else 'toolCalls=?'} | {stop_lines[-1] if stop_lines else ''}")
        for q in report["questions"]:
            print(f"  {q['questionId']} 강점={q['strengths']} 보완={q['improvements']} 한줄={q['comment']}")
        assert report["totalScore"] is not None and report["areas"]["attitude"]["score"] is None
