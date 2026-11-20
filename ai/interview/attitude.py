"""태도 측정 measure_attitude (camera design §6, Requirement 4, 노션 6-③).

코드로만 계산한다. AWS·LLM을 부르지 않고 같은 입력이면 같은 결과다.
- 답변 중 캡처(type=ANSWER, accepted=true, valid=true)만 쓴다. 평가 불가 답변의 캡처도 쓴다 (camera 결정 4)
- 눈 감음은 확신도 eyes_closed_min_confidence 이상일 때만 뺀다 (★ 백엔드와의 약속: 판단은 점수 단계)
- 정면은 정면 보정 기준값(session.baseline) 대비로 본다. 기준값이 없으면 태도 미측정 (C §2.3 "정면 보정 필수")
- 형식이 어긋난 캡처는 그 캡처만 뺀다 (camera 결정 5)
로그에는 사유 코드와 캡처 개수만 남긴다. 각도와 비율은 남기지 않는다.
"""

import logging
import time
from collections import defaultdict

from pydantic import ValidationError

from .config import AttitudeConfig, ScoringConfig
from .models import AttitudeResult, Baseline, Frame, QuestionFrontal, Session

logger = logging.getLogger("interview")

STAGE = "measure_attitude"

CAMERA_NOT_USED = "CAMERA_NOT_USED"
CALIBRATION_FAILED = "CALIBRATION_FAILED"
NOT_ENOUGH_FRAMES = "NOT_ENOUGH_FRAMES"

FOLLOW_UP_SUFFIX = "-f"


def parse_frames(frames) -> tuple[list[Frame], int]:
    """검사를 통과한 캡처와, 형식이 어긋나 뺀 캡처 수."""
    parsed, bad = [], 0
    for item in frames if isinstance(frames, list) else []:
        try:
            parsed.append(Frame.model_validate(item))
        except ValidationError:
            bad += 1
    return parsed, bad


def eyes_closed(frame: Frame, cfg: AttitudeConfig) -> bool:
    eyes = frame.eyes_open
    return eyes is not None and eyes.value is False and eyes.confidence >= cfg.eyes_closed_min_confidence


def _within(value: float, base: float, limit: float) -> bool:
    # 15 - 0이 15.000000000000002처럼 되는 부동소수 오차로 경계값이 뒤집히지 않게 자른다
    return round(abs(value - base), 6) <= limit


def is_frontal(frame: Frame, baseline: Baseline, cfg: AttitudeConfig) -> bool:
    """기준값 대비 시선 좌우 ±gaze_yaw_limit, 위아래 ±gaze_pitch_limit, 고개 좌우·위아래 ±head_angle_limit (경계 포함)."""
    gaze, head = frame.gaze, frame.head
    return (_within(gaze.yaw, baseline.gaze.yaw, cfg.gaze_yaw_limit)
            and _within(gaze.pitch, baseline.gaze.pitch, cfg.gaze_pitch_limit)
            and _within(head.yaw, baseline.head.yaw, cfg.head_angle_limit)
            and _within(head.pitch, baseline.head.pitch, cfg.head_angle_limit))


def attitude_points(ratio: float, cfg: AttitudeConfig) -> float:
    """정면 응시 비율(%) → 태도 점수. frontal_full_min 이상 100, frontal_zero_max 이하 0, 사이는 직선."""
    if ratio >= cfg.frontal_full_min:
        return 100.0
    if ratio <= cfg.frontal_zero_max:
        return 0.0
    return (ratio - cfg.frontal_zero_max) / (cfg.frontal_full_min - cfg.frontal_zero_max) * 100


def _not_measured(reason: str, used: int = 0) -> AttitudeResult:
    return AttitudeResult(score=None, reason=reason, frontal_ratio=None, used_frames=used, frontal_frames=0)


def measure_attitude(session: Session, frames, config: ScoringConfig) -> AttitudeResult:
    started = time.monotonic()
    cfg = config.attitude
    bad = closed = 0

    def log(result: AttitudeResult) -> AttitudeResult:
        logger.info("stage=%s reason=%s usedFrames=%d eyesClosed=%d badFrames=%d durationMs=%d", STAGE,
                    result.reason or "none", result.used_frames, closed, bad, int((time.monotonic() - started) * 1000))
        return result

    if not session.camera_consent:
        return log(_not_measured(CAMERA_NOT_USED))
    if session.baseline is None:
        return log(_not_measured(CALIBRATION_FAILED))

    # 답변 ID → 기본 질문 ID (q1-f의 답변도 q1 묶음)
    bundle_of = {a.answer_id: a.question_id.removesuffix(FOLLOW_UP_SUFFIX) for a in session.answers}
    parsed, bad = parse_frames(frames)
    used: list[tuple[str, Frame]] = []
    for frame in parsed:
        if frame.type != "ANSWER" or not frame.accepted or not frame.valid or frame.answer_id not in bundle_of:
            continue
        if eyes_closed(frame, cfg):
            closed += 1
            continue
        used.append((bundle_of[frame.answer_id], frame))

    if len(used) < cfg.min_valid_count:
        return log(_not_measured(NOT_ENOUGH_FRAMES, len(used)))

    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # 질문 ID → [정면, 전체]
    for question_id, frame in used:
        counts[question_id][1] += 1
        if is_frontal(frame, session.baseline, cfg):
            counts[question_id][0] += 1
    frontal = sum(c[0] for c in counts.values())
    ratio = frontal * 100 / len(used)
    order = [q.question_id for q in session.questions]
    by_question = tuple(QuestionFrontal(question_id=q, frontal_ratio=counts[q][0] * 100 / counts[q][1])
                        for q in order if q in counts)
    return log(AttitudeResult(score=attitude_points(ratio, cfg), reason=None, frontal_ratio=ratio,
                              used_frames=len(used), frontal_frames=frontal, by_question=by_question))
