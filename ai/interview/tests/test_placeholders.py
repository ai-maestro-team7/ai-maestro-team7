import pytest

import interview
from interview import placeholders


def test_only_camera_functions_remain():
    # 음성 함수 3개는 2차(voice.py, #74), generate_report는 3차(report.py, #92)로 옮겼다
    for name in ("synthesize_question", "start_transcription", "get_transcription_result", "_s3_client",
                 "generate_report"):
        assert not hasattr(placeholders, name)
    for name in ("analyze_face", "compute_baseline"):
        assert getattr(interview, name) is getattr(placeholders, name)


def test_analyze_face_empty_and_normal():
    assert interview.analyze_face(b"") == {"valid": False, "reason": "NO_FACE", "gaze": None, "head": None,
                                           "eyesOpen": None}
    face = interview.analyze_face(b"\xff\xd8fake")
    assert face["valid"] is True and face["eyesOpen"] == {"value": True, "confidence": 98.5}
    assert set(face) == {"valid", "reason", "gaze", "head", "eyesOpen"}


@pytest.mark.parametrize("n_valid, expect_none", [(0, True), (2, True), (3, False), (5, False)])
def test_compute_baseline_threshold(n_valid, expect_none):
    results = [{"valid": True}] * n_valid + [{"valid": False}] * 2
    baseline = interview.compute_baseline(results)
    assert (baseline is None) is expect_none
    if baseline is not None:
        assert set(baseline) == {"gaze", "head"}



