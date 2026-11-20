"""프롬프트 만들기 (design §7).

- 자료는 정해진 태그로 감싸 데이터로만 넘긴다. 자료 안의 같은 이름 태그는 무력화한다 (Requirement 6).
- 자리표시({{RESUME}} 등)는 한 번에 바꾼다. 넣은 자료 안의 자리표시가 다시 바뀌지 않게 하기 위해서다.
- 프롬프트 파일 이름은 versions.py의 버전에서 만든다. 버전을 올리면 새 파일이 있어야 한다.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from .versions import (PROMPT_A_VERSION, PROMPT_B_VERSION, PROMPT_C1_VERSION, PROMPT_C2_VERSION,
                       PROMPT_EVAL_SYSTEM_VERSION)

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

DATA_TAGS = ("job", "interview_type", "resume", "profile", "question", "answer",
             "question_type", "follow_up_question", "follow_up_answer")

_TAG_RE = re.compile(r"<(/?)(" + "|".join(DATA_TAGS) + r")\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


def _file_for(version: str, stem: str) -> str:
    return f"{stem}_{version.split('-', 1)[1]}.md"  # "A-v1" → "a_questions_v1.md"


SYSTEM_FILE = "system_v1.md"
QUESTIONS_FILE = _file_for(PROMPT_A_VERSION, "a_questions")
FOLLOW_UP_FILE = _file_for(PROMPT_B_VERSION, "b_follow_up")
EVAL_SYSTEM_FILE = _file_for(PROMPT_EVAL_SYSTEM_VERSION, "system_eval")
CONTENT_FILE = _file_for(PROMPT_C1_VERSION, "c1_content")
FEEDBACK_FILE = _file_for(PROMPT_C2_VERSION, "c2_feedback")


def neutralize(text: str) -> str:
    """자료 안의 <resume>, </answer> 같은 태그가 태그로 읽히지 않게 '<'를 '&lt;'로 바꾼다."""
    return _TAG_RE.sub(lambda m: "&lt;" + m.group(1) + m.group(2), text)


def wrap(tag: str, text: str) -> str:
    if tag not in DATA_TAGS:
        raise ValueError(f"unknown data tag: {tag}")
    return f"<{tag}>\n{neutralize(text)}\n</{tag}>"


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def fill(template: str, values: dict[str, str]) -> str:
    used = set(_PLACEHOLDER_RE.findall(template))
    if used != set(values):
        raise ValueError(f"placeholder mismatch: template={sorted(used)} values={sorted(values)}")
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def _profile_text(profile: BaseModel | None) -> str:
    if profile is None:
        return ""
    return json.dumps(profile.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)


def system_prompt() -> str:
    return load(SYSTEM_FILE)


def questions_prompt(job: str, interview_type: str, resume_text: str, profile: BaseModel | None) -> str:
    """Prompt_A 사용자 메시지."""
    return fill(load(QUESTIONS_FILE), {
        "JOB": wrap("job", job),
        "INTERVIEW_TYPE": wrap("interview_type", interview_type),
        "RESUME": wrap("resume", resume_text),
        "PROFILE": wrap("profile", _profile_text(profile)),
    })


def follow_up_prompt(job: str, resume_text: str, question_type: str, question: str, answer_text: str) -> str:
    """Prompt_B 사용자 메시지 (B-v2, #109). 이전 답변·남은 기본 질문은 넣지 않고 에이전트가 툴로 본다."""
    return fill(load(FOLLOW_UP_FILE), {
        "JOB": wrap("job", job),
        "RESUME": wrap("resume", resume_text),
        "QUESTION_TYPE": wrap("question_type", question_type),
        "QUESTION": wrap("question", question),
        "ANSWER": wrap("answer", answer_text),
    })


def eval_system_prompt() -> str:
    """C-1·C-2 시스템 프롬프트 (report 결정 6: system_v1의 '점수를 말하지 않는다'와 충돌해 따로 둔다)."""
    return load(EVAL_SYSTEM_FILE)


def content_prompt(job: str, resume_text: str, question_type: str, question: str, answer_text: str,
                   follow_up_question: str, follow_up_answer: str, rubric: str) -> str:
    """C-1 사용자 메시지. 꼬리질문이 없으면 follow_up 태그는 비운다. rubric은 코드가 정한 평가표 문장."""
    return fill(load(CONTENT_FILE), {
        "JOB": wrap("job", job),
        "RESUME": wrap("resume", resume_text),
        "QUESTION_TYPE": wrap("question_type", question_type),
        "QUESTION": wrap("question", question),
        "ANSWER": wrap("answer", answer_text),
        "FOLLOW_UP_QUESTION": wrap("follow_up_question", follow_up_question),
        "FOLLOW_UP_ANSWER": wrap("follow_up_answer", follow_up_answer),
        "RUBRIC": rubric,
    })


def feedback_prompt(questions: list[tuple[str, str, str]]) -> str:
    """C-2 사용자 메시지. (questionId, 질문 유형, 질문 문장)만 넣고 점수·답변은 에이전트가 툴로 가져온다."""
    blocks = [f"- questionId: {qid} / 유형: {qtype}\n{wrap('question', text)}" for qid, qtype, text in questions]
    return fill(load(FEEDBACK_FILE), {"QUESTIONS": "\n".join(blocks)})
