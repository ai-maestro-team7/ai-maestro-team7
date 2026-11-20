import copy
import json

import pytest

from interview import config, versions
from interview.errors import AWS_SERVICE_ERROR, InterviewError


def raw_config():
    return json.loads(config.SCORING_CONFIG_PATH.read_text(encoding="utf-8"))


def write(tmp_path, data):
    path = tmp_path / "scoring.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def test_load_packaged_config():
    cfg = config.load_scoring_config()
    assert cfg.scoring_version == versions.SCORING_VERSION
    assert config.load_scoring_config() is cfg  # 프로세스에서 한 번만 읽는다


def test_delivery_values_match_spec():
    d = config.load_scoring_config().delivery
    # 가중치: docs/개발계획서3.md §4.3 (시간 관리 10 + 발화 속도 30 + 분당 긴 침묵 30)
    assert (d.time_management.weight, d.speech_rate.weight, d.long_pause_per_min.weight) == (10, 30, 30)
    # 15초 미만 → 발화 속도·침묵 미측정: §7 품질 검증 표
    assert d.speech_rate.min_answer_sec == 15 and d.long_pause_per_min.min_answer_sec == 15
    # 노션 6-②·6-⑤ 값
    assert d.speech_rate.max_non_hangul_ratio == 0.2
    assert d.long_pause_per_min.long_pause_sec == 2
    assert (d.long_pause_per_min.full_max, d.long_pause_per_min.zero_min) == (1, 5)


def test_scoring_values_match_notion_section_6():
    cfg = config.load_scoring_config()
    d = cfg.delivery
    assert cfg.recording_limit_sec == 120
    assert (d.time_management.before_limit, d.time_management.at_limit) == (10, 8)  # §7 "2분 초과 → 8점"
    assert d.speech_rate.full == (240, 360) and d.speech_rate.half == (180, 420)
    a = cfg.attitude
    assert (a.gaze_yaw_limit, a.gaze_pitch_limit, a.head_angle_limit) == (15, 8, 20)  # §4.3
    assert (a.frontal_full_min, a.frontal_zero_max, a.min_valid_count) == (80, 40, 10)
    tw = cfg.total_weights
    assert tw.all == {"content": 50, "delivery": 25, "attitude": 25}  # §4.3
    assert tw.no_attitude == {"content": 70, "delivery": 30}          # §7 카메라 미동의
    assert tw.for_areas({"content"}) == {"content": 100}
    assert [(g.min, g.label) for g in cfg.grades] == [(90, "우수"), (75, "양호"), (60, "보통"), (0, "보완 필요")]


@pytest.mark.parametrize("score, label", [(100, "우수"), (90, "우수"), (89.9, "양호"), (75, "양호"),
                                          (74, "보통"), (60, "보통"), (59, "보완 필요"), (0, "보완 필요")])
def test_grade_for(score, label):
    assert config.load_scoring_config().grade_for(score) == label


def test_config_has_no_model_id():
    assert "model_id" not in json.dumps(raw_config())


def test_unknown_keys_kept_for_later_stages(tmp_path):
    data = raw_config()
    data["content"] = {"weight": 50}
    data["delivery"]["speech_rate"]["full_range"] = [250, 350]
    cfg = config.read_scoring_config(write(tmp_path, data))
    assert cfg.model_extra["content"] == {"weight": 50}


def _broken(mutate):
    data = copy.deepcopy(raw_config())
    mutate(data)
    return data


@pytest.mark.parametrize("data", [
    "{not json",
    [],
    _broken(lambda d: d.update(scoring_version="v2.0")),
    _broken(lambda d: d.update(model_id="x")),
    _broken(lambda d: d["delivery"].pop("speech_rate")),
    _broken(lambda d: d["delivery"]["speech_rate"].update(max_non_hangul_ratio=1.5)),
    _broken(lambda d: d["delivery"]["speech_rate"].update(min_answer_sec=0)),
    _broken(lambda d: d["delivery"]["long_pause_per_min"].pop("long_pause_sec")),
    _broken(lambda d: d["delivery"]["long_pause_per_min"].update(full_max=5, zero_min=5)),
    _broken(lambda d: d["delivery"].update(extra_item={"enabled": True, "weight": 1})),
    _broken(lambda d: d["delivery"]["speech_rate"].update(full=[170, 360])),          # full이 half 밖
    _broken(lambda d: d["delivery"]["time_management"].update(at_limit=11)),
    _broken(lambda d: d["total_weights"]["all"].update(content=60)),                  # 합 110
    _broken(lambda d: d["total_weights"]["no_attitude"].update(attitude=0)),         # 영역 집합이 다름
    _broken(lambda d: d.pop("total_weights")),
    _broken(lambda d: d.update(grades=[{"min": 60, "label": "보통"}, {"min": 90, "label": "우수"},
                                       {"min": 0, "label": "보완 필요"}])),           # 내림차순 아님
    _broken(lambda d: d.update(grades=[{"min": 90, "label": "우수"}, {"min": 10, "label": "보통"}])),  # 0으로 안 끝남
    _broken(lambda d: d["attitude"].update(frontal_zero_max=90)),
])
def test_invalid_config_raises_config_error(tmp_path, data):
    with pytest.raises(InterviewError) as exc:
        config.read_scoring_config(write(tmp_path, data))
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False
    assert exc.value.__cause__ is None


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(InterviewError) as exc:
        config.read_scoring_config(tmp_path / "none.json")
    assert exc.value.code == AWS_SERVICE_ERROR and exc.value.retryable is False
