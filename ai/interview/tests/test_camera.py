"""analyze_face·compute_baseline (camera design §4·§5, Requirement 2·3). Rekognition은 가짜다."""

import json
import logging
import sys
from decimal import Decimal

import pytest

import interview
from fakes import FakeRekognition, client_error, face_detail
from interview import camera, voice
from interview.models import Baseline

IMAGE = b"\xff\xd8\xff\xe0fake-jpeg"
FACE_KEYS = {"valid", "reason", "gaze", "head", "eyesOpen"}


@pytest.fixture
def rek(monkeypatch):
    fake = FakeRekognition()
    monkeypatch.setattr(camera, "_rekognition_client", lambda: fake)
    return fake


def analyze(rek, *details):
    rek.responses = [list(details)]
    return interview.analyze_face(IMAGE)


# ---------------------------------------------------------------- 요청


def test_request_uses_image_bytes_and_only_needed_attributes(rek):
    interview.analyze_face(IMAGE)
    (call,) = rek.calls
    assert call["Image"] == {"Bytes": IMAGE}  # S3 객체가 아니라 bytes
    assert set(call["Attributes"]) == {"EYE_DIRECTION", "EYES_OPEN", "FACE_OCCLUDED"}
    for banned in ("EMOTIONS", "AGE_RANGE", "GENDER", "ALL"):  # 노션 6-③ 감정 분석 안 함
        assert banned not in call["Attributes"]


def test_normal_face_shape_and_rounding(rek):
    face = analyze(rek, face_detail(gaze=(-1.84, -9.86), head=(1.549, 8.01), eyes_open=(True, 96.14)))
    assert set(face) == FACE_KEYS
    assert face == {"valid": True, "reason": None, "gaze": {"yaw": -1.8, "pitch": -9.9},
                    "head": {"yaw": 1.5, "pitch": 8.0}, "eyesOpen": {"value": True, "confidence": 96.1}}


# ---------------------------------------------------------------- 분석 제외 (감점 아님)


@pytest.mark.parametrize("details, reason", [
    ([], "NO_FACE"),
    ([face_detail(), face_detail()], "MULTIPLE_FACES"),
    ([face_detail(confidence=80)], "LOW_CONFIDENCE"),                       # 얼굴 신뢰도 90 미만뿐
    ([face_detail(gaze_confidence=40)], "LOW_CONFIDENCE"),                  # 시선 신뢰도 50 미만
    ([face_detail(occluded=(True, 85))], "FACE_OCCLUDED"),
    ([face_detail(brightness=10)], "TOO_DARK"),
    ([face_detail(sharpness=5)], "BLURRY"),
    ([face_detail(gaze=None)], "ANALYSIS_FAILED"),                          # 시선 값 없음
    ([face_detail(head=None)], "ANALYSIS_FAILED"),
])
def test_excluded_frames(rek, details, reason):
    face = analyze(rek, *details)
    assert face == {"valid": False, "reason": reason, "gaze": None, "head": None, "eyesOpen": None}


@pytest.mark.parametrize("detail", [
    face_detail(occluded=(True, 70)),   # 가림 확신도 80 미만 → 빼지 않음
    face_detail(occluded=None),         # 가림 값이 없으면 검사를 건너뜀
    face_detail(brightness=20, sharpness=10),  # 기준값과 같으면 통과
    face_detail(gaze_confidence=50, confidence=90),
])
def test_borderline_frames_stay_valid(rek, detail):
    assert analyze(rek, detail)["valid"] is True


def test_weak_background_face_is_not_counted(rek):
    # 뒤 배경 포스터 같은 낮은 신뢰도 얼굴은 "여러 명"으로 세지 않는다
    face = analyze(rek, face_detail(confidence=60, head=(40, 0)), face_detail(head=(2.0, 3.0)))
    assert face["valid"] is True and face["head"] == {"yaw": 2.0, "pitch": 3.0}


def test_eyes_closed_alone_is_still_valid(rek):
    # 눈 감음 판단은 점수 단계 (★ 백엔드와의 약속)
    face = analyze(rek, face_detail(eyes_open=(False, 99.0)))
    assert face["valid"] is True and face["eyesOpen"] == {"value": False, "confidence": 99.0}


def test_looking_down_at_notes_is_valid(rek):
    # C §7 "눈만 아래로 내려 메모 보기": 분석 제외가 아니다. 정면 여부는 measure_attitude가 본다
    # 사전 테스트(C §11): 위아래 차이 약 10°, 눈 감음 확신도 57%
    face = analyze(rek, face_detail(gaze=(0.0, -20.0), head=(0.0, 5.0), eyes_open=(False, 57.0)))
    assert face["valid"] is True and face["gaze"]["pitch"] == -20.0


def test_missing_eyes_open_gives_null(rek):
    face = analyze(rek, face_detail(eyes_open=None))
    assert face["valid"] is True and face["eyesOpen"] is None


# ---------------------------------------------------------------- 실패해도 예외 없음


@pytest.mark.parametrize("image", [b"", None, "not-bytes", bytearray()])
def test_invalid_image_does_not_call_rekognition(rek, image):
    assert interview.analyze_face(image)["reason"] == "INVALID_IMAGE"
    assert rek.calls == []


@pytest.mark.parametrize("error, reason", [
    (client_error("InvalidImageFormatException", "DetectFaces"), "INVALID_IMAGE"),
    (client_error("ImageTooLargeException", "DetectFaces"), "INVALID_IMAGE"),
    (client_error("AccessDeniedException", "DetectFaces"), "ANALYSIS_FAILED"),
    (client_error("ThrottlingException", "DetectFaces"), "ANALYSIS_FAILED"),
    (client_error("ProvisionedThroughputExceededException", "DetectFaces"), "ANALYSIS_FAILED"),
    (RuntimeError("network"), "ANALYSIS_FAILED"),
])
def test_rekognition_errors_return_invalid(rek, error, reason):
    rek.responses = [error]
    face = interview.analyze_face(IMAGE)
    assert face == {"valid": False, "reason": reason, "gaze": None, "head": None, "eyesOpen": None}


