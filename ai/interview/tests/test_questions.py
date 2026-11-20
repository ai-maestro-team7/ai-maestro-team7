import pytest

from conftest import sample_json, sample_text
from fakes import FakeLLM
from interview.errors import AI_OUTPUT_INVALID, INVALID_INPUT, InterviewError
from interview.questions import generate_questions

RESUME = sample_text("resume_data_analysis.txt")
PROFILE = sample_json("profile_data_analysis.json")
OK = sample_text("llm/questions_ok.json")


def test_generate_without_session_and_model_id(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)  # 가짜 LLM이면 모델 설정 없이도 된다
    fake = FakeLLM([OK])
    questions = generate_questions("데이터 분석", RESUME, "MIXED", llm=fake)
    assert [q["questionId"] for q in questions] == ["q1", "q2", "q3"]
    assert [q["questionType"] for q in questions] == ["experience", "knowledge", "situation"]
    assert all(set(q) == {"questionId", "questionType", "question"} for q in questions)
    assert len(fake.calls) == 1


def test_llm_ids_ignored_and_fenced_output():
    fake = FakeLLM([sample_text("llm/questions_fenced.txt")])
    questions = generate_questions("데이터 분석", RESUME, "JOB", llm=fake)
    assert [q["questionId"] for q in questions] == ["q1", "q2", "q3"]


def test_prompt_contents():
    fake = FakeLLM([OK])
    generate_questions("데이터 분석", RESUME, "PERSONALITY", PROFILE, llm=fake)
    call = fake.calls[0]
    assert "기출 문제" in call["system"]
    assert "<interview_type>\nPERSONALITY\n</interview_type>" in call["user"]
    assert "<resume>\n" + RESUME + "\n</resume>" in call["user"]
    assert "실무 데이터 파이프라인 경험" in call["user"]


def test_job_posting_keyword_reaches_prompt():
    # #158: generate_questions도 같은 공고 입력을 받는다 (키워드 인자)
    posting = sample_json("job_posting_data_analysis.json")
    fake = FakeLLM([OK])
    generate_questions("데이터 분석", RESUME, "JOB", job_posting=posting, llm=fake)
    assert "<job_posting>\n제목: " + posting["title"] in fake.calls[0]["user"]
    fake = FakeLLM([OK])
    generate_questions("데이터 분석", RESUME, "JOB", llm=fake)
    assert "<job_posting>\n\n</job_posting>" in fake.calls[0]["user"]


def test_invalid_job_posting_does_not_call_llm():
    fake = FakeLLM([OK])
    with pytest.raises(InterviewError) as exc:
        generate_questions("데이터 분석", RESUME, "JOB", job_posting={"text": "짧음"}, llm=fake)
    assert exc.value.code == INVALID_INPUT and fake.calls == []


def test_retry_then_success():
    fake = FakeLLM([sample_text("llm/questions_two_only.json"), OK])
    assert len(generate_questions("데이터 분석", RESUME, "MIXED", llm=fake)) == 3
    assert len(fake.calls) == 2


def test_two_questions_twice_raises():
    two = sample_text("llm/questions_two_only.json")
    fake = FakeLLM([two, two])
    with pytest.raises(InterviewError) as exc:
        generate_questions("데이터 분석", RESUME, "MIXED", llm=fake)
    assert exc.value.code == AI_OUTPUT_INVALID
    assert len(fake.calls) == 2


@pytest.mark.parametrize("args", [
    ("", RESUME, "MIXED", None),
    ("데이터 분석", "짧은 자소서", "MIXED", None),
    ("데이터 분석", RESUME, "TECH", None),
    ("데이터 분석", RESUME, "MIXED", {"targetJob": "데이터 분석"}),
])
def test_invalid_input_does_not_call_llm(args):
    fake = FakeLLM([OK])
    with pytest.raises(InterviewError) as exc:
        generate_questions(*args, llm=fake)
    assert exc.value.code == INVALID_INPUT
    assert fake.calls == []
