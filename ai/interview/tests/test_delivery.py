import json

import pytest

from interview.config import load_scoring_config, read_scoring_config
from interview.delivery import measure_delivery, non_hangul_ratio, speech_span
from interview.models import DeliveryMetrics, Word

CFG = load_scoring_config().delivery


def contiguous(seconds: float, step: float = 1.0) -> list[Word]:
    """0초부터 seconds초까지 빈틈없이 이어진 단어들."""
    n = round(seconds / step)
    return [Word(word="말", start=round(i * step, 3), end=round((i + 1) * step, 3)) for i in range(n)]


def with_gaps(gaps: list[float], total: float = 60.0) -> list[Word]:
    """0초에서 시작해 total초에 끝나고, 단어 사이 공백이 gaps인 단어들 (나머지 공백 0)."""
    words, t = [], 0.0
    speak = (total - sum(gaps)) / (len(gaps) + 1)
    for gap in gaps + [None]:
        words.append(Word(word="말", start=round(t, 3), end=round(t + speak, 3)))
        t += speak
        if gap is not None:
            t += gap
    return words


def measure(text, words, cfg=CFG):
    return measure_delivery(text, words, cfg)


def test_speech_rate_300_syllables_per_minute():
    m = measure("가" * 300, contiguous(60))
    assert m.answer_sec == 60.0 and m.speech_rate == 300.0 and m.speech_rate_reason is None
    assert m.long_pause_count == 0 and m.long_pause_per_min == 0.0 and m.long_pause_reason is None


def test_short_answer_not_measured():
    # C §7: 15초 미만 답변 → 발화 속도·침묵 미측정
    m = measure("가" * 50, contiguous(10))
    assert m.answer_sec == 10.0
    assert m.speech_rate is None and m.speech_rate_reason == "TOO_SHORT"
    assert m.long_pause_count is None and m.long_pause_per_min is None and m.long_pause_reason == "TOO_SHORT"


def test_exactly_min_answer_sec_is_measured():
    m = measure("가" * 75, contiguous(15))
    assert m.speech_rate == 300.0 and m.long_pause_reason is None


@pytest.mark.parametrize("text, heavy", [
    ("가" * 70 + "a" * 30, True),    # 30%
    ("가" * 80 + "1" * 20, True),    # 정확히 20%
    ("가" * 81 + "B" * 19, False),   # 19%
])
def test_non_hangul_heavy_skips_speech_rate_only(text, heavy):
    # C §7: 숫자·영어가 많은 답변 → 발화 속도 미측정 (침묵은 잰다)
    m = measure(text, contiguous(60))
    if heavy:
        assert m.speech_rate is None and m.speech_rate_reason == "NON_HANGUL_HEAVY"
    else:
        assert m.speech_rate == 81.0 and m.speech_rate_reason is None
    assert m.long_pause_count == 0 and m.long_pause_reason is None


def test_ratio_ignores_spaces_and_punctuation():
    assert non_hangul_ratio("가 나, 다. SQL!") == pytest.approx(3 / 6)
    assert non_hangul_ratio("...  ") == 0.0


def test_long_pauses_counted_at_two_seconds():
    m = measure("가" * 200, with_gaps([2.0, 2.0, 1.9]))
    assert m.long_pause_count == 2 and m.long_pause_per_min == 2.0


def test_float_noise_at_boundary():
    # 3.1 - 1.1 = 1.9999999999999998 이지만 2초 공백으로 센다
    words = [Word(word="a", start=0.0, end=1.1), Word(word="b", start=3.1, end=20.0)]
    assert measure("가" * 50, words).long_pause_count == 1


def test_no_words():
    m = measure("말은 했는데 단어 시간이 없음", [])
    assert m.answer_sec == 0.0 and m.speech_rate_reason == "TOO_SHORT" and m.long_pause_reason == "TOO_SHORT"
    assert speech_span([]) == 0.0


def test_uses_config_values(tmp_path):
    data = load_scoring_config().model_dump()
    data["delivery"]["speech_rate"]["min_answer_sec"] = 5
    data["delivery"]["long_pause_per_min"]["min_answer_sec"] = 5
    path = tmp_path / "scoring.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    m = measure("가" * 50, contiguous(10), read_scoring_config(path).delivery)
    assert m.speech_rate == 300.0 and m.long_pause_count == 0


def test_same_input_same_output_and_rounding():
    words = contiguous(17.2, step=0.4)
    a, b = measure("가" * 95, words), measure("가" * 95, words)
    assert a == b
    assert a.answer_sec == 17.2 and a.speech_rate == round(95 / 17.2 * 60, 1)


def test_result_is_delivery_metrics_with_camel_dump():
    m = measure("가" * 300, contiguous(60))
    assert isinstance(m, DeliveryMetrics)
    assert set(m.model_dump(by_alias=True)) == {"answerSec", "speechRate", "speechRateReason", "longPauseCount",
                                               "longPausePerMin", "longPauseReason"}
