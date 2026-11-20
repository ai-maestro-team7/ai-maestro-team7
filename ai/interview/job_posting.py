"""채용공고 입력 검사와 B 공고 변환 (#158, design §4).

- normalize_job_posting: 백엔드가 /start 본문의 jobPosting을 검사할 때 쓴다. start_interview도 같은 모델로 검사한다.
- job_posting_from_posting: B 공고 상세(posting)나 계약 PostingForAnalysis를 jobPosting 값으로 바꾼다.
  C는 계약 PostingForAnalysis의 소비자다. 공고를 찾지 않고 받은 값만 바꾼다 (DB·API·LLM 호출 없음).
"""

from collections.abc import Mapping
from typing import Any

from . import settings
from .errors import INVALID_INPUT, InterviewError
from .models import JobPostingInput, parse_input

STAGE = "normalize_job_posting"

JOB_POSTING_INVALID_MESSAGE = (f"채용공고 내용을 확인해 주세요. 공고 본문은 {settings.JOB_POSTING_TEXT_MIN}자 이상 "
                               f"{settings.JOB_POSTING_TEXT_MAX:,}자 이하로 넣어 주세요.")

# 변환 결과 본문의 절 제목. 요건을 앞에 둬서 4,000자에서 잘려도 요건이 남게 한다 (design §4.2)
REQUIRED_HEADING = "[필수 요건]"
PREFERRED_HEADING = "[우대 사항]"
DESCRIPTION_HEADING = "[공고 내용]"
_KIND_HEADINGS = {"REQUIRED_SKILL": REQUIRED_HEADING, "PREFERRED_SKILL": PREFERRED_HEADING}


def normalize_job_posting(value: Any) -> dict | None:
    """jobPosting 값을 검사해 {title, company, text}로 돌려준다. None이면 None (공고 없이 면접).

    어긋나면 INVALID_INPUT. 로그에는 실패한 필드 이름만 남는다 (models.parse_input).
    """
    if value is None:
        return None
    try:
        posting = parse_input(JobPostingInput, value, stage=STAGE)
    except InterviewError:
        raise InterviewError(INVALID_INPUT, JOB_POSTING_INVALID_MESSAGE) from None
    return {"title": posting.title, "company": posting.company, "text": posting.text}


def _clean(value: Any, max_len: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if max_len is not None:
        value = value[:max_len].strip()
    return value or None


def _requirement_line(item: Any) -> tuple[str, str] | None:
    """요건 하나 → (절 제목, 줄). 원문 인용(sourceQuote)이 있으면 그것을, 없으면 요건 이름을 쓴다."""
    if not isinstance(item, Mapping):
        return None
    heading = _KIND_HEADINGS.get(item.get("kind"))
    text = _clean(item.get("sourceQuote")) or _clean(item.get("name"))
    if heading is None or text is None:
        return None
    return heading, "- " + " ".join(text.split())


def job_posting_from_posting(data: Any) -> dict | None:
    """B 공고 상세를 jobPosting 값으로 바꾼다. 본문이 30자 미만이면 None (공고 없이 면접).

    본문 순서: [필수 요건] → [우대 사항] → [공고 내용](jobDescription). 4,000자를 넘으면 자른다.
    eligibilityRules·마감일·근무지·급여는 넣지 않는다 (requirements 3.8). 받은 값은 바꾸지 않는다.
    """
    if hasattr(data, "model_dump"):  # 계약 모델(PostingForAnalysis 등)
        data = data.model_dump(by_alias=True, mode="json")
    if not isinstance(data, Mapping):
        return None

    lines: dict[str, list[str]] = {REQUIRED_HEADING: [], PREFERRED_HEADING: []}
    requirements = data.get("requirements")
    for item in requirements if isinstance(requirements, list) else []:
        found = _requirement_line(item)
        if found is not None and found[1] not in lines[found[0]]:
            lines[found[0]].append(found[1])
    description = _clean(data.get("jobDescription"))

    sections = [f"{heading}\n" + "\n".join(body) for heading, body in lines.items() if body]
    if description:
        sections.append(f"{DESCRIPTION_HEADING}\n{description}")
    text = "\n\n".join(sections)[:settings.JOB_POSTING_TEXT_MAX].rstrip()
    if len(text) < settings.JOB_POSTING_TEXT_MIN:
        return None
    return {"title": _clean(data.get("title"), settings.JOB_POSTING_TITLE_MAX),
            "company": _clean(data.get("organization"), settings.JOB_POSTING_COMPANY_MAX),
            "text": text}
