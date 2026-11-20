"""꼬리질문 판단 에이전트 (follow-up design §4, Requirement 1·2·4·8). AWS·Bedrock을 부르지 않는다."""

import copy
import inspect
import json
import logging

import pytest

import interview
from conftest import sample_text
from fakes import FakeLLM, FakeToolLLM
from interview import follow_up, llm, prompting, settings
from interview.errors import AWS_SERVICE_ERROR, InterviewError
from interview.tools import ToolUsage
from scoring_helpers import answer, session

NEEDED = sample_text("llm/follow_up_needed.json")
SUFFICIENT = sample_text("llm/follow_up_sufficient.json")
QUESTIONS_OK = sample_text("llm/questions_ok.json")
NOT_JSON = sample_text("llm/not_json.txt")
RESUME = sample_text("resume_data_analysis.txt")
ALL_TOOLS = ["find_resume_passages", "get_previous_answers", "get_remaining_questions"]


@pytest.fixture(autouse=True)
def model_id(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.delenv("INTERVIEW_FOLLOW_UP_MAX_TOKENS", raising=False)


def context_for(answers, base_index, answer_text="이번 답변입니다."):
    s = session(answers)
    return follow_up.build_follow_up_context(s, s.questions[base_index], s.questions[base_index].question, answer_text)


def tools_for(ctx, limit=settings.FOLLOW_UP_MAX_TOOL_CALLS):
    usage = ToolUsage(limit)
    usage.start_attempt()
    return {t.__name__: t for t in follow_up.make_follow_up_tools(ctx, usage)}, usage


# ---------------------------------------------------------------- 컨텍스트 범위 (Requirement 1.2~1.4)


def test_first_question_has_no_previous_and_two_remaining():
    ctx = context_for([], 0)
    assert ctx.previous == () and ctx.question_type == "experience"
    assert [(q.question_id, q.question_type) for q in ctx.remaining] == [("q2", "knowledge"), ("q3", "situation")]


def test_last_question_has_no_remaining_and_only_evaluable_previous():
    answers = [answer("q1", text="첫 답변"), answer("q1", follow_up=True, text="꼬리 답변"),
               answer("q2", evaluable=False, reason="NO_ANSWER")]
    ctx = context_for(answers, 2)
    assert ctx.remaining == ()
    assert [(p.question_id, p.is_follow_up, p.answer_text) for p in ctx.previous] == [
        ("q1", False, "첫 답변"), ("q1-f", True, "꼬리 답변")]  # 평가 불가 q2는 빠진다


def test_previous_answers_capped_by_count_and_length(monkeypatch):
    monkeypatch.setattr(settings, "FOLLOW_UP_PREVIOUS_MAX", 2)
    answers = [answer("q1", text="가" * 600), answer("q1", follow_up=True, text="둘째"), answer("q2", text="셋째")]
    ctx = context_for(answers, 2)
    assert len(ctx.previous) == 2  # 앞에서부터
    assert ctx.previous[0].answer_text == "가" * settings.FOLLOW_UP_ANSWER_MAX_CHARS


def test_context_is_frozen():
    ctx = context_for([], 0)
    with pytest.raises(Exception):
        ctx.answer_text = "바꿈"


# ---------------------------------------------------------------- 툴 (Requirement 1.5~1.7)


def test_tools_are_documented_and_take_no_ids():
    tools, _ = tools_for(context_for([], 0))
    assert sorted(tools) == ALL_TOOLS
    for fn in tools.values():
        assert fn.__doc__  # strands가 툴 설명으로 쓴다
        params = inspect.signature(fn).parameters
        assert not {"user_id", "userId", "session_id", "sessionId"} & set(params)
    assert list(inspect.signature(tools["find_resume_passages"]).parameters) == ["keyword"]
    assert not inspect.signature(tools["get_previous_answers"]).parameters
    assert not inspect.signature(tools["get_remaining_questions"]).parameters


def test_tool_results():
    answers = [answer("q1", text="자료를 비교했습니다.")]
    s = session(answers)
    ctx = follow_up.build_follow_up_context(s, s.questions[1], s.questions[1].question, "이번 답변")
    tools, _ = tools_for(ctx)  # scoring_helpers의 자소서는 "가" * 60 한 문장
    assert tools["get_previous_answers"]() == {"answers": [{"questionId": "q1", "isFollowUp": False,
                                                            "question": "q1 질문입니다.",
                                                            "answerText": "자료를 비교했습니다."}], "count": 1}
    assert tools["get_remaining_questions"]() == {"questions": [{"questionId": "q3", "questionType": "situation",
                                                                 "question": "q3 질문입니다."}], "count": 1}
    assert tools["find_resume_passages"]("가가")["found"] == 1
    assert tools["find_resume_passages"]("  ") == {"error": "EMPTY_KEYWORD"}


def test_tool_results_are_copies():
    ctx = context_for([answer("q1", text="자료를 비교했습니다.")], 1)
    before = ctx.model_copy(deep=True)
    tools, _ = tools_for(ctx)
    first = tools["get_previous_answers"]()
    first["answers"][0]["answerText"] = "바꿈"
    first["answers"].append({"x": 1})
    tools["get_remaining_questions"]()["questions"].clear()
    assert tools["get_previous_answers"]()["answers"][0]["answerText"] == "자료를 비교했습니다."
    assert tools["get_remaining_questions"]()["count"] == 1
    assert ctx == before


def test_tool_call_limit():
    tools, usage = tools_for(context_for([], 0), limit=4)
    for _ in range(4):
        assert "error" not in tools["get_remaining_questions"]()
    assert tools["get_previous_answers"]()["error"] == "TOOL_LIMIT"
    usage.start_attempt()  # 다음 시도는 새로 센다
    assert "error" not in tools["get_previous_answers"]()


# ---------------------------------------------------------------- process_answer에서 (이번 답변·이후는 안 보임)


def _after_q1():
    started = interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, None,
                                        llm=FakeLLM([QUESTIONS_OK]))
    q1 = {"answerId": "a-q1-1", "timeLimitReached": False,
          "transcription": {"status": "COMPLETED", "text": "첫 번째 답변 원문입니다.", "words": []}}
    return interview.process_answer(started["session"], q1, llm=FakeLLM([SUFFICIENT]))["session"]


