"""tools.py 공통 툴 부분 (follow-up design §3, Requirement 1.1·1.7·7.4). AWS·LLM을 부르지 않는다."""

import pytest

from interview import feedback, tools

RESUME = ("저는 부산 관광 데이터를 분석했습니다. 공공데이터 API로 방문객 수를 모았습니다.\n"
          "Python과 SQL로 전처리를 했고, 결측치는 평균으로 채웠습니다! 팀 프로젝트에서 시각화를 맡았습니다?\n"
          "관광 수요 예측 모델도 만들었습니다. 관광   안내 앱 기획에도 참여했습니다.")


# ---------------------------------------------------------------- search_resume


def test_finds_sentences_with_keyword():
    out = tools.search_resume(RESUME, "관광")
    assert out["keyword"] == "관광" and out["found"] == 3
    assert out["passages"] == ["저는 부산 관광 데이터를 분석했습니다.", "관광 수요 예측 모델도 만들었습니다.",
                               "관광 안내 앱 기획에도 참여했습니다."]  # 문장 안 공백도 정리


def test_case_insensitive_and_whitespace_normalized_keyword():
    assert tools.search_resume(RESUME, "  python  ")["passages"] == [
        "Python과 SQL로 전처리를 했고, 결측치는 평균으로 채웠습니다!"]
    assert tools.search_resume(RESUME, "공공데이터   API")["found"] == 1


def test_splits_on_question_and_exclamation_marks():
    assert tools.search_resume(RESUME, "시각화")["passages"] == ["팀 프로젝트에서 시각화를 맡았습니다?"]


def test_at_most_three_passages_and_200_chars():
    long_sentence = "가" * 250 + " 키워드."
    resume = " ".join(["키워드가 있는 문장입니다."] * 5) + " " + long_sentence
    out = tools.search_resume(resume, "키워드")
    assert out["found"] == 6 and len(out["passages"]) == tools.RESUME_PASSAGE_LIMIT
    capped = tools.search_resume(long_sentence, "키워드")
    # 키워드는 자르기 전 문장에서 찾고, 돌려줄 때만 200자로 자른다 (3차 피드백 툴과 같은 동작)
    assert capped["found"] == 1 and capped["passages"] == ["가" * tools.PASSAGE_MAX_CHARS]


def test_no_hit():
    assert tools.search_resume(RESUME, "블록체인") == {"keyword": "블록체인", "passages": [], "found": 0}


@pytest.mark.parametrize("keyword", ["", "   ", None])
def test_empty_keyword(keyword):
    assert tools.search_resume(RESUME, keyword) == {"error": "EMPTY_KEYWORD"}


def test_keyword_length_boundary():
    assert "error" not in tools.search_resume(RESUME, "가" * 30)
    assert tools.search_resume(RESUME, "가" * 31) == {"error": "KEYWORD_TOO_LONG", "maxChars": 30}


def test_search_does_not_change_inputs():
    text = str(RESUME)
    tools.search_resume(text, "관광")
    assert text == RESUME


# ---------------------------------------------------------------- ToolUsage


def test_tool_usage_limit_per_attempt():
    usage = tools.ToolUsage(2)
    usage.start_attempt()
    assert usage.take("a") is None and usage.take("b") is None
    assert usage.take("a")["error"] == "TOOL_LIMIT"  # 3번째에서 상한
    usage.start_attempt()  # 시도마다 새로 센다
    assert usage.total == 0 and usage.take("a") is None
    assert usage.attempts == 2
    assert usage.summary() == "a:3,b:1"  # 로그는 모든 시도의 합, 이름 순


def test_tool_usage_summary_when_unused():
    assert tools.ToolUsage(1).summary() == "none"


# ---------------------------------------------------------------- 피드백이 같은 코드를 쓴다


def test_feedback_reexports_shared_names():
    assert feedback.ToolUsage is tools.ToolUsage
    assert (feedback.PASSAGE_MAX_CHARS, feedback.RESUME_PASSAGE_LIMIT, feedback.KEYWORD_MAX_CHARS) == (200, 3, 30)
