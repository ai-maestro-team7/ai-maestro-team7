"""질문 생성 (Prompt_A, design §3.2·§7.2).

generate_questions는 Session 없이 직무·자소서·면접 유형만 받는 독립 함수다 (결정 4).
나중에 챗 질문 연습 도구가 같은 함수를 쓸 수 있게 하려는 것이다 (architecture.md §5.3).
questionId는 코드가 q1부터 순서대로 붙인다. LLM이 준 ID는 쓰지 않는다.
"""

from . import llm as llm_module
from . import prompting
from .models import Question, QuestionRequest, QuestionsOutput, dump, parse_input

STAGE = "generate_questions"


def generate_from_request(request: QuestionRequest, llm=None) -> list[Question]:
    """검사를 마친 요청으로 기본 질문을 만든다. start_interview도 이 함수를 쓴다."""
    client = llm if llm is not None else llm_module.default_client()
    output = llm_module.call_json(
        client,
        system_prompt=prompting.system_prompt(),
        user_prompt=prompting.questions_prompt(request.job, request.interview_type, request.resume_text,
                                               request.profile, request.job_posting),
        schema=QuestionsOutput,
        stage=STAGE,
    )
    return [Question(question_id=f"q{i}", question_type=q.question_type, question=q.question)
            for i, q in enumerate(output.questions, start=1)]


def generate_questions(job, resume_text, interview_type, profile=None, *, job_posting=None, llm=None) -> list[dict]:
    """job_posting은 {title?, company?, text} (#158). 없으면 직무·자소서만으로 만든다."""
    request = parse_input(QuestionRequest, {"job": job, "resume_text": resume_text, "interview_type": interview_type,
                                            "profile": profile, "job_posting": job_posting}, stage=STAGE)
    return [dump(q) for q in generate_from_request(request, llm)]