def test_tools_in_process_answer_see_only_earlier_answers_and_later_questions():
    s = _after_q1()
    before = copy.deepcopy(s)
    fake = FakeToolLLM([SUFFICIENT], tool_calls=[("get_previous_answers", {}), ("get_remaining_questions", {}),
                                                 ("find_resume_passages", {"keyword": "부산"})])
    q2 = {"answerId": "a-q2-1", "timeLimitReached": False,
          "transcription": {"status": "COMPLETED", "text": "두 번째 답변 원문입니다.", "words": []}}
    out = interview.process_answer(s, q2, llm=fake)
    results = {name: result for name, _, result in fake.runs[0]["results"]}
    prev = results["get_previous_answers"]["answers"]
    assert [a["answerText"] for a in prev] == ["첫 번째 답변 원문입니다."]  # 이번 답변(q2)은 없다
    assert [q["questionId"] for q in results["get_remaining_questions"]["questions"]] == ["q3"]
    assert results["find_resume_passages"]["found"] >= 1
    assert fake.runs[0]["tools"] == ALL_TOOLS
    assert out["action"] == "NEXT_QUESTION" and out["session"]["answers"][-1]["followUpCheck"] == "SUFFICIENT"
    assert s == before  # 받은 Session은 그대로


# ---------------------------------------------------------------- 판단 (Requirement 2·4)


def test_judge_success_passes_prompt_tools_limits_and_max_tokens():
    ctx = context_for([], 1, answer_text="원리는 잘 모르지만 써 봤습니다.")
    fake = FakeToolLLM([NEEDED])
    decision = follow_up.judge_follow_up(ctx, llm=fake)
    assert decision == follow_up.FollowUpDecision(
        need=True, reason="ABSTRACT", question=json.loads(NEEDED)["followUpQuestions"][0])
    run = fake.runs[0]
    assert run["system"] == prompting.system_prompt()
    assert "<question_type>\nknowledge\n</question_type>" in run["user"]
    assert "<answer>\n원리는 잘 모르지만 써 봤습니다.\n</answer>" in run["user"]
    assert run["tools"] == ALL_TOOLS
    assert run["limits"] == {"turns": 4, "total_tokens": 12000} and run["max_tokens"] == 1024


