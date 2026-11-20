"""채용공고 입력 검사와 B 공고 변환 (#158, requirements 1~3)."""

import copy
import json
import logging

import pytest
from pydantic import ValidationError
from team07_contracts import PostingForAnalysis

import interview
from conftest import REPO_ROOT, sample_json
from interview import settings
from interview.errors import INVALID_INPUT, InterviewError
from interview.job_posting import (DESCRIPTION_HEADING, JOB_POSTING_INVALID_MESSAGE, PREFERRED_HEADING,
                                   REQUIRED_HEADING)
from interview.models import JobPostingInput

POSTING = sample_json("job_posting_data_analysis.json")
TEXT_30 = "가" * 30


def contract_postings():
    path = REPO_ROOT / "contracts" / "fixtures" / "valid" / "PostingForAnalysis.json"
    return {e["name"]: e["data"] for e in json.loads(path.read_text(encoding="utf-8"))["examples"]}


def requirement(kind, quote=None, name="요건 이름", **extra):
    item = {"requirementId": "req", "name": name, "kind": kind, **extra}
    if quote is not None:
        item["sourceQuote"] = quote
    return item


# ---------------------------------------------------------------- JobPostingInput (requirements 1)


@pytest.mark.parametrize("length, ok", [(29, False), (30, True), (4000, True), (4001, False)])
def test_text_length(length, ok):
    data = {"text": "가" * length}
    if ok:
        assert len(JobPostingInput.model_validate(data).text) == length
    else:
        with pytest.raises(ValidationError):
            JobPostingInput.model_validate(data)


def test_text_measured_after_strip():
    assert JobPostingInput.model_validate({"text": "\n\n  " + TEXT_30 + "  \n"}).text == TEXT_30
    with pytest.raises(ValidationError):
        JobPostingInput.model_validate({"text": "  " + "가" * 29 + "\n" * 10})


@pytest.mark.parametrize("field, max_len", [("title", 200), ("company", 100)])
def test_title_company_length(field, max_len):
    assert getattr(JobPostingInput.model_validate({"text": TEXT_30, field: "가" * max_len}), field) == "가" * max_len
    with pytest.raises(ValidationError):
        JobPostingInput.model_validate({"text": TEXT_30, field: "가" * (max_len + 1)})


@pytest.mark.parametrize("value", ["", "   ", None])
def test_blank_title_company_become_none(value):
    parsed = JobPostingInput.model_validate({"text": TEXT_30, "title": value, "company": value})
    assert parsed.title is None and parsed.company is None


def test_title_company_stripped():
    parsed = JobPostingInput.model_validate({"text": TEXT_30, "title": "  데이터 분석 신입 ", "company": " 가상 기업 "})
    assert parsed.title == "데이터 분석 신입" and parsed.company == "가상 기업"


@pytest.mark.parametrize("data", [
    {},                                              # text 없음
    {"text": None},
    {"text": 12345678901234567890123456789012345},   # 문자열 아님
    {"text": TEXT_30, "title": 123},
    {"text": TEXT_30, "requirements": ["SQL"]},      # 모르는 키
    {"text": TEXT_30, "jobPostingId": "job-1"},
    {"text": TEXT_30, "인재상": "소통"},
])
def test_invalid_inputs(data):
    with pytest.raises(ValidationError):
        JobPostingInput.model_validate(data)


def test_limits_come_from_settings():
    assert (settings.JOB_POSTING_TEXT_MIN, settings.JOB_POSTING_TEXT_MAX) == (30, 4000)
    assert (settings.JOB_POSTING_TITLE_MAX, settings.JOB_POSTING_COMPANY_MAX) == (200, 100)


# ---------------------------------------------------------------- normalize_job_posting (requirements 2)


def test_normalize_none():
    assert interview.normalize_job_posting(None) is None


def test_normalize_returns_three_keys():
    out = interview.normalize_job_posting(POSTING)
    assert out == {"title": POSTING["title"], "company": POSTING["company"], "text": POSTING["text"]}


