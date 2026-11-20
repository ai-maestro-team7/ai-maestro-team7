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

from .versions import PROMPT_A_VERSION, PROMPT_B_VERSION

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

DATA_TAGS = ("job", "interview_type", "resume", "profile", "question", "answer")

_TAG_RE = re.compile(r"<(/?)(" + "|".join(DATA_TAGS) + r")\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


def _file_for(version: str, stem: str) -> str:
    return f"{stem}_{version.split('-', 1)[1]}.md"  # "A-v1" → "a_questions_v1.md"


SYSTEM_FILE = "system_v1.md"
QUESTIONS_FILE = _file_for(PROMPT_A_VERSION, "a_questions")
FOLLOW_UP_FILE = _file_for(PROMPT_B_VERSION, "b_follow_up")


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


def follow_up_prompt(job: str, resume_text: str, question: str, answer_text: str) -> str:
    """Prompt_B 사용자 메시지."""
    return fill(load(FOLLOW_UP_FILE), {
        "JOB": wrap("job", job),
        "RESUME": wrap("resume", resume_text),
        "QUESTION": wrap("question", question),
        "ANSWER": wrap("answer", answer_text),
    })
