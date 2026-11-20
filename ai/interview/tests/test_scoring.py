import json

import pytest

from interview import scoring
from interview.config import load_scoring_config
from interview.models import AnswerRecord, ScoreResult
from scoring_helpers import all_evaluations, answer, delivery, evaluation, session

CFG = load_scoring_config()
D = CFG.delivery


def calc(s, content=None):
    return scoring.calculate_interview_scores(s, [], CFG, content if content is not None else all_evaluations())


def full_session(**kw):
    return session([answer("q1", **kw), answer("q2", **kw), answer("q3", **kw)])


# ---------------------------------------------------------------- 변환 경계값 (노션 6-②)


@pytest.mark.parametrize("rate, points", [
    (100, 15), (180, 15), (210, 22.5), (240, 30), (300, 30), (360, 30), (390, 22.5), (420, 15), (500, 15),
])
def test_speech_rate_points(rate, points):
    assert scoring.speech_rate_points(rate, D.speech_rate) == pytest.approx(points)


@pytest.mark.parametrize("per_min, points", [(0, 30), (1, 30), (3, 15), (5, 0), (8, 0)])
def test_long_pause_points(per_min, points):
    assert scoring.long_pause_points(per_min, D.long_pause_per_min) == pytest.approx(points)


def test_time_points_at_limit_is_8():
    # C §7 "2분 초과 → 시간 관리 8점"
    assert scoring.time_points(False, D.time_management) == 10
    assert scoring.time_points(True, D.time_management) == 8


def _record(**kw):
    return AnswerRecord.model_validate(answer("q1", **kw))


def test_answer_delivery_full_marks():
    assert scoring.answer_delivery_score(_record(), CFG) == 100


def test_answer_delivery_time_limit():
    assert scoring.answer_delivery_score(_record(time_limit=True), CFG) == pytest.approx(68 / 70 * 100)


def test_answer_delivery_unmeasured_speech_rate_excluded_from_denominator():
    # 숫자·영어가 많아 속도만 미측정 → 시간 관리 10 + 침묵 30 기준
    r = _record(metrics=delivery(rate=None, per_min=3.0))
    assert scoring.answer_delivery_score(r, CFG) == pytest.approx((10 + 15) / 40 * 100)


@pytest.mark.parametrize("metrics", [delivery(rate=None, per_min=None), None])
def test_answer_without_speech_measures_is_excluded(metrics):
    # 15초 미만(둘 다 미측정)이나 1차 Session(측정값 없음)은 시간 관리만으로 점수를 내지 않는다
    assert scoring.answer_delivery_score(_record(metrics=metrics), CFG) is None


# ---------------------------------------------------------------- 영역·종합


def test_all_measured_no_attitude_weights():
    r = calc(full_session())
    assert r.areas.content.score == 80 and r.areas.delivery.score == 100
    assert r.areas.attitude.score is None and r.areas.attitude.not_measured_reason == "ATTITUDE_NOT_READY"
    assert r.total_score == 86 and r.grade == "양호"  # 80×0.7 + 100×0.3
    assert r.weight_basis == "내용 70% · 전달력 30% 기준"
    assert r.not_measured_messages == ("카메라 분석은 다음 단계에서 제공돼 태도는 제외했어요.",)
    assert r.evaluated_base_questions == 3


def test_camera_not_used_reason():
    s = session([answer("q1"), answer("q2"), answer("q3")], camera=False)
    r = calc(s)
    assert r.areas.attitude.not_measured_reason == "CAMERA_NOT_USED"
    assert r.not_measured_messages == ("카메라를 사용하지 않아 태도는 제외했어요.",)


def test_delivery_unmeasured_uses_content_only():
    r = calc(full_session(metrics=delivery(rate=None, per_min=None)))
    assert r.areas.delivery.score is None and r.areas.delivery.not_measured_reason == "NOT_ENOUGH_SPEECH"
    assert r.total_score == 80 and r.weight_basis == "내용 100% 기준"
    assert len(r.not_measured_messages) == 2


