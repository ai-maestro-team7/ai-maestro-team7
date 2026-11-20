"""전달력 측정 (voice design §7, Requirement 4).

Transcribe 결과(문장과 단어별 시간)로 발화 속도와 분당 긴 침묵을 잰다. 점수 환산은 하지 않는다 (3차).
AWS를 부르지 않는 순수 함수다. 기준값은 config/scoring_v1.json에서 받는다.
"""

from collections.abc import Sequence
from itertools import pairwise

from .config import DeliveryConfig
from .models import DeliveryMetrics, Word

TOO_SHORT = "TOO_SHORT"
NON_HANGUL_HEAVY = "NON_HANGUL_HEAVY"

_HANGUL_FIRST, _HANGUL_LAST = "\uac00", "\ud7a3"  # 한글 음절 U+AC00~U+D7A3
_PER_MIN = 60
_TIME_DIGITS = 3


def _is_hangul_syllable(ch: str) -> bool:
    return _HANGUL_FIRST <= ch <= _HANGUL_LAST


def _is_digit_or_latin(ch: str) -> bool:
    return ch.isdigit() or (ch.isascii() and ch.isalpha())


def speech_span(words: Sequence[Word]) -> float:
    """첫 단어 시작부터 마지막 단어 끝까지의 초 (Speech_Span). 단어가 없으면 0."""
    if not words:
        return 0.0
    return max(0.0, words[-1].end - words[0].start)


def non_hangul_ratio(text: str) -> float:
    """숫자·영문 글자 수 ÷ 공백·문장부호를 뺀 글자 수. 셀 글자가 없으면 0."""
    chars = [ch for ch in text if ch.isalnum()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if _is_digit_or_latin(ch)) / len(chars)


def measure_delivery(text: str, words: Sequence[Word], config: DeliveryConfig) -> DeliveryMetrics:
    span = speech_span(words)
    rate_cfg, pause_cfg = config.speech_rate, config.long_pause_per_min

    speech_rate, speech_rate_reason = None, None
    if span < rate_cfg.min_answer_sec:
        speech_rate_reason = TOO_SHORT
    elif non_hangul_ratio(text) >= rate_cfg.max_non_hangul_ratio:
        speech_rate_reason = NON_HANGUL_HEAVY
    else:
        syllables = sum(1 for ch in text if _is_hangul_syllable(ch))
        speech_rate = round(syllables / span * _PER_MIN, 1)

    pause_count, pause_per_min, pause_reason = None, None, None
    if span < pause_cfg.min_answer_sec:
        pause_reason = TOO_SHORT
    else:
        # Transcribe 시각은 소수 셋째 자리까지라 같은 자리로 맞춰 비교한다 (3.1 - 1.1 = 1.9999… 같은 오차 방지)
        pause_count = sum(1 for a, b in pairwise(words)
                          if round(b.start - a.end, _TIME_DIGITS) >= pause_cfg.long_pause_sec)
        pause_per_min = round(pause_count / span * _PER_MIN, 2)

    return DeliveryMetrics(
        answer_sec=round(span, 1), speech_rate=speech_rate, speech_rate_reason=speech_rate_reason,
        long_pause_count=pause_count, long_pause_per_min=pause_per_min, long_pause_reason=pause_reason,
    )
