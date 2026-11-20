"""점수 계산 (report design §5, requirements Requirement 3).

코드로만 계산한다. AWS·LLM을 부르지 않고, 같은 입력이면 같은 결과다 (C §2.3, 노션 6 "핵심 원칙").
미측정은 0점으로 넣지 않고 뺀다. 기준값은 모두 설정 파일(config/scoring_v1.json)에서 읽는다.

내용 항목 점수(1~5)는 C-1이 매기고 여기서는 환산·평균만 한다.
태도는 4차(#108)부터 measure_attitude(정면 응시 비율)로 계산한다. 미측정이면 종합 비율에서 뺀다.
"""

import logging
import time
from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean

from . import settings
from .attitude import measure_attitude
from .bundles import Bundle, make_bundles
from .config import AREAS, LongPauseConfig, ScoringConfig, SpeechRateConfig, TimeManagementConfig
from .models import AnswerRecord, Areas, AreaScore, BundleScore, ContentEvaluation, DeliveryMetrics, ScoreResult, Session

logger = logging.getLogger("interview")

STAGE = "calculate_interview_scores"

AREA_LABELS = {"content": "내용", "delivery": "전달력", "attitude": "태도"}

# 미측정 사유 → 리포트 안내 문장 (코드가 정한 틀, report design §5)
NOT_MEASURED_MESSAGES = {
    "CAMERA_NOT_USED": "카메라를 사용하지 않아 태도는 제외했어요.",
    "CALIBRATION_FAILED": "정면 보정이 되지 않아 태도는 제외했어요.",
    "NOT_ENOUGH_FRAMES": "얼굴이 확인된 캡처가 적어 태도는 제외했어요.",
    "NOT_ENOUGH_SPEECH": "말한 시간이 짧거나 숫자·영어가 많아 전달력은 제외했어요.",
}