def test_unexpected_response_shape_is_analysis_failed(rek, monkeypatch):
    class Broken:
        def detect_faces(self, **kwargs):
            return {}  # FaceDetails 없음

    monkeypatch.setattr(camera, "_rekognition_client", lambda: Broken())
    assert interview.analyze_face(IMAGE)["reason"] == "ANALYSIS_FAILED"


def test_without_boto3_returns_analysis_failed(monkeypatch):
    monkeypatch.setattr(voice, "_clients", {})
    monkeypatch.setitem(sys.modules, "boto3", None)
    assert interview.analyze_face(IMAGE)["reason"] == "ANALYSIS_FAILED"


def test_logs_have_no_angles_or_image(rek, caplog):
    rek.responses = [[face_detail(gaze=(3.21, -12.34), head=(4.56, 7.89), eyes_open=(True, 93.21))],
                     client_error("AccessDeniedException", "DetectFaces")]
    with caplog.at_level(logging.DEBUG, logger="interview"):
        interview.analyze_face(IMAGE)
        interview.analyze_face(IMAGE)
    assert "stage=analyze_face valid=true reason=none faces=1" in caplog.text
    assert "reason=ANALYSIS_FAILED awsError=AccessDeniedException" in caplog.text
    for secret in ("3.2", "12.3", "4.6", "7.9", "93.2", "fake-jpeg", "70.0", "40.0"):
        assert secret not in caplog.text


def test_judge_face_is_pure():
    cfg = camera.load_scoring_config().face_check
    details = [face_detail()]
    before = json.dumps(details)
    assert camera.judge_face(details, cfg) == camera.judge_face(details, cfg)
    assert json.dumps(details) == before


# ---------------------------------------------------------------- 정면 기준값


def valid_result(gaze=(0.0, -10.0), head=(0.0, 5.0)):
    return {"valid": True, "reason": None, "gaze": {"yaw": gaze[0], "pitch": gaze[1]},
            "head": {"yaw": head[0], "pitch": head[1]}, "eyesOpen": {"value": True, "confidence": 98.0}}


INVALID_RESULT = {"valid": False, "reason": "NO_FACE", "gaze": None, "head": None, "eyesOpen": None}


@pytest.mark.parametrize("n_valid, expect_none", [(0, True), (2, True), (3, False), (5, False)])
def test_baseline_needs_three_valid(n_valid, expect_none):
    # 보정 유효 2/3장 경계 (calibration_min_valid 3)
    results = [valid_result()] * n_valid + [INVALID_RESULT] * 4
    assert (interview.compute_baseline(results) is None) is expect_none


def test_baseline_is_median_of_valid_results():
    results = [valid_result((1.0, -9.0), (2.0, 4.0)), valid_result((3.0, -11.0), (0.0, 6.0)),
               valid_result((30.0, -10.0), (1.0, 5.0)),  # 보정 중 한 번 옆을 봄 → 중앙값이라 영향이 작다
               INVALID_RESULT]
    assert interview.compute_baseline(results) == {"gaze": {"yaw": 3.0, "pitch": -10.0},
                                                   "head": {"yaw": 1.0, "pitch": 5.0}}


def test_baseline_even_count_rounds_to_one_digit():
    results = [valid_result((1.0, -9.0)), valid_result((1.25, -9.5)), valid_result((2.0, -10.0)),
               valid_result((2.5, -10.0))]
    assert interview.compute_baseline(results)["gaze"] == {"yaw": 1.6, "pitch": -9.8}


def test_baseline_skips_malformed_items():
    malformed = [{"valid": True, "gaze": None, "head": None}, {"valid": "yes"}, "x", None,
                 {"valid": True, "gaze": {"yaw": "a", "pitch": 1}, "head": {"yaw": 0, "pitch": 0}}]
    assert interview.compute_baseline(malformed + [valid_result()] * 2) is None
    assert interview.compute_baseline(malformed + [valid_result()] * 3) is not None
    assert interview.compute_baseline(None) is None


def test_baseline_accepts_backend_rows_and_survives_dynamodb():
    # make_report는 FRAME 항목에서 valid·reason·gaze·head·eyesOpen만 골라 넘긴다. DynamoDB를 거치면 정수는 int
    rows = [json.loads(json.dumps(valid_result((0.0, -10.0))), parse_float=Decimal)] * 3
    plain = [json.loads(json.dumps(r, default=float)) for r in rows]
    baseline = interview.compute_baseline(plain)
    stored = json.loads(json.dumps(baseline), parse_float=Decimal)
    restored = {k: {a: (int(v) if v == v.to_integral_value() else float(v)) for a, v in part.items()}
                for k, part in stored.items()}
    assert restored == {"gaze": {"yaw": 0, "pitch": -10}, "head": {"yaw": 0, "pitch": 5}}
    Baseline.model_validate(restored)


def test_analyze_then_baseline_round_trip(rek):
    rek.responses = [[face_detail(gaze=(1.0, -10.0))], [face_detail(gaze=(2.0, -9.0))], [],
                     [face_detail(gaze=(0.0, -11.0))]]
    results = [interview.analyze_face(IMAGE) for _ in range(4)]
    assert [r["valid"] for r in results] == [True, True, False, True]
    assert interview.compute_baseline(results)["gaze"] == {"yaw": 1.0, "pitch": -10.0}
