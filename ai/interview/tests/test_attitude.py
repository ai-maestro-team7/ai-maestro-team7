"""measure_attitude (camera design §6, Requirement 4). AWS·LLM을 부르지 않는다."""

import logging

import pytest

from interview import attitude
from interview.config import load_scoring_config
from interview.models import Frame
from scoring_helpers import BASELINE, answer, frame, frames, session

CFG = load_scoring_config()
A = CFG.attitude


def answered(camera=True, baseline=BASELINE):
    return session([answer("q1"), answer("q1", follow_up=True), answer("q2"), answer("q3")],
                   camera=camera, baseline=baseline)


def measure(items, **kw):
    return attitude.measure_attitude(answered(**kw), items, CFG)


def judge(**kw):
    """기준값(시선 0/-10, 고개 0/5)에 대한 캡처 한 장의 정면 판정."""
    return attitude.is_frontal(Frame.model_validate(frame(**kw)), answered().baseline, A)


# ---------------------------------------------------------------- 정면 판단 경계 (노션 6-③, C §2.3)


@pytest.mark.parametrize("kw, expected", [
    ({"gaze": (15.0, -10.0)}, True), ({"gaze": (15.1, -10.0)}, False),      # 시선 좌우 ±15°
    ({"gaze": (-15.0, -10.0)}, True), ({"gaze": (-15.1, -10.0)}, False),
    ({"gaze": (0.0, -2.0)}, True), ({"gaze": (0.0, -1.9)}, False),          # 시선 위아래 ±8° (기준 -10)
    ({"gaze": (0.0, -18.0)}, True), ({"gaze": (0.0, -18.1)}, False),
    ({"head": (20.0, 5.0)}, True), ({"head": (20.1, 5.0)}, False),          # 고개 좌우 ±20°
    ({"head": (0.0, 25.0)}, True), ({"head": (0.0, 25.1)}, False),          # 고개 위아래 ±20° (기준 5)
    ({"head": (0.0, -15.0)}, True), ({"head": (0.0, -15.1)}, False),
])
def test_frontal_boundaries(kw, expected):
    assert judge(**kw) is expected


def test_raw_zero_pitch_is_not_frontal_without_baseline_offset():
    # 노트북 카메라는 눈보다 아래라 정면을 봐도 시선 위아래가 약 -10°. 기준값 0을 쓰면 정면이 정면 아님이 된다 (C §2.3)
    assert judge(gaze=(0.0, -10.0)) is True
    zero = answered(baseline={"gaze": {"yaw": 0, "pitch": 0}, "head": {"yaw": 0, "pitch": 5}}).baseline
    assert attitude.is_frontal(Frame.model_validate(frame(gaze=(0.0, -10.0))), zero, A) is False


def test_looking_down_at_notes_is_not_frontal_but_counted():
    # C §7 "눈만 아래로 내려 메모 보기 → 정면 아님 (분석 제외 아님)": 위아래 약 10° 차이, 눈 감음 확신도 57%
    down = [frame(gaze=(0.0, -20.0), eyes=(False, 57.0))] * 10
    r = measure(down)
    assert r.reason is None and r.used_frames == 10 and r.frontal_frames == 0 and r.score == 0


# ---------------------------------------------------------------- 점수 환산 (정면 비율 80% 이상 100, 40% 이하 0)


@pytest.mark.parametrize("ratio, points", [(100, 100), (80, 100), (79, 97.5), (60, 50), (41, 2.5), (40, 0), (0, 0)])
def test_attitude_points(ratio, points):
    assert attitude.attitude_points(ratio, A) == pytest.approx(points)


@pytest.mark.parametrize("n_frontal, ratio, score", [(10, 100, 100), (8, 80, 100), (6, 60, 50), (5, 50, 25),
                                                     (4, 40, 0), (0, 0, 0)])
def test_ratio_and_score_from_frames(n_frontal, ratio, score):
    r = measure(frames(n_frontal, 10 - n_frontal))
    assert r.frontal_ratio == ratio and r.score == pytest.approx(score)


# ---------------------------------------------------------------- 미측정 사유


@pytest.mark.parametrize("n, measured", [(9, False), (10, True)])
def test_min_valid_frames(n, measured):
    r = measure(frames(n))
    assert (r.score is not None) is measured
    if not measured:
        assert r.reason == "NOT_ENOUGH_FRAMES" and r.used_frames == 9 and r.by_question == ()