def round_half_up(value: float) -> int:
    """표시용 정수 반올림 (0.5는 올림). Python round는 짝수 쪽으로 반올림해서 쓰지 않는다."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- 전달력 변환 (노션 6-②)


def time_points(time_limit_reached: bool, cfg: TimeManagementConfig) -> float:
    return cfg.at_limit if time_limit_reached else cfg.before_limit


def speech_rate_points(rate: float, cfg: SpeechRateConfig) -> float:
    """full 구간이면 배점, half 값 이하·이상이면 배점의 절반, 그 사이는 직선."""
    full_lo, full_hi = cfg.full
    half_lo, half_hi = cfg.half
    top, floor = cfg.weight, cfg.weight / 2
    if full_lo <= rate <= full_hi:
        return top
    if rate <= half_lo or rate >= half_hi:
        return floor
    if rate < full_lo:
        return floor + (rate - half_lo) / (full_lo - half_lo) * (top - floor)
    return top - (rate - full_hi) / (half_hi - full_hi) * (top - floor)


def long_pause_points(per_min: float, cfg: LongPauseConfig) -> float:
    """분당 full_max 이하면 배점, zero_min 이상이면 0, 그 사이는 직선."""
    if per_min <= cfg.full_max:
        return cfg.weight
    if per_min >= cfg.zero_min:
        return 0.0
    return cfg.weight * (cfg.zero_min - per_min) / (cfg.zero_min - cfg.full_max)


def answer_delivery_score(record: AnswerRecord, config: ScoringConfig) -> float | None:
    """답변 하나의 전달력 = 획득 점수 합 ÷ 측정된 항목 배점 합 × 100.

    발화 속도와 긴 침묵이 둘 다 미측정이거나 측정값이 없으면(1차 Session) None.
    시간 관리만으로는 점수를 내지 않는다 (노션 6-②).
    """
    delivery: DeliveryMetrics | None = record.delivery
    if delivery is None:
        return None
    d = config.delivery
    earned = possible = 0.0
    measured_speech = False
    if d.speech_rate.enabled and delivery.speech_rate is not None:
        earned += speech_rate_points(delivery.speech_rate, d.speech_rate)
        possible += d.speech_rate.weight
        measured_speech = True
    if d.long_pause_per_min.enabled and delivery.long_pause_per_min is not None:
        earned += long_pause_points(delivery.long_pause_per_min, d.long_pause_per_min)
        possible += d.long_pause_per_min.weight
        measured_speech = True
    if not measured_speech:
        return None
    if d.time_management.enabled:
        earned += time_points(record.time_limit_reached, d.time_management)
        possible += d.time_management.weight
    return earned / possible * 100


def _bundle_delivery(bundle: Bundle, config: ScoringConfig) -> float | None:
    scores = [s for s in (answer_delivery_score(r, config) for r in bundle.answer_records()) if s is not None]
    return fmean(scores) if scores else None


# ---------------------------------------------------------------- 문장 (코드가 만든다)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def weight_basis(weights: dict[str, float], evaluated: int) -> str:
    text = " · ".join(f"{AREA_LABELS[a]} {_number(weights[a])}%" for a in AREAS if a in weights) + " 기준"
    if evaluated < settings.BASE_QUESTION_COUNT:
        text += f" · 평가 가능한 기본 질문 {evaluated}/{settings.BASE_QUESTION_COUNT}개 기준"
    return text


# ---------------------------------------------------------------- 공개 함수


def evaluable_bundles(session: Session) -> list[Bundle]:
    return [b for b in make_bundles(session) if b.evaluable]


def calculate_interview_scores(session: Session, frames: list, config: ScoringConfig,
                               content: dict[str, ContentEvaluation]) -> ScoreResult:
    """영역별·종합 점수, 등급, 미측정 사유 (requirements 결정 5: content는 C-1 결과, 기본 질문 ID → 평가).

    평가 가능한 묶음이 0개면 부르지 않는다 (generate_report가 점수 없는 리포트를 만든다).
    """
    started = time.monotonic()
    bundles = evaluable_bundles(session)
    if not bundles:
        raise ValueError("no evaluable bundle")
    if set(content) != {b.question_id for b in bundles}:
        raise ValueError("content evaluations must match evaluable bundles")

    bundle_scores, content_scores, delivery_scores = [], [], []
    for b in bundles:
        c = content[b.question_id].raw_score
        dl = _bundle_delivery(b, config)
        content_scores.append(c)
        if dl is not None:
            delivery_scores.append(dl)
        bundle_scores.append(BundleScore(question_id=b.question_id, content_score=round_half_up(c),
                                         delivery_score=round(dl, 1) if dl is not None else None))

    raw = {"content": fmean(content_scores)}
    reasons: dict[str, str] = {}
    if delivery_scores:
        raw["delivery"] = fmean(delivery_scores)
    else:
        reasons["delivery"] = "NOT_ENOUGH_SPEECH"
    attitude = measure_attitude(session, frames, config)
    if attitude.score is not None:
        raw["attitude"] = attitude.score
    else:
        reasons["attitude"] = attitude.reason

    weights = config.total_weights.for_areas(set(raw))
    total = sum(raw[a] * weights[a] for a in raw) / 100
    total_display = round_half_up(total)

    areas = Areas(**{a: AreaScore(score=round_half_up(raw[a]) if a in raw else None,
                                  not_measured_reason=reasons.get(a)) for a in AREAS})
    result = ScoreResult(
        total_score=total_display,
        grade=config.grade_for(total_display),  # 등급은 화면에 보이는 반올림 점수로
        weight_basis=weight_basis(weights, len(bundles)),
        areas=areas,
        not_measured_messages=tuple(NOT_MEASURED_MESSAGES[reasons[a]] for a in AREAS if a in reasons),
        evaluated_base_questions=len(bundles),
        bundles=tuple(bundle_scores),
        frontal_ratios=attitude.by_question,
    )
    logger.info("stage=%s bundles=%d measured=%s durationMs=%d", STAGE, len(bundles),
                ",".join(sorted(raw)), int((time.monotonic() - started) * 1000))
    return result
