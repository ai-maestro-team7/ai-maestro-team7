import copy
import inspect
import json
import logging

import pytest

from conftest import sample_json, sample_text
from fakes import FakeToolLLM
from interview import feedback, prompting, scoring, settings
from interview.config import load_scoring_config
from interview.errors import AI_OUTPUT_INVALID, AWS_SERVICE_ERROR, InterviewError
from scoring_helpers import all_evaluations, answer, delivery, session

NORMAL_TEXT = sample_json("answers/normal_q1.json")["transcription"]["text"]
RESUME = sample_text("resume_data_analysis.txt")
OK = sample_text("llm/c2_feedback_ok.json")
ALL_TOOLS = ["find_resume_passages", "get_answer_text", "get_confirmed_scores", "get_delivery_metrics"]


def context(follow_up=False):
    answers = [answer("q1", text=NORMAL_TEXT, metrics=delivery(rate=310.0, per_min=1.5)), answer("q2"), answer("q3")]
    if follow_up:
        answers.insert(1, answer("q1", follow_up=True, text="직접 대응표를 만들었습니다."))
    s = session(answers)
    content = all_evaluations()
    score = scoring.calculate_interview_scores(s, [], load_scoring_config(), content)
    return feedback.build_feedback_context(scoring.evaluable_bundles(s), content, score, RESUME)


def tools_for(ctx, limit=settings.FEEDBACK_MAX_TOOL_CALLS):
    usage = feedback.ToolUsage(limit)
    return {t.__name__: t for t in feedback.make_feedback_tools(ctx, usage)}, usage


# ---------------------------------------------------------------- 툴 (조회만)


def test_tools_are_documented_functions_without_user_ids():
    tools, _ = tools_for(context())
    assert sorted(tools) == ALL_TOOLS
    for fn in tools.values():
        assert fn.__doc__ and "Args:" in fn.__doc__  # strands가 툴 설명으로 쓴다
        params = inspect.signature(fn).parameters
        assert all(p.annotation is str for p in params.values())
        assert not {"user_id", "userId", "session_id", "sessionId"} & set(params)


def test_get_confirmed_scores():
    ctx = context()
    tools, _ = tools_for(ctx)
    out = tools["get_confirmed_scores"]("q1")
    assert out["contentScore"] == 80 and len(out["contentItems"]) == 4
    assert out["areas"]["attitude"]["notMeasuredReason"] == "ATTITUDE_NOT_READY"
    assert out["deliveryScore"] == ctx.score.bundles[0].delivery_score


def test_get_delivery_metrics_and_answer_text():
    tools, _ = tools_for(context(follow_up=True))
    m = tools["get_delivery_metrics"]("q1")
    assert m["metrics"]["speechRate"] == 310.0 and m["timeLimitReached"] is False
    a = tools["get_answer_text"]("q1")
    assert a["answer"] == NORMAL_TEXT and a["followUpAnswer"] == "직접 대응표를 만들었습니다."
    assert tools["get_answer_text"]("q2")["followUpQuestion"] is None


def test_unknown_question_is_error_fact_not_exception():
    tools, _ = tools_for(context())
    for name in ("get_confirmed_scores", "get_delivery_metrics", "get_answer_text"):
        out = tools[name]("q9")
        assert out["error"] == "UNKNOWN_QUESTION" and out["questionIds"] == ["q1", "q2", "q3"]


def test_find_resume_passages():
    tools, _ = tools_for(context())
    out = tools["find_resume_passages"]("관광")
    assert 1 <= len(out["passages"]) <= 3 and all("관광" in p for p in out["passages"])
    assert all(len(p) <= feedback.PASSAGE_MAX_CHARS for p in out["passages"])
    assert tools["find_resume_passages"]("없는단어xyz")["passages"] == []
    assert tools["find_resume_passages"]("  ")["error"] == "EMPTY_KEYWORD"
    assert tools["find_resume_passages"]("가" * 31)["error"] == "KEYWORD_TOO_LONG"


def test_tool_results_are_copies_and_scores_cannot_change():
    ctx = context()
    before = ctx.score.model_copy(deep=True)
    tools, _ = tools_for(ctx)
    out = tools["get_confirmed_scores"]("q1")
    out["contentScore"] = 100
    out["contentItems"][0]["score"] = 5
    out["areas"]["content"]["score"] = 100
    assert tools["get_confirmed_scores"]("q1")["contentScore"] == 80
    assert ctx.score == before
    with pytest.raises(Exception):
        ctx.score.total_score = 100  # frozen


def test_tool_call_limit():
    tools, usage = tools_for(context(), limit=2)
    assert "error" not in tools["get_answer_text"]("q1")
    assert "error" not in tools["get_confirmed_scores"]("q1")
    assert tools["get_delivery_metrics"]("q1")["error"] == "TOOL_LIMIT"
    assert usage.total == 3 and usage.summary() == "get_answer_text:1,get_confirmed_scores:1,get_delivery_metrics:1"


# ---------------------------------------------------------------- write_feedback


SCRIPT = [("get_confirmed_scores", {"question_id": "q1"}), ("get_answer_text", {"question_id": "q1"}),
          ("get_delivery_metrics", {"question_id": "q1"}), ("find_resume_passages", {"keyword": "관광"})]


