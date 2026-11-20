"""샘플 데이터가 계약·모델과 맞는지 확인한다 (Requirement 13). 뒤 task의 테스트가 이 샘플을 쓴다."""

import json
import re

import pytest
from pydantic import ValidationError

from conftest import REPO_ROOT, sample_json, sample_text
from interview import llm, settings
from interview.models import AnswerResult, FollowUpOutput, NextQuestion, QuestionRequest, QuestionsOutput, Session


def test_resume_length_and_job_type():
    resume = sample_text("resume_data_analysis.txt")
    assert settings.RESUME_MIN <= len(resume) <= settings.RESUME_MAX
    assert "데이터" in resume


@pytest.mark.parametrize("pattern", [
    r"01[016789]-?\d{3,4}-?\d{4}",  # 휴대전화
    r"[\w.+-]+@[\w-]+\.[\w.]+",     # 메일
    r"\d{6}-?[1-4]\d{6}",           # 주민번호
])
def test_resume_has_no_personal_info(pattern):
    assert re.search(pattern, sample_text("resume_data_analysis.txt")) is None


def test_resume_uses_placeholder_names():
    resume = sample_text("resume_data_analysis.txt")
    assert "A대학교" in resume and "B기관" in resume


def test_profile_matches_contract_example():
    path = REPO_ROOT / "contracts" / "fixtures" / "valid" / "CareerProfileSummary.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    demo = next(e["data"] for e in contract["examples"] if e["name"] == "data-analysis-demo")
    assert sample_json("profile_data_analysis.json") == demo


def test_sample_inputs_pass_validation():
    QuestionRequest.model_validate({"job": "데이터 분석", "resume_text": sample_text("resume_data_analysis.txt"),
                                    "interview_type": "MIXED", "profile": sample_json("profile_data_analysis.json")})


@pytest.mark.parametrize("name, evaluable_text", [
    ("normal_q1.json", True),
    ("abstract_q1.json", True),
    ("no_answer.json", False),
    ("transcribe_failed.json", False),
])
def test_answer_samples(name, evaluable_text):
    result = AnswerResult.model_validate(sample_json(f"answers/{name}"))
    has_text = result.transcription.status == "COMPLETED" and bool((result.transcription.text or "").strip())
    assert has_text is evaluable_text


def test_session_after_start_sample():
    data = sample_json("session_after_start.json")
    session = Session.model_validate(data["session"])
    nq = NextQuestion.model_validate(data["nextQuestion"])
    assert session.current_question == nq
    assert session.job == "데이터 분석"
    ok = QuestionsOutput.model_validate(sample_json("llm/questions_ok.json"))
    assert [q.question for q in session.questions] == [q.question for q in ok.questions]


@pytest.mark.parametrize("name", ["llm/questions_ok.json", "llm/questions_fenced.txt"])
def test_llm_question_samples_valid(name):
    QuestionsOutput.model_validate(llm.extract_json(sample_text(name)))


def test_llm_two_questions_sample_invalid():
    with pytest.raises(ValidationError):
        QuestionsOutput.model_validate(llm.extract_json(sample_text("llm/questions_two_only.json")))


@pytest.mark.parametrize("name, need, count", [
    ("llm/follow_up_needed.json", True, 1),
    ("llm/follow_up_multiple.json", True, 3),
    ("llm/follow_up_sufficient.json", False, 0),
])
def test_llm_follow_up_samples(name, need, count):
    out = FollowUpOutput.model_validate(llm.extract_json(sample_text(name)))
    assert out.need_follow_up is need and len(out.follow_up_questions) == count


def test_llm_not_json_sample():
    with pytest.raises(ValueError):
        llm.extract_json(sample_text("llm/not_json.txt"))


def test_samples_excluded_from_package_bundle():
    # infra/package.sh는 samples/와 tests/를 배포 묶음에서 뺀다
    script = (REPO_ROOT / "infra" / "package.sh").read_text(encoding="utf-8")
    assert "--exclude 'samples'" in script and "--exclude 'tests'" in script
