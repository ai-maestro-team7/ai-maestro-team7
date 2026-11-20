"""로그와 표준 출력에 자소서·답변·질문·profile 원문이 남지 않는지 확인한다 (Requirement 12)."""

import ast
import logging
from pathlib import Path

import pytest

import interview
from conftest import sample_json, sample_text
from fakes import FakeLLM

PACKAGE_DIR = Path(interview.__file__).resolve().parent
RESUME = sample_text("resume_data_analysis.txt")
PROFILE = sample_json("profile_data_analysis.json")
QUESTIONS = sample_json("llm/questions_ok.json")["questions"]
ANSWER_TEXT = sample_json("answers/normal_q1.json")["transcription"]["text"]
FOLLOW_UP_TEXT = sample_json("llm/follow_up_needed.json")["followUpQuestions"][0]
JOB_POSTING = sample_json("job_posting_data_analysis.json")

SECRETS = [
    "공공데이터 포털의 관광지 입장객 통계",  # 자소서
    "A대학교 통계학과",                      # 자소서
    "이름을 짝지은 대응표",                  # 답변
    QUESTIONS[0]["question"],                # 질문
    FOLLOW_UP_TEXT,                          # 꼬리질문
    "실무 데이터 파이프라인 경험",            # profile
    "관광 통계 데이터 정제와 대시보드 운영",  # 채용공고 본문 (#158)
    JOB_POSTING["title"],                    # 채용공고 제목
    JOB_POSTING["company"],                  # 채용공고 회사
]


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "test-model")


def answer(answer_id, text):
    return {"answerId": answer_id, "timeLimitReached": False,
            "transcription": {"status": "COMPLETED", "text": text, "words": []}}


def assert_clean(text):
    for secret in SECRETS:
        assert secret not in text, f"원문이 남았다: {secret[:10]}"


def test_full_flow_logs_and_stdout_have_no_raw_text(caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        result = interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE,
                                           llm=FakeLLM([sample_text("llm/questions_ok.json")]))
        out = interview.process_answer(result["session"], answer("a-q1-1", ANSWER_TEXT),
                                       llm=FakeLLM([sample_text("llm/follow_up_needed.json")]))
        interview.process_answer(out["session"], answer("a-q1-2", ANSWER_TEXT), llm=FakeLLM([]))
    assert "stage=start_interview" in caplog.text and "stage=process_answer" in caplog.text
    assert_clean(caplog.text)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_failure_paths_have_no_raw_text(caplog):
    with caplog.at_level(logging.DEBUG):
        # 입력 검사 실패: 자소서는 정상, job만 틀림
        with pytest.raises(interview.InterviewError):
            interview.start_interview("iv-1", "", RESUME, "MIXED", True, PROFILE, llm=FakeLLM([]))
        # LLM 출력이 원문을 담은 채 형식이 틀림 (2번)
        bad = '{"questions": "' + RESUME[:40] + '"}'
        with pytest.raises(interview.InterviewError) as exc:
            interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE, llm=FakeLLM([bad, bad]))
        # 모델 호출 예외 메시지에 원문이 들어 있어도 로그에는 예외 종류만
        with pytest.raises(interview.InterviewError):
            interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE,
                                      llm=FakeLLM([RuntimeError(RESUME)]))
    assert "errorCode=INVALID_INPUT" in caplog.text and "errorCode=AI_OUTPUT_INVALID" in caplog.text
    assert "errorType=RuntimeError" in caplog.text
    assert_clean(caplog.text)
    assert_clean(str(exc.value))
    assert_clean(repr(exc.value))


def test_job_posting_paths_have_no_raw_text(caplog, capsys):
    # #158: 공고가 있는 시작, 잘못된 공고(검사 함수·시작 함수), 변환 함수 모두 원문을 남기지 않는다
    too_long = dict(JOB_POSTING, text=JOB_POSTING["text"] * 40)  # 4,000자 넘음
    with caplog.at_level(logging.DEBUG):
        interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE, JOB_POSTING,
                                  llm=FakeLLM([sample_text("llm/questions_ok.json")]))
        for call in (lambda: interview.normalize_job_posting(too_long),
                     lambda: interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE, too_long,
                                                       llm=FakeLLM([]))):
            with pytest.raises(interview.InterviewError) as exc:
                call()
            assert_clean(str(exc.value))
            assert_clean(repr(exc.value))
        interview.job_posting_from_posting({"title": JOB_POSTING["title"], "organization": JOB_POSTING["company"],
                                            "jobDescription": JOB_POSTING["text"]})
    assert "jobPosting=True" in caplog.text and "fields=text" in caplog.text
    assert "fields=job_posting.text" in caplog.text  # 함수 인자로 넘기므로 Python 필드 이름
    assert_clean(caplog.text)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_follow_up_fallback_logs_have_no_raw_text(caplog):
    # 꼬리질문 판단 출력이 원문을 담은 채 2번 실패해도(→ 꼬리질문 없이 진행) 로그에는 코드만 남는다 (#109)
    result = interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE,
                                       llm=FakeLLM([sample_text("llm/questions_ok.json")]))
    bad = '{"needFollowUp": true, "reason": "ABSTRACT", "followUpQuestions": ["' + ANSWER_TEXT[:20] * 10 + '"]}'
    with caplog.at_level(logging.DEBUG):
        out = interview.process_answer(result["session"], answer("a-q1-1", ANSWER_TEXT), llm=FakeLLM([bad, bad]))
    assert out["action"] == "NEXT_QUESTION"
    assert "fallback=NO_FOLLOW_UP" in caplog.text and "followUpCheck=JUDGE_FAILED" in caplog.text
    assert_clean(caplog.text)


def test_voice_logs_have_no_raw_text(monkeypatch, caplog, capsys):
    from fakes import FakePolly, FakeS3, FakeTranscribe, client_error
    from interview import voice

    transcript_doc = sample_text("transcribe/result_normal.json")
    spoken = "대응표를 만들고 이름을 통일했습니다"  # 결과 파일 속 답변 문장
    fake_t = FakeTranscribe()
    monkeypatch.setattr(voice, "_transcribe_client", lambda: fake_t)
    monkeypatch.setattr(voice, "_s3_client", lambda: FakeS3(default_body=transcript_doc))
    with caplog.at_level(logging.DEBUG):
        monkeypatch.setattr(voice, "_polly_client", lambda: FakePolly())
        interview.synthesize_question(QUESTIONS[0]["question"])
        monkeypatch.setattr(voice, "_polly_client", lambda: FakePolly(error=client_error("ThrottlingException")))
        interview.synthesize_question(QUESTIONS[0]["question"])
        job = interview.start_transcription("s3://b/uploads/a.webm", "job-1", "webm", "b", "uploads/t/a.json")
        tr = interview.get_transcription_result(job)
        out = interview.start_interview("iv-1", "데이터 분석", RESUME, "MIXED", True, PROFILE,
                                        llm=FakeLLM([sample_text("llm/questions_ok.json")]))
        interview.process_answer(out["session"], {"answerId": "a-q1-1", "transcription": tr},
                                 llm=FakeLLM([sample_text("llm/follow_up_sufficient.json")]))
    assert spoken in tr["text"]
    for stage in ("synthesize_question", "start_transcription", "get_transcription_result", "process_answer"):
        assert f"stage={stage}" in caplog.text
    assert_clean(caplog.text)
    assert spoken not in caplog.text and "uploads/" not in caplog.text
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_no_print_in_package_source():
    found = []
    for path in PACKAGE_DIR.rglob("*.py"):
        if "tests" in path.relative_to(PACKAGE_DIR).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                found.append(path.name)
    assert found == []
