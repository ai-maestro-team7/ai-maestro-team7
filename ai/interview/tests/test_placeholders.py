import json

import pytest

import interview
from fakes import FakeS3
from interview import placeholders


@pytest.fixture
def fake_s3(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(placeholders, "_s3_client", lambda: s3)
    return s3


def test_synthesize_question_returns_none():
    assert interview.synthesize_question("질문") is None


def test_start_transcription_writes_fake_result(fake_s3):
    key = "uploads/interview/iv-1/transcripts/a-q1-1.json"
    job = interview.start_transcription("s3://bucket/uploads/interview/iv-1/answers/a-q1-1.webm", "job-1", "webm",
                                        "test-uploads", key)
    assert job == "job-1"
    assert len(fake_s3.puts) == 1
    put = fake_s3.puts[0]
    assert put["Bucket"] == "test-uploads" and put["Key"] == key and put["ContentType"] == "application/json"
    assert json.loads(put["Body"])["jobName"] == "job-1"


def test_start_transcription_requires_output_location():
    with pytest.raises(TypeError):
        interview.start_transcription("s3://b/k", "job-1", "webm")


def test_get_transcription_result_shape():
    tr = interview.get_transcription_result("job-1")
    assert tr["status"] == "COMPLETED" and tr["text"] and tr["words"][0]["word"] == "저는"


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