@pytest.mark.parametrize("confidence, used", [(79.0, 10), (80.0, 9)])
def test_eyes_closed_excluded_only_at_80(confidence, used):
    items = frames(9) + [frame(eyes=(False, confidence))]
    r = measure(items)
    assert r.used_frames == used
    assert r.reason == (None if used == 10 else "NOT_ENOUGH_FRAMES")


def test_eyes_open_with_high_confidence_is_kept():
    assert measure(frames(9) + [frame(eyes=(True, 99.0))]).used_frames == 10


def test_missing_eyes_open_is_not_closed():
    assert measure(frames(9) + [frame(eyes=None)]).used_frames == 10


def test_reason_order():
    many = frames(20)
    assert measure(many, camera=False).reason == "CAMERA_NOT_USED"           # 캡처가 있어도
    assert measure(many, camera=False, baseline=None).reason == "CAMERA_NOT_USED"
    assert measure(many, baseline=None).reason == "CALIBRATION_FAILED"       # 정면 보정 없음
    assert measure([]).reason == "NOT_ENOUGH_FRAMES"


@pytest.mark.parametrize("extra", [
    frame(accepted=False),                    # 답변 제출 뒤 도착
    frame(valid=False),                       # 분석 제외 캡처
    frame(ftype="CALIBRATION"),               # 보정 캡처는 답변 중이 아님
    frame(answer_id="a-q9-1"),                # 면접 기록에 없는 답변
    {"type": "ANSWER", "answerId": "a-q1-1", "accepted": True, "valid": True, "gaze": None, "head": None},
    {"type": "ANSWER", "answerId": "a-q1-1", "valid": True},  # accepted 없음
    "not a frame",
])
def test_unusable_frames_are_excluded(extra):
    r = measure(frames(9) + [extra])
    assert r.reason == "NOT_ENOUGH_FRAMES" and r.used_frames == 9


def test_parse_frames_counts_bad_and_ignores_unknown_keys():
    good = dict(frame(), SK="INTERVIEW#x#FRAME#a-q1-1#t", reason=None)  # 백엔드가 키를 더해도 빠지지 않는다
    parsed, bad = attitude.parse_frames([good, {"type": "ANSWER"}, None])
    assert len(parsed) == 1 and bad == 2
    assert attitude.parse_frames("x") == ([], 0)


def test_dynamodb_ints_are_accepted():
    # DynamoDB를 거치면 0.0·98.0은 0·98이 된다
    item = {"type": "ANSWER", "questionId": "q1", "answerId": "a-q1-1", "capturedAt": "t", "accepted": True,
            "valid": True, "gaze": {"yaw": 0, "pitch": -10}, "head": {"yaw": 0, "pitch": 5},
            "eyesOpen": {"value": True, "confidence": 98}}
    assert measure([item] * 10).score == 100


# ---------------------------------------------------------------- 문항별 비율


def test_ratio_by_question_bundles_follow_up():
    items = (frames(6, answer_id="a-q1-1") + frames(0, 4, answer_id="a-q1-2")  # q1 묶음: 기본 6 정면 + 꼬리 4 돌림
             + frames(4, 1, answer_id="a-q2-1"))                               # q2: 5장 중 4장 정면
    r = measure(items)
    assert r.used_frames == 15 and r.frontal_frames == 10
    assert r.frontal_ratio == pytest.approx(10 * 100 / 15)
    assert [(q.question_id, q.frontal_ratio) for q in r.by_question] == [("q1", 60.0), ("q2", 80.0)]  # q3는 캡처 없음


def test_frames_of_unevaluable_answer_are_used():
    # camera 결정 4: 무응답 답변 중에도 화면을 보는 태도는 본다
    s = session([answer("q1"), answer("q2", evaluable=False, reason="NO_ANSWER"), answer("q3")], baseline=BASELINE)
    r = attitude.measure_attitude(s, frames(10, answer_id="a-q2-1"), CFG)
    assert r.used_frames == 10 and [q.question_id for q in r.by_question] == ["q2"]


def test_same_input_same_result():
    items = frames(7, 3) + frames(2, 2, answer_id="a-q2-1")
    assert measure(items) == measure(items)


def test_logs_have_counts_only(caplog):
    items = [frame(gaze=(3.21, -12.34), head=(4.56, 7.89), eyes=(True, 93.21))] * 10 + [{"bad": 1}]
    with caplog.at_level(logging.DEBUG, logger="interview"):
        measure(items)
    assert "stage=measure_attitude reason=none usedFrames=10 eyesClosed=0 badFrames=1" in caplog.text
    for secret in ("3.21", "12.34", "4.56", "7.89", "93.21"):
        assert secret not in caplog.text