def test_normalize_text_only():
    assert interview.normalize_job_posting({"text": "  " + TEXT_30}) == {"title": None, "company": None,
                                                                          "text": TEXT_30}


def test_normalize_does_not_change_input():
    data = {"title": "  제목 ", "text": "\n" + TEXT_30}
    before = copy.deepcopy(data)
    out = interview.normalize_job_posting(data)
    assert data == before and out is not data


@pytest.mark.parametrize("value", ["공고 본문 문자열" * 5, ["text"], 1, {"text": "짧음"}, {"text": TEXT_30, "x": 1}])
def test_normalize_rejects(value):
    with pytest.raises(InterviewError) as exc:
        interview.normalize_job_posting(value)
    assert exc.value.code == INVALID_INPUT and exc.value.retryable is False
    assert exc.value.message == JOB_POSTING_INVALID_MESSAGE
    assert "4,000자" in exc.value.message and "30자" in exc.value.message


def test_normalize_failure_logs_field_names_only(caplog):
    secret = "가상기업비밀업무내용" * 401  # 4,010자
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InterviewError) as exc:
            interview.normalize_job_posting({"title": "비밀 공고 제목", "company": "비밀 회사", "text": secret})
    assert "stage=normalize_job_posting errorCode=INVALID_INPUT fields=text" in caplog.text
    for raw in ("가상기업비밀업무내용", "비밀 공고 제목", "비밀 회사"):
        assert raw not in caplog.text and raw not in str(exc.value) and raw not in repr(exc.value)
    assert exc.value.__cause__ is None


# ---------------------------------------------------------------- job_posting_from_posting (requirements 3)


def test_from_posting_order_and_quotes():
    data = {
        "title": "데이터 분석 신입", "organization": "가상 데이터랩",
        "jobDescription": "  사내 서비스 이용 데이터를 분석해 지표 보고서를 작성합니다.  ",
        "requirements": [
            requirement("PREFERRED_SKILL", "Tableau 사용 경험 우대"),
            requirement("REQUIRED_SKILL", "SQL을 활용한 데이터 추출 경험"),
            requirement("REQUIRED_SKILL", None, name="Python 분석"),       # sourceQuote 없음 → name
            requirement("REQUIRED_SKILL", "   ", name="통계 지식"),         # 빈 sourceQuote → name
        ],
    }
    out = interview.job_posting_from_posting(data)
    assert out == {
        "title": "데이터 분석 신입", "company": "가상 데이터랩",
        "text": (f"{REQUIRED_HEADING}\n- SQL을 활용한 데이터 추출 경험\n- Python 분석\n- 통계 지식\n\n"
                 f"{PREFERRED_HEADING}\n- Tableau 사용 경험 우대\n\n"
                 f"{DESCRIPTION_HEADING}\n사내 서비스 이용 데이터를 분석해 지표 보고서를 작성합니다."),
    }
    assert interview.normalize_job_posting(out) == out


def test_from_posting_skips_empty_sections_and_bad_items():
    data = {"title": "제목", "organization": "회사", "requirements": [
        requirement("REQUIRED_SKILL", "SQL을 활용한 데이터 추출 및 가공 경험이 있는 분"),
        requirement("REQUIRED_SKILL", "SQL을 활용한 데이터 추출 및 가공 경험이 있는 분"),  # 같은 줄은 한 번
        requirement("ELIGIBILITY", "학사 이상"),        # 알 수 없는 kind
        requirement("REQUIRED_SKILL", None, name=""),   # 인용·이름 모두 없음
        "SQL",                                          # dict 아님
        requirement("REQUIRED_SKILL", "여러   칸\n줄바꿈 인용"),  # 줄 안 공백 정리
    ]}
    out = interview.job_posting_from_posting(data)
    assert out["text"] == f"{REQUIRED_HEADING}\n- SQL을 활용한 데이터 추출 및 가공 경험이 있는 분\n- 여러 칸 줄바꿈 인용"
    assert PREFERRED_HEADING not in out["text"] and DESCRIPTION_HEADING not in out["text"]