def test_partial_bundles_marked():
    s = session([answer("q1"), answer("q2", evaluable=False, reason="NO_ANSWER"), answer("q3")])
    r = calc(s, all_evaluations(("q1", "q3")))
    assert r.evaluated_base_questions == 2
    assert r.weight_basis == "내용 70% · 전달력 30% 기준 · 평가 가능한 기본 질문 2/3개 기준"
    assert [b.question_id for b in r.bundles] == ["q1", "q3"]


def test_bundle_average_then_bundle_mean():
    # q1 묶음: 기본(100점) + 꼬리(시간 제한 도달, 68/70) 평균, q2·q3는 100점
    s = session([answer("q1"), answer("q1", follow_up=True, time_limit=True), answer("q2"), answer("q3")])
    r = calc(s)
    q1 = (100 + 68 / 70 * 100) / 2
    assert r.bundles[0].delivery_score == round(q1, 1)
    assert r.areas.delivery.score == scoring.round_half_up((q1 + 100 + 100) / 3)


def test_content_score_from_items():
    content = {"q1": evaluation("q1", (5, 5, 5, 5)), "q2": evaluation("q2", (1, 1, 1, 1)),
               "q3": evaluation("q3", (3, 3, 2, 4))}
    r = calc(full_session(), content)
    assert [b.content_score for b in r.bundles] == [100, 20, 60]
    assert r.areas.content.score == 60


@pytest.mark.parametrize("item_scores, grade", [
    ((5, 5, 5, 5), "우수"),  # 내용 100 → 100×0.7 + 100×0.3 = 100
    ((4, 4, 3, 4), "양호"),  # 75 → 82.5 → 83
    ((3, 3, 3, 3), "보통"),  # 60 → 72
    ((1, 1, 2, 2), "보완 필요"),  # 30 → 51
])
def test_grades(item_scores, grade):
    assert calc(full_session(), all_evaluations(scores=item_scores)).grade == grade


def test_grade_uses_rounded_total():
    # 내용 (90 + 80 + 85) / 3 = 85, 전달력 100 → 85×0.7 + 100×0.3 = 89.5 → 표시 90 → 우수
    content = {"q1": evaluation("q1", (5, 5, 4, 4)), "q2": evaluation("q2", (4, 4, 4, 4)),
               "q3": evaluation("q3", (4, 4, 5, 4))}
    r = calc(full_session(), content)
    assert r.total_score == 90 and r.grade == "우수"


def test_round_half_up():
    assert scoring.round_half_up(82.5) == 83 and scoring.round_half_up(72.5) == 73 and scoring.round_half_up(0.4) == 0


def test_same_input_same_result_and_json_round_trip():
    s = session([answer("q1"), answer("q1", follow_up=True, metrics=delivery(rate=210.0, per_min=2.0)),
                 answer("q2", metrics=delivery(rate=None, per_min=1.5)), answer("q3", time_limit=True)])
    a, b = calc(s), calc(s)
    assert a == b
    dumped = a.model_dump(by_alias=True, mode="json")
    assert ScoreResult.model_validate(json.loads(json.dumps(dumped))) == a


def test_no_evaluable_bundle_rejected():
    s = session([answer("q1", evaluable=False, reason="NO_ANSWER")])
    with pytest.raises(ValueError):
        scoring.calculate_interview_scores(s, [], CFG, {})


def test_content_must_match_evaluable_bundles():
    with pytest.raises(ValueError):
        calc(full_session(), all_evaluations(("q1", "q2")))


def test_frames_are_ignored_in_third_stage():
    frames = [{"type": "ANSWER", "answerId": "a-q1-1", "accepted": True, "valid": True}] * 20
    assert scoring.calculate_interview_scores(full_session(), frames, CFG, all_evaluations()) == calc(full_session())
