"""내용 평가 evaluate_content (프롬프트 C-1, report design §4, Requirement 2).

묶음(기본 질문 + 꼬리질문) 하나를 질문 유형별 4개 항목 × 1~5점으로 평가한다 (노션 6-① 평가표).
- 점수는 LLM이 매기고, 환산·평균은 scoring.py가 한다.
- 근거 인용(quote)은 실제 답변에 있는지 대조하고, 없으면 근거로 쓰지 않는다 (AGENTS.md "AI·데이터 규칙").
- 평가표 문장을 바꾸면 versions.PROMPT_C1_VERSION을 올린다.
"""

import logging
from typing import ClassVar, Literal

from pydantic import Field, field_validator, model_validator

from . import llm as llm_module
from . import prompting
from .bundles import Bundle
from .models import ContentEvaluation, ContentItem, _LLMOutputModel

logger = logging.getLogger("interview")

STAGE = "evaluate_content"

# 평가표 항목 키 (출력 검사용). 순서는 리포트 표시 순서
RUBRIC_KEYS: dict[str, tuple[str, ...]] = {
    "experience": ("relevance", "specificity", "structure", "outcome"),
    "knowledge": ("accuracy", "relevance", "logic", "support"),
    "situation": ("understanding", "reasoning", "process", "alternatives"),
}

# 노션 "AI 모의면접 에이전트 기능" 6-① 평가표 (1점 / 3점 / 5점 기준)
_RUBRIC_ROWS: dict[str, tuple[tuple[str, str, str, str, str], ...]] = {
    "experience": (
        ("relevance", "질문 관련성", "질문과 다른 이야기", "관련 있지만 일부 벗어남", "질문에 정확히 답함"),
        ("specificity", "행동의 구체성", '"열심히 했다" 수준', "행동이 있지만 두루뭉술", "내가 한 행동이 구체적으로 드러남"),
        ("structure", "설명 구조", "순서 없이 나열", "흐름은 있지만 일부 빠짐", "상황 → 행동 → 결과가 명확"),
        ("outcome", "결과·배운 점", "언급 없음", "결과나 배운 점 중 하나만", "결과와 배운 점이 모두 드러남"),
    ),
    "knowledge": (
        ("accuracy", "정확성", "틀린 내용이 중심", "대체로 맞지만 부정확한 부분", "내용이 정확함"),
        ("relevance", "질문 관련성", "질문과 다른 이야기", "관련 있지만 일부 벗어남", "질문에 정확히 답함"),
        ("logic", "논리성", "근거 없이 주장", "근거가 약함", "이유와 근거가 명확"),
        ("support", "근거·예시", "예시 없음", "일반적인 예시", "본인 경험이나 구체적 예시"),
    ),
    "situation": (
        ("understanding", "문제 이해", "상황을 잘못 이해", "핵심을 일부만 파악", "문제의 핵심을 정확히 파악"),
        ("reasoning", "판단 근거", "이유 없이 결정", "이유가 약함", "판단 이유가 명확"),
        ("process", "해결 과정", "해결 방법이 모호", "방법은 있지만 단계가 부족", "구체적인 단계로 설명"),
        ("alternatives", "대안·한계 고려", "고려 없음", "일부 언급", "다른 방법이나 위험까지 고려"),
    ),
}

EVIDENCE_MAX = 150
_QUOTE_CHARS = "\"'“”‘’「」"


def rubric_text(question_type: str) -> str:
    lines = ["| key | 항목 | 1점 | 3점 | 5점 |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {k} | {name} | {one} | {three} | {five} |" for k, name, one, three, five in _RUBRIC_ROWS[question_type]]
    return "\n".join(lines)


# ---------------------------------------------------------------- LLM 출력


class ContentItemOutput(_LLMOutputModel):
    key: str
    score: int = Field(ge=1, le=5)
    evidence_type: Literal["quote", "missing"]
    evidence: str

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= EVIDENCE_MAX:
            raise ValueError("length")
        return value


class _ContentOutput(_LLMOutputModel):
    EXPECTED: ClassVar[tuple[str, ...]] = ()
    items: list[ContentItemOutput]

    @model_validator(mode="after")
    def _keys(self) -> "_ContentOutput":
        keys = [i.key for i in self.items]
        if len(keys) != len(self.EXPECTED) or set(keys) != set(self.EXPECTED):
            raise ValueError("rubric keys")
        return self


class ExperienceOutput(_ContentOutput):
    EXPECTED = RUBRIC_KEYS["experience"]


class KnowledgeOutput(_ContentOutput):
    EXPECTED = RUBRIC_KEYS["knowledge"]


class SituationOutput(_ContentOutput):
    EXPECTED = RUBRIC_KEYS["situation"]


OUTPUT_MODELS: dict[str, type[_ContentOutput]] = {
    "experience": ExperienceOutput, "knowledge": KnowledgeOutput, "situation": SituationOutput,
}


# ---------------------------------------------------------------- 근거 대조


def _normalize(text: str) -> str:
    return " ".join(text.split())


def quote_in_answer(quote: str, answer_text: str) -> bool:
    """인용이 답변에 실제로 있는지 (공백 정규화, 앞뒤 따옴표·마침표 무시, 부분 문자열)."""
    q = _normalize(quote.strip().strip(_QUOTE_CHARS).rstrip(".…").strip())
    return bool(q) and q in _normalize(answer_text)


# ---------------------------------------------------------------- 공개 함수


def evaluate_content(job: str, resume_text: str, bundle: Bundle, *, llm=None) -> ContentEvaluation:
    if not bundle.evaluable:
        raise ValueError("bundle is not evaluable")
    qtype = bundle.question.question_type
    follow_up = bundle.follow_up if bundle.follow_up is not None and bundle.follow_up.evaluable else None
    client = llm if llm is not None else llm_module.default_client()
    output = llm_module.call_json(
        client,
        system_prompt=prompting.eval_system_prompt(),
        user_prompt=prompting.content_prompt(
            job, resume_text, qtype, bundle.base.question, bundle.base.answer_text or "",
            follow_up.question if follow_up else "", (follow_up.answer_text or "") if follow_up else "",
            rubric_text(qtype)),
        schema=OUTPUT_MODELS[qtype],
        stage=STAGE,
    )

    answers = bundle.answer_text()
    by_key = {i.key: i for i in output.items}
    items, unverified = [], 0
    for key in RUBRIC_KEYS[qtype]:
        out = by_key[key]
        verified = out.evidence_type == "missing" or quote_in_answer(out.evidence, answers)
        if not verified:
            unverified += 1
        items.append(ContentItem(key=key, score=out.score, evidence_type=out.evidence_type,
                                 evidence=out.evidence if verified else None, evidence_verified=verified))
    if unverified:
        logger.info("stage=%s questionId=%s unverifiedEvidence=%d", STAGE, bundle.question_id, unverified)
    return ContentEvaluation(question_id=bundle.question_id, question_type=qtype, items=tuple(items))
