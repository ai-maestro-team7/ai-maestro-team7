"""점수 설정 파일 읽기 (voice design §9, report design §8, camera design §3).

`config/scoring_v2.json`을 프로세스에서 한 번 읽고 검사한다. 모르는 키는 보관만 한다.
v1.0 파일(scoring_v1.json)은 3차 머지 뒤 바꾸지 않았다. 4차(#108)에서 분석 제외 기준(face_check)을 더하며
v2.0 파일을 새로 만들었다 (report 결정 2). v1 파일은 기록으로만 남고 읽지 않는다.

기준값 출처:
- 가중치 시간 관리 10·발화 속도 30·긴 침묵 30, 종합 50/25/25: docs/개발계획서3.md §4.3
- 15초 미만 답변은 발화 속도·침묵 미측정, 2분 초과 8점: §7 품질 검증 표
- 나머지(숫자·영문 비율 0.2, 긴 침묵 2초, 속도 구간, 침묵 구간, 태도 기준, 종합 비율, 등급):
  노션 "AI 모의면접 에이전트 기능" 6-②~⑤ (저장소에 없음). 등급은 노션 표의 값을 설정 파일로 옮겼다
- face_check(얼굴 신뢰도, 시선 신뢰도, 가림, 밝기, 선명도): 노션에 없는 제안값. 수동 확인으로 맞춘다 (camera 결정 1)
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
SCORING_CONFIG_PATH = CONFIG_DIR / "scoring_v2.json"
STAGE = "load_scoring_config"


class _Item(BaseModel):
    # 3차에서 점수 환산 값(구간 등)을 더할 수 있게 모르는 키는 보관한다
    model_config = ConfigDict(extra="allow")

    enabled: bool
    weight: float = Field(ge=0)


class TimeManagementConfig(_Item):
    before_limit: float = Field(ge=0)  # 제한 전에 제출
    at_limit: float = Field(ge=0)      # 시간 제한 도달 (자동 제출)

    @model_validator(mode="after")
    def _within_weight(self) -> "TimeManagementConfig":
        if self.before_limit > self.weight or self.at_limit > self.before_limit:
            raise ValueError("at_limit <= before_limit <= weight")
        return self


class SpeechRateConfig(_Item):
    full: tuple[float, float]   # 이 구간이면 만점
    half: tuple[float, float]   # 이 값 이하·이상이면 배점의 절반, full과의 사이는 직선
    min_answer_sec: float = Field(gt=0)
    max_non_hangul_ratio: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _ranges(self) -> "SpeechRateConfig":
        if not self.half[0] < self.full[0] <= self.full[1] < self.half[1]:
            raise ValueError("half[0] < full[0] <= full[1] < half[1]")
        return self


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


class AttitudeConfig(BaseModel):
    """태도 기준 (노션 6-③). measure_attitude·compute_baseline이 쓴다 (4차)."""

    model_config = ConfigDict(extra="forbid")

    gaze_yaw_limit: float = Field(gt=0)
    gaze_pitch_limit: float = Field(gt=0)
    head_angle_limit: float = Field(gt=0)
    eyes_closed_min_confidence: float = Field(gt=0, le=100)
    frontal_full_min: float = Field(gt=0, le=100)
    frontal_zero_max: float = Field(ge=0, le=100)
    min_valid_count: int = Field(gt=0)
    calibration_min_valid: int = Field(gt=0)

    @model_validator(mode="after")
    def _range(self) -> "AttitudeConfig":
        if self.frontal_zero_max >= self.frontal_full_min:
            raise ValueError("frontal_zero_max must be below frontal_full_min")
        return self


class FaceCheckConfig(BaseModel):
    """analyze_face의 분석 제외 기준 (camera design §3). Rekognition 값은 모두 0~100이다."""

    model_config = ConfigDict(extra="forbid")

    min_face_confidence: float = Field(gt=0, le=100)           # 얼굴 신뢰도. 미달 얼굴은 "여러 명"으로도 세지 않는다
    min_eye_direction_confidence: float = Field(gt=0, le=100)  # 시선 신뢰도
    occluded_min_confidence: float = Field(gt=0, le=100)       # 가림이라고 할 때 필요한 확신도
    min_brightness: float = Field(gt=0, le=100)                # Quality.Brightness 미만이면 어두움
    min_sharpness: float = Field(gt=0, le=100)                 # Quality.Sharpness 미만이면 흐림


AREAS = ("content", "delivery", "attitude")

# 측정된 영역 → total_weights 키 (노션 6-④)
WEIGHT_KEYS = {
    frozenset({"content", "delivery", "attitude"}): "all",
    frozenset({"content", "delivery"}): "no_attitude",
    frozenset({"content", "attitude"}): "no_delivery",
    frozenset({"content"}): "content_only",
}


class TotalWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: dict[str, float]
    no_attitude: dict[str, float]
    no_delivery: dict[str, float]
    content_only: dict[str, float]

    @model_validator(mode="after")
    def _shape(self) -> "TotalWeights":
        for areas, key in WEIGHT_KEYS.items():
            weights = getattr(self, key)
            if set(weights) != areas:
                raise ValueError(f"{key} areas")
            if any(w <= 0 for w in weights.values()) or abs(sum(weights.values()) - 100) > 1e-9:
                raise ValueError(f"{key} must sum to 100")
        return self

    def for_areas(self, measured: set[str]) -> dict[str, float]:
        return getattr(self, WEIGHT_KEYS[frozenset(measured)])


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float = Field(ge=0, le=100)
    label: str = Field(min_length=1)


class ScoringConfig(BaseModel):
    # 모르는 키는 보관만 한다 (다음 단계에서 검사를 더할 수 있게)
    model_config = ConfigDict(extra="allow")

    scoring_version: str
    recording_limit_sec: int = Field(gt=0)
    delivery: DeliveryConfig
    attitude: AttitudeConfig
    face_check: FaceCheckConfig
    total_weights: TotalWeights
    grades: list[Grade] = Field(min_length=1)

    @model_validator(mode="after")
    def _version(self) -> "ScoringConfig":
        if self.scoring_version != SCORING_VERSION:
            raise ValueError("scoring_version mismatch")
        if "model_id" in (self.model_extra or {}):
            raise ValueError("model_id must come from MODEL_ID")
        mins = [g.min for g in self.grades]
        if mins != sorted(mins, reverse=True) or len(set(mins)) != len(mins) or mins[-1] != 0:
            raise ValueError("grades must be strictly descending and end at 0")
        return self

    def grade_for(self, score: float) -> str:
        """점수에 맞는 등급 (설정 파일 grades, 높은 기준부터)."""
        return next(g.label for g in self.grades if score >= g.min)


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
    """배포 묶음의 config/scoring_v2.json. 프로세스에서 한 번만 읽는다."""
    return read_scoring_config(SCORING_CONFIG_PATH)