def test_judge_max_tokens_from_env(monkeypatch):
    monkeypatch.setenv("INTERVIEW_FOLLOW_UP_MAX_TOKENS", "512")
    fake = FakeToolLLM([SUFFICIENT])
    follow_up.judge_follow_up(context_for([], 0), llm=fake)
    assert fake.runs[0]["max_tokens"] == 512


@pytest.mark.parametrize("outputs", [
    [NOT_JSON, NOT_JSON],                                                # 형식 오류 2번
    ["도구 호출 한도에 닿아 여기서 멈춥니다.", "턴 상한에 닿았습니다."],      # 상한에 닿아 JSON 없이 멈춤
    [llm.OutputTruncated(), llm.OutputTruncated()],                      # 출력 잘림 2번
    [NOT_JSON, llm.OutputTruncated()],
])
def test_judge_output_failure_falls_back(outputs, caplog):
    fake = FakeToolLLM(outputs, tool_calls=[("get_previous_answers", {})])
    with caplog.at_level(logging.INFO, logger="interview"):
        decision = follow_up.judge_follow_up(context_for([], 0), llm=fake)
    assert decision == follow_up.FollowUpDecision(need=False, reason="JUDGE_FAILED", question=None)
    assert len(fake.runs) == 2
    assert "stage=judge_follow_up fallback=NO_FOLLOW_UP errorCode=AI_OUTPUT_INVALID attempts=2" in caplog.text
    assert "toolCalls=get_previous_answers:2" in caplog.text


def test_judge_tool_limit_reset_per_attempt():
    # 상한(4)을 넘게 부르는 시도가 실패해도, 재시도는 새로 센다 (3차 피드백과 같은 방식)
    calls = [("get_remaining_questions", {})] * 5
    fake = FakeToolLLM([NOT_JSON, SUFFICIENT], tool_calls=calls)
    decision = follow_up.judge_follow_up(context_for([], 0), llm=fake)
    assert decision.reason == "SUFFICIENT"
    for run in fake.runs:
        assert [r.get("error") for _, _, r in run["results"]] == [None] * 4 + ["TOOL_LIMIT"]


def test_judge_bedrock_failure_raises():
    fake = FakeToolLLM([RuntimeError("bedrock down")])
    with pytest.raises(InterviewError) as exc:
        follow_up.judge_follow_up(context_for([], 0), llm=fake)
    assert exc.value.code == AWS_SERVICE_ERROR


def test_judge_config_error_raises(monkeypatch):
    monkeypatch.setenv("INTERVIEW_FOLLOW_UP_MAX_TOKENS", "0")
    with pytest.raises(InterviewError) as exc:
        follow_up.judge_follow_up(context_for([], 0), llm=FakeToolLLM([SUFFICIENT]))
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False


def test_logs_have_tool_names_only(caplog):
    secret_answer = "비밀 답변 문장 아무도 몰라"
    ctx = context_for([answer("q1", text=secret_answer)], 1)
    fake = FakeToolLLM([NEEDED], tool_calls=[("get_previous_answers", {}), ("find_resume_passages", {"keyword": "가"})])
    with caplog.at_level(logging.DEBUG):
        follow_up.judge_follow_up(ctx, llm=fake)
    assert "stage=judge_follow_up reason=ABSTRACT candidates=1 dropped=0 attempts=1" in caplog.text
    assert "toolCalls=find_resume_passages:1,get_previous_answers:1" in caplog.text
    for secret in (secret_answer, "가" * 10, json.loads(NEEDED)["followUpQuestions"][0], "q2 질문입니다"):
        assert secret not in caplog.text


def test_real_strands_tool_wraps_follow_up_tools():
    # 설치된 strands가 인자 없는 툴과 키워드 툴을 툴로 감쌀 수 있는지. 네트워크 없음
    strands = pytest.importorskip("strands")
    tools, _ = tools_for(context_for([], 0))
    specs = {name: strands.tool(fn).tool_spec for name, fn in tools.items()}
    assert sorted(spec["name"] for spec in specs.values()) == ALL_TOOLS
    assert all(spec["description"] for spec in specs.values())
    assert "keyword" in json.dumps(specs["find_resume_passages"]["inputSchema"])
