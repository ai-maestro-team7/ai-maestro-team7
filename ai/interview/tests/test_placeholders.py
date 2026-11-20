import pytest

import interview
from interview import placeholders


def test_only_camera_and_report_remain():
    # 음성 함수 3개는 2차에서 voice.py로 옮겼다 (#74)
    for name in ("synthesize_question", "start_transcription", "get_transcription_result", "_s3_client"):
        assert not hasattr(placeholders, name)
    for name in ("analyze_face", "compute_baseline", "generate_report"):
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


def test_generate_report_shape():
    session = {"job": "데이터 분석", "interviewType": "MIXED",
               "answers": [{"evaluable": True}, {"evaluable": False}, {"evaluable": True}]}
    report = interview.generate_report(session, [{}, {}])
    assert report["evaluatedBaseQuestions"] == 2
    assert report["frameCount"] == 2
    assert report["totalScore"] is None and report["scoringVersion"] == "stub"
