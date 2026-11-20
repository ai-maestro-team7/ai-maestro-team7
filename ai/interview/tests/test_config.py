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