def test_from_posting_description_only():
    out = interview.job_posting_from_posting({"title": "t", "organization": "o", "requirements": [],
                                             "jobDescription": "관광 통계 데이터를 정제하고 대시보드를 운영하는 업무입니다."})
    assert out["text"].startswith(DESCRIPTION_HEADING + "\n관광 통계")


@pytest.mark.parametrize("data", [
    None, "공고", ["x"],
    {"title": "제목", "organization": "회사", "requirements": []},                       # 내용 없음
    {"title": "제목", "organization": "회사", "requirements": [requirement("REQUIRED_SKILL", "SQL")]},  # 30자 미만
    {"title": "제목", "requirements": "SQL", "jobDescription": None},                    # 형식이 틀린 값
])
def test_from_posting_none_when_too_short(data):
    assert interview.job_posting_from_posting(data) is None


def test_from_posting_truncates_but_keeps_requirements():
    data = {"title": "제목", "organization": "회사", "jobDescription": "업무 설명 " * 1000,
            "requirements": [requirement("REQUIRED_SKILL", "SQL 활용 가능자"),
                             requirement("PREFERRED_SKILL", "Python 시각화 경험")]}
    out = interview.job_posting_from_posting(data)
    assert len(out["text"]) <= settings.JOB_POSTING_TEXT_MAX
    assert out["text"].startswith(f"{REQUIRED_HEADING}\n- SQL 활용 가능자\n\n{PREFERRED_HEADING}\n- Python 시각화 경험")
    assert out["text"] == out["text"].rstrip()
    assert interview.normalize_job_posting(out) == out


def test_from_posting_title_company_cut_and_blank():
    out = interview.job_posting_from_posting({"title": "가" * 250, "organization": "  ",
                                             "jobDescription": "관광 통계 데이터를 정제하고 대시보드를 운영하는 업무입니다."})
    assert out["title"] == "가" * 200 and out["company"] is None
    out = interview.job_posting_from_posting({"jobDescription": "관광 통계 데이터를 정제하고 대시보드를 운영하는 업무입니다.",
                                             "organization": "나" * 150})
    assert out["title"] is None and out["company"] == "나" * 100
    assert interview.normalize_job_posting(out) == out


def test_from_posting_does_not_change_input():
    data = contract_postings()["busan-data-analysis"]
    before = copy.deepcopy(data)
    interview.job_posting_from_posting(data)
    assert data == before


def test_from_posting_contract_examples():
    examples = contract_postings()
    busan = interview.job_posting_from_posting(examples["busan-data-analysis"])
    assert busan == {
        "title": "데이터 분석 신입", "company": "가상 데이터랩 부산",
        "text": (f"{REQUIRED_HEADING}\n- SQL을 활용한 데이터 추출 및 가공 경험\n- Python 기반 데이터 분석 가능자\n\n"
                 f"{PREFERRED_HEADING}\n- Tableau 등 시각화 도구 사용 경험 우대\n\n"
                 f"{DESCRIPTION_HEADING}\n사내 서비스 이용 데이터를 분석해 지표 보고서를 작성합니다."),
    }
    assert "ADsP" not in busan["text"]  # eligibilityRules는 넣지 않는다
    seoul = interview.job_posting_from_posting(examples["seoul-data-analysis"])
    assert seoul["text"] == f"{REQUIRED_HEADING}\n- SQL 능숙자\n\n{PREFERRED_HEADING}\n- A/B 테스트 설계 경험 우대"
    assert interview.job_posting_from_posting(examples["region-unknown"]) is None  # 요건·설명 없음
    expired = interview.job_posting_from_posting(examples["expired"])
    assert expired is None  # 요건 한 줄(30자 미만)뿐
    for out in (busan, seoul):
        assert interview.normalize_job_posting(out) == out


def test_from_posting_accepts_contract_model():
    data = contract_postings()["busan-data-analysis"]
    model = PostingForAnalysis.model_validate(data)
    assert interview.job_posting_from_posting(model) == interview.job_posting_from_posting(data)
