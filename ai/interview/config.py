"""점수 설정 파일 읽기 (voice design §9, Requirement 6).

`config/scoring_v1.json`을 프로세스에서 한 번 읽는다. 2차는 전달력(delivery) 기준만 엄격하게 검사하고,
나머지 키는 그대로 보관한다 (3차 점수 계산이 채운다).

기준값 출처:
- 가중치 시간 관리 10·발화 속도 30·긴 침묵 30: docs/개발계획서3.md §4.3
- 15초 미만 답변은 발화 속도·침묵 미측정: §7 품질 검증 표
- 숫자·영문 비율 0.2, 긴 침묵 2초, full_max·zero_min: 노션 "AI 모의면접 에이전트 기능" 6-②·6-⑤ (저장소에 없음)
- model_id 키는 두지 않는다 (모델은 환경변수 MODEL_ID만, 1차 결정 5)
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import settings
from .errors import AWS_SERVICE_ERROR, InterviewError
from .versions import SCORING_VERSION

logger = logging.getLogger("interview")

CONFIG_DIR = Path(__file__).resolve().parent / "config"
SCORING_CONFIG_PATH = CONFIG_DIR / "scoring_v1.json"
STAGE = "load_scoring_config"


class _Item(BaseModel):
    # 3차에서 점수 환산 값(구간 등)을 더할 수 있게 모르는 키는 보관한다
    model_config = ConfigDict(extra="allow")

    enabled: bool
    weight: float = Field(ge=0)


class TimeManagementConfig(_Item):
    pass


class SpeechRateConfig(_Item):
    min_answer_sec: float = Field(gt=0)
    max_non_hangul_ratio: float = Field(gt=0, le=1)


class LongPauseConfig(_Item):
    full_max: float = Field(ge=0)
    zero_min: float = Field(gt=0)
    min_answer_sec: float = Field(gt=0)
    long_pause_sec: float = Field(gt=0)

    @model_validator(mode="after")
    def _range(self) -> "LongPauseConfig":
        if self.full_max >= self.zero_min:
            raise ValueError("full_max must be below zero_min")
        return self


class DeliveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_management: TimeManagementConfig
    speech_rate: SpeechRateConfig
    long_pause_per_min: LongPauseConfig


class ScoringConfig(BaseModel):
    # content·attitude·total 등은 3차에서 검사를 더한다. 지금은 그대로 보관한다
    model_config = ConfigDict(extra="allow")

    scoring_version: str
    delivery: DeliveryConfig

    @model_validator(mode="after")
    def _version(self) -> "ScoringConfig":
        if self.scoring_version != SCORING_VERSION:
            raise ValueError("scoring_version mismatch")
        if "model_id" in (self.model_extra or {}):
            raise ValueError("model_id must come from MODEL_ID")
        return self


def _config_error(reason: str) -> InterviewError:
    logger.error("stage=%s errorCode=%s reason=%s", STAGE, AWS_SERVICE_ERROR, reason)
    return InterviewError(AWS_SERVICE_ERROR, settings.CONFIG_ERROR_MESSAGE, retryable=False)


def read_scoring_config(path: Path) -> ScoringConfig:
    """설정 파일 하나를 읽고 검사한다. 실패하면 AWS_SERVICE_ERROR(retryable false)."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _config_error("missing") from None
    except (OSError, ValueError):
        raise _config_error("unreadable") from None
    try:
        return ScoringConfig.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "(root)"
                         for e in exc.errors(include_input=False, include_url=False)})
        raise _config_error("invalid:" + ",".join(fields)) from None


@lru_cache(maxsize=1)
def load_scoring_config() -> ScoringConfig:
    """배포 묶음의 config/scoring_v1.json. 프로세스에서 한 번만 읽는다."""
    return read_scoring_config(SCORING_CONFIG_PATH)