def test_write_feedback_with_tools():
    ctx = context()
    before = ctx.score.model_copy(deep=True)
    fake = FakeToolLLM([OK], tool_calls=SCRIPT)
    out = feedback.write_feedback(ctx, llm=fake)
    assert sorted(out.by_question()) == ["q1", "q2", "q3"]
    assert ctx.score == before  # 에이전트가 끝난 뒤에도 점수 그대로
    run = fake.runs[0]
    assert run["tools"] == ALL_TOOLS
    assert run["limits"] == {"turns": settings.FEEDBACK_MAX_TURNS, "total_tokens": settings.FEEDBACK_MAX_TOTAL_TOKENS}
    assert run["system"] == prompting.eval_system_prompt()
    assert [name for name, _, _ in run["results"]] == [name for name, _ in SCRIPT]


def test_prompt_has_question_ids_but_not_answers_or_scores():
    fake = FakeToolLLM([OK])
    feedback.write_feedback(context(), llm=fake)
    user = fake.runs[0]["user"]
    for qid in ("q1", "q2", "q3"):
        assert f"questionId: {qid}" in user
    assert "<question>\nq1 질문입니다.\n</question>" in user
    assert NORMAL_TEXT not in user and "contentScore" not in user  # 답변·점수는 툴로 가져온다
    assert "{{" not in user


def _with(change):
    data = json.loads(OK)
    change(data)
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize("bad", [
    _with(lambda d: d["questions"][0].update(comment="합격 가능성이 높은 답변이에요.")),
    _with(lambda d: d["questions"][1]["strengths"].__setitem__(0, "합격 확률을 높이는 답변이에요.")),
    _with(lambda d: d["questions"].pop()),                                    # q3 빠짐
    _with(lambda d: d["questions"].append(dict(d["questions"][0]))),          # q1 두 번
    _with(lambda d: d["questions"][0].update(strengths=[])),
    _with(lambda d: d["questions"][0].update(improvements=["a", "b", "c"])),
    _with(lambda d: d["questions"][0].update(direction="짧음")),
    "",                                                                       # 턴 상한에 닿아 JSON 없음
])
def test_invalid_feedback_twice_raises(bad):
    fake = FakeToolLLM([bad, bad])
    with pytest.raises(InterviewError) as exc:
        feedback.write_feedback(context(), llm=fake)
    assert exc.value.code == AI_OUTPUT_INVALID and exc.value.retryable is True
    assert len(fake.runs) == 2


def test_more_than_two_strengths_keeps_first_two_without_retry():
    # 실제 Bedrock에서 강점 3개를 써서 스키마 실패가 났다 (#92 수동 확인). 실패시키지 않고 앞의 2개만 남긴다
    three = ["첫 번째 강점 문장입니다.", "두 번째 강점 문장입니다.", "세 번째 강점 문장입니다."]
    data = _with(lambda d: d["questions"][0].update(strengths=three, improvements=three))
    fake = FakeToolLLM([data])
    item = feedback.write_feedback(context(), llm=fake).by_question()["q1"]
    assert item.strengths == three[:2] and item.improvements == three[:2]
    assert len(fake.runs) == 1


def test_dropped_third_item_is_not_checked():
    # 버린 세 번째 문장은 검사하지 않는다 (남긴 2개만 검사)
    data = _with(lambda d: d["questions"][0].update(
        strengths=["첫 번째 강점 문장입니다.", "두 번째 강점 문장입니다.", "합격에 가까운 문장"]))
    assert feedback.write_feedback(context(), llm=FakeToolLLM([data])).by_question()["q1"].strengths[1] == \
        "두 번째 강점 문장입니다."


def test_kept_items_still_checked():
    data = _with(lambda d: d["questions"][0].update(strengths=["합격에 가까운 답변이에요.", "두 번째 강점 문장입니다.",
                                                              "세 번째 강점 문장입니다."]))
    with pytest.raises(InterviewError):
        feedback.write_feedback(context(), llm=FakeToolLLM([data, data]))


def test_banned_word_retried_then_ok():
    bad = _with(lambda d: d["questions"][0].update(comment="합격에 가까운 답변이에요."))
    fake = FakeToolLLM([bad, OK])
    assert len(feedback.write_feedback(context(), llm=fake).questions) == 3
    assert len(fake.runs) == 2


def test_extra_score_field_is_ignored_not_used():
    # 모델이 점수를 덧붙여도 출력 모델에 점수 필드가 없어 쓰이지 않는다
    sneaky = _with(lambda d: d["questions"][0].update(score=100, contentScore=100))
    out = feedback.write_feedback(context(), llm=FakeToolLLM([sneaky]))
    assert not hasattr(out.questions[0], "score") and "contentScore" not in out.questions[0].model_dump()


def test_service_error_not_retried():
    fake = FakeToolLLM([RuntimeError("throttled"), OK])
    with pytest.raises(InterviewError) as exc:
        feedback.write_feedback(context(), llm=fake)
    assert exc.value.code == AWS_SERVICE_ERROR and len(fake.runs) == 1


def test_no_bundles_rejected():
    ctx = context()
    empty = feedback.FeedbackContext(bundles=(), score=ctx.score, resume_text=RESUME)
    with pytest.raises(ValueError):
        feedback.write_feedback(empty, llm=FakeToolLLM([OK]))


def test_logs_have_tool_names_only(caplog):
    fake = FakeToolLLM([OK], tool_calls=SCRIPT)
    with caplog.at_level(logging.DEBUG, logger="interview"):
        feedback.write_feedback(context(), llm=fake)
    assert "stage=write_feedback toolCalls=find_resume_passages:1,get_answer_text:1" in caplog.text
    assert "관광" not in caplog.text and "대응표" not in caplog.text and "질문입니다" not in caplog.text


def test_context_is_immutable():
    ctx = context()
    snapshot = copy.deepcopy(ctx.model_dump())
    with pytest.raises(Exception):
        ctx.bundles[0].answer_text = "바뀜"
    assert ctx.model_dump() == snapshot
