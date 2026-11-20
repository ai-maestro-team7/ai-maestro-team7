"""설정 파일 `supervisor_config.json`을 읽고 검사한다 (개발계획서4 §11). 숫자를 코드에 박지 않는다."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

CONFIG_PATH = Path(__file__).with_name("supervisor_config.json")


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


class ReplyLimits(_Model):
    max_chars: int = Field(gt=0)
    max_follow_ups: int = Field(ge=0)
    follow_up_max_chars: int = Field(gt=0)
    free_number_max: int = Field(ge=0)  # "공고 3개"처럼 개수를 말할 때 쓰는 작은 수는 대조하지 않는다


class CoverLetterLimits(_Model):
    min_chars: int = Field(gt=0)
    max_chars: int = Field(gt=0)


class Thinking(_Model):
    family: str
    thinking: dict


class SupervisorConfig(_Model):
    config_version: str
    prompt_version: str
    max_tokens: int = Field(gt=0)
    max_turns: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)
    history_messages: int = Field(ge=0)
    message_max_chars: int = Field(gt=0)
    max_attachments: int = Field(ge=0)
    max_messages_per_session: int = Field(ge=2)
    max_policies: int = Field(gt=0)
    stale_seconds: int = Field(gt=0)
    title_max_chars: int = Field(gt=0)
    reply: ReplyLimits
    cover_letter: CoverLetterLimits
    interview_job_max_chars: int = Field(gt=0)
    banned_phrases: tuple[str, ...]
    allowed_phrases: tuple[str, ...] = ()
    thinking_by_model: tuple[Thinking, ...] = ()

    @model_validator(mode="after")
    def _check(self):
        if self.cover_letter.min_chars > self.cover_letter.max_chars:
            raise ValueError("coverLetter.minChars가 maxChars보다 커요")
        if any(not p.strip() for p in self.banned_phrases):
            raise ValueError("bannedPhrases에 빈 값이 있어요")
        return self

    def thinking_for(self, model_id: str) -> dict | None:
        """모델에 맞는 '생각 끄기' 값. 표에 없는 모델은 None (요청에 넣지 않는다)."""
        for item in self.thinking_by_model:
            if item.family in model_id:
                return dict(item.thinking)
        return None


def load_config(path: Path = CONFIG_PATH) -> SupervisorConfig:
    """읽을 때 검사하고, 어긋나면 ValidationError로 멈춘다."""
    return SupervisorConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def get_config() -> SupervisorConfig:
    return load_config()
