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


class MentoringConfig(_ConfigModel):
    config_version: str
    document: DocumentConfig
    extraction: ExtractionConfig
    confirmation: ConfirmationConfig
    idempotency: IdempotencyConfig


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
