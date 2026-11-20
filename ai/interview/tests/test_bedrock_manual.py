"""실제 Bedrock 확인 (tasks 10.1·10.2, Requirement 14.6). 기본 실행에서는 건너뛴다.

켜는 방법: aws login 뒤 RUN_BEDROCK=1, MODEL_ID를 넣고 이 파일만 -s로 실행한다.
결과 문장은 커밋하지 않는다. 질문이 샘플 자소서 내용을 반영하는지 사람이 눈으로 확인한다.
"""

import os

import pytest

from conftest import sample_json, sample_text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BEDROCK") != "1" or not os.environ.get("MODEL_ID", "").strip(),
    reason="실제 Bedrock 호출은 RUN_BEDROCK=1과 MODEL_ID가 있을 때만",
)


def test_generate_questions_with_real_model():
    from interview.questions import generate_questions

    questions = generate_questions("데이터 분석", sample_text("resume_data_analysis.txt"), "MIXED",
                                   sample_json("profile_data_analysis.json"))
    assert [q["questionId"] for q in questions] == ["q1", "q2", "q3"]
    print()
    for q in questions:
        print(f"{q['questionId']} [{q['questionType']}] {q['question']}")
