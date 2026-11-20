"""A 설정. 숫자(한도, 재시도 횟수)는 `mentoring_config.json`에서만 읽는다 (AGENTS.md "코딩 규칙").

자원 이름과 모델 ID는 이 파일이 아니라 환경변수로 받는다. `require_env`는 값이 없으면 이름을 담아 멈추고
기본값으로 대신하지 않는다 (Requirement 1 기준 5).
"""
import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

CONFIG_PATH = Path(__file__).with_name("mentoring_config.json")


class _ConfigModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


class DocumentConfig(_ConfigModel):
    text_min_chars: int = Field(ge=1)
    text_max_chars: int = Field(ge=1)
    title_max_chars: int = Field(ge=1)

    @model_validator(mode="after")
    def _range(self):
        if self.text_min_chars > self.text_max_chars:
            raise ValueError("document.textMinChars는 textMaxChars보다 클 수 없다")
        return self


class ExtractionConfig(_ConfigModel):
    prompt_version: str = Field(min_length=1)
    max_tokens: int = Field(ge=256)
    schema_retries: int = Field(ge=0, le=2)  # 형식 검사 실패 뒤 다시 요청하는 횟수 (tech.md "재시도 1회")
    fact_retries: int = Field(ge=0, le=2)    # 원문에 없는 사실을 고쳐 달라고 다시 요청하는 횟수 (A F-01 10단계)


class ConfirmationConfig(_ConfigModel):
    max_additions: int = Field(ge=0)
    name_max_chars: int = Field(ge=1)


class IdempotencyConfig(_ConfigModel):
    ttl_hours: int = Field(ge=1)
    key_max_chars: int = Field(ge=1)


class UploadConfig(_ConfigModel):
    """PDF 업로드 한도. 개발계획서1 F-01의 10MB·20페이지는 예시 값이다 (Requirement 3 기준 2)."""
    allowed_content_types: list[str] = Field(min_length=1)
    max_bytes: int = Field(ge=1)
    max_pages: int = Field(ge=1)
    presign_expires_seconds: int = Field(ge=30, le=3600)
    file_name_max_chars: int = Field(ge=1)


class MetricsConfig(_ConfigModel):
    namespace: str = Field(min_length=1)


class JobFitConfig(_ConfigModel):
    """직무 적합도 분석 (개발계획서1 F-02, mentoring-fit-review-learning Requirement 2~8).
    점수 가중치·근거 단계 값은 `fit/fit_config.json`에 따로 있다."""
    link_prompt_version: str = Field(min_length=1)
    summary_prompt_version: str = Field(min_length=1)
    link_max_tokens: int = Field(ge=256)
    summary_max_tokens: int = Field(ge=64)
    schema_retries: int = Field(ge=0, le=2)
    summary_retries: int = Field(ge=0, le=2)
    max_requirements: int = Field(ge=1)
    max_profile_skills: int = Field(ge=1)
    kb_top_k: int = Field(ge=1, le=10)
    citation_excerpt_chars: int = Field(ge=0)
    question_max_chars: int = Field(ge=1)
    summary_max_chars: int = Field(ge=1)
    banned_summary_patterns: list[str] = Field(min_length=1)  # 정규식. 합격 확률처럼 보이는 표현 (Requirement 5 기준 8)
    notice: str = Field(min_length=1)  # "적합도는 실제 합격 확률이 아닙니다" (docs/api.md §6.3)


class ReviewConfig(_ConfigModel):
    """자기소개서·이력서 첨삭 (개발계획서1 F-03, mentoring-fit-review-learning Requirement 9~11)."""
    prompt_version: str = Field(min_length=1)
    max_tokens: int = Field(ge=256)
    schema_retries: int = Field(ge=0, le=2)
    text_min_chars: int = Field(ge=1)
    text_max_chars: int = Field(ge=1)
    question_max_chars: int = Field(ge=1)
    max_characters_limit: int = Field(ge=1)  # 요청 maxCharacters의 상한
    max_issues: int = Field(ge=1)
    max_questions: int = Field(ge=1, le=3)   # STAR가 빠졌을 때 묻는 확인 질문 수 (패키지 03 절차 4)
    max_stories: int = Field(ge=0)
    intents: list[str] = Field(min_length=1)       # 문항 의도 (F-03 처리 3단계)
    issue_types: list[str] = Field(min_length=1)
    blind_risk_patterns: list[str] = Field(default_factory=list)  # 직무와 무관한 개인정보 (F-03 "블라인드 공채")


class LearningConfig(_ConfigModel):
    """학습·자격 경로 (개발계획서1 F-05, mentoring-fit-review-learning Requirement 12~14)."""
    prompt_version: str = Field(min_length=1)
    max_tokens: int = Field(ge=256)
    schema_retries: int = Field(ge=0, le=2)
    default_weeks: int = Field(ge=1)
    min_weeks: int = Field(ge=1)
    max_weeks: int = Field(ge=1)
    max_targets: int = Field(ge=1)
    max_units_per_posting: int = Field(ge=0)
    max_certificates: int = Field(ge=0)
    exam_lookahead_years: int = Field(ge=0, le=2)
    exam_date_fields: dict[str, str] = Field(min_length=1)  # 공단 시험일정 원본 칸 → 우리 칸 (#95 수집 형식)
    exam_guide_url: str = Field(min_length=1)               # 일정을 확인하지 못했을 때 붙이는 공식 안내
    policy_wallet_path: str = Field(min_length=1)           # 부산 청년정책은 B 정책 지갑으로 안내 (M-10)

    @model_validator(mode="after")
    def _weeks(self):
        if not self.min_weeks <= self.default_weeks <= self.max_weeks:
            raise ValueError("learning: minWeeks ≤ defaultWeeks ≤ maxWeeks 이어야 한다")
        return self


class MentoringConfig(_ConfigModel):
    config_version: str
    document: DocumentConfig
    extraction: ExtractionConfig
    confirmation: ConfirmationConfig
    idempotency: IdempotencyConfig
    upload: UploadConfig
    metrics: MetricsConfig
    job_fit: JobFitConfig
    review: ReviewConfig
    learning: LearningConfig


def load_config(path: Path | str | None = None, *, data: dict | None = None) -> MentoringConfig:
    """설정을 읽고 검사한다. 테스트는 data로 값을 바꿔 넣는다."""
    if data is None:
        data = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    return MentoringConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_config() -> MentoringConfig:
    return load_config()


class MissingEnvError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingEnvError(f"환경변수 {name}가 없다")
    return value
