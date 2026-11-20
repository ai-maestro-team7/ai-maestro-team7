"""카메라 함수: 얼굴 분석(Rekognition DetectFaces), 정면 기준값 (camera design §4·§5, Requirement 2·3).

- 이미지는 bytes로 한 번 넘기고 어디에도 저장하지 않는다. S3에 올리지 않는다 (C §2.3 "얼굴 이미지 미저장")
- 감정·나이·성별은 요청하지 않는다 (노션 6-③ "감정 분석은 사용하지 않음")
- 눈 감음만으로 valid: false를 주지 않는다. eyesOpen을 넘기고 점수 단계에서 판단한다 (★ 백엔드와의 약속)
- Rekognition 호출이 실패해도 예외를 던지지 않고 valid: false(ANALYSIS_FAILED)를 돌려준다.
  캡처 한 장 실패로 면접이 끊기지 않게 한다 (camera 결정 2)
- 로그에는 단계, 처리 시간, 유효 여부, 사유 코드, 얼굴 수, AWS 오류 코드만 남긴다. 각도·확신도·품질 값은 남기지 않는다
"""

import logging
import time
from statistics import median

from pydantic import ValidationError

from .config import FaceCheckConfig, load_scoring_config
from .models import FaceResult
from .voice import _aws_error_code, _client

logger = logging.getLogger("interview")

STAGE_ANALYZE = "analyze_face"
STAGE_BASELINE = "compute_baseline"

# 기본 속성(BoundingBox, Confidence, Pose, Quality, Landmarks)은 따로 적지 않아도 같이 온다 (DetectFaces API 문서)
ATTRIBUTES = ("EYE_DIRECTION", "EYES_OPEN", "FACE_OCCLUDED")

# 분석 제외 사유 코드 (Requirement 2.4)
INVALID_IMAGE = "INVALID_IMAGE"
NO_FACE = "NO_FACE"
MULTIPLE_FACES = "MULTIPLE_FACES"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
FACE_OCCLUDED = "FACE_OCCLUDED"
TOO_DARK = "TOO_DARK"
BLURRY = "BLURRY"
ANALYSIS_FAILED = "ANALYSIS_FAILED"

# 이미지 자체가 문제인 Rekognition 오류. 나머지 오류는 ANALYSIS_FAILED
_IMAGE_ERRORS = frozenset({"InvalidImageFormatException", "ImageTooLargeException", "InvalidParameterException"})

DIGITS = 1  # 각도·확신도 반올림 자리 (C ★ frames 예시와 같은 소수 첫째 자리)


def _rekognition_client():
    return _client("rekognition")


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _invalid(reason: str) -> dict:
    return {"valid": False, "reason": reason, "gaze": None, "head": None, "eyesOpen": None}


def _angle(part) -> dict | None:
    if not isinstance(part, dict):
        return None
    yaw, pitch = part.get("Yaw"), part.get("Pitch")
    if not isinstance(yaw, (int, float)) or not isinstance(pitch, (int, float)):
        return None
    return {"yaw": round(float(yaw), DIGITS), "pitch": round(float(pitch), DIGITS)}


def _number(part, key: str) -> float | None:
    value = part.get(key) if isinstance(part, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _eyes_open(part) -> dict | None:
    if not isinstance(part, dict) or not isinstance(part.get("Value"), bool):
        return None
    confidence = _number(part, "Confidence")
    if confidence is None:
        return None
    return {"value": part["Value"], "confidence": round(confidence, DIGITS)}


def judge_face(details, cfg: FaceCheckConfig) -> dict:
    """DetectFaces의 FaceDetails → Face_Result (camera design §4.2). AWS를 부르지 않는 순수 함수다."""
    if not isinstance(details, list) or not details:
        return _invalid(NO_FACE)
    strong = [d for d in details if isinstance(d, dict) and (_number(d, "Confidence") or 0) >= cfg.min_face_confidence]
    if len(strong) >= 2:
        return _invalid(MULTIPLE_FACES)
    if not strong:
        return _invalid(LOW_CONFIDENCE)
    face = strong[0]
    gaze, head = _angle(face.get("EyeDirection")), _angle(face.get("Pose"))
    if gaze is None or head is None:
        return _invalid(ANALYSIS_FAILED)
    if (_number(face.get("EyeDirection"), "Confidence") or 0) < cfg.min_eye_direction_confidence:
        return _invalid(LOW_CONFIDENCE)
    occluded = face.get("FaceOccluded")
    if (isinstance(occluded, dict) and occluded.get("Value") is True
            and (_number(occluded, "Confidence") or 0) >= cfg.occluded_min_confidence):
        return _invalid(FACE_OCCLUDED)
    quality = face.get("Quality")
    brightness, sharpness = _number(quality, "Brightness"), _number(quality, "Sharpness")
    if brightness is not None and brightness < cfg.min_brightness:
        return _invalid(TOO_DARK)
    if sharpness is not None and sharpness < cfg.min_sharpness:
        return _invalid(BLURRY)
    # 눈 감음은 여기서 판정하지 않는다 (★ 백엔드와의 약속)
    return {"valid": True, "reason": None, "gaze": gaze, "head": head, "eyesOpen": _eyes_open(face.get("EyesOpen"))}


def detect_faces(image_bytes) -> list:
    """DetectFaces 호출 → FaceDetails. 실패하면 예외를 그대로 던진다 (analyze_face와 수동 확인이 쓴다)."""
    response = _rekognition_client().detect_faces(Image={"Bytes": image_bytes}, Attributes=list(ATTRIBUTES))
    return response["FaceDetails"]


def analyze_face(image_bytes):
    """캡처 이미지 한 장 → Face_Result (★ 형식). 예외를 던지지 않는다 (설정 파일 오류만 예외)."""
    cfg = load_scoring_config().face_check  # 설정 오류는 배포 오류라 숨기지 않는다
    started = time.monotonic()
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        logger.warning("stage=%s valid=false reason=%s", STAGE_ANALYZE, INVALID_IMAGE)
        return _invalid(INVALID_IMAGE)
    try:
        details = detect_faces(bytes(image_bytes))
    except Exception as exc:  # noqa: BLE001 — 권한, 한도, 네트워크, SDK 없음 모두 이 캡처만 빼고 진행
        code = _aws_error_code(exc)
        reason = INVALID_IMAGE if code in _IMAGE_ERRORS else ANALYSIS_FAILED
        logger.warning("stage=%s valid=false reason=%s awsError=%s durationMs=%d",
                       STAGE_ANALYZE, reason, code, _ms(started))
        return _invalid(reason)
    result = judge_face(details, cfg)
    faces = len(details) if isinstance(details, list) else 0
    logger.info("stage=%s valid=%s reason=%s faces=%d durationMs=%d", STAGE_ANALYZE,
                str(result["valid"]).lower(), result["reason"] or "none", faces, _ms(started))
    return result


def _usable(item) -> FaceResult | None:
    try:
        result = FaceResult.model_validate(item)
    except ValidationError:
        return None
    return result if result.valid else None


def compute_baseline(results):
    """보정 캡처의 Face_Result 목록 → 정면 기준값(중앙값). 쓸 수 있는 결과가 calibration_min_valid 미만이면 None.

    None이면 태도는 미측정이다. 백엔드는 대체값을 넣지 않고 그대로 session.baseline에 저장한다 (★ 백엔드와의 약속).
    형식이 어긋난 항목은 건너뛴다 (camera 결정 5).
    """
    cfg = load_scoring_config().attitude
    started = time.monotonic()
    usable = [r for r in (_usable(item) for item in (results if isinstance(results, list) else [])) if r is not None]
    if len(usable) < cfg.calibration_min_valid:
        logger.info("stage=%s usable=%d result=none durationMs=%d", STAGE_BASELINE, len(usable), _ms(started))
        return None

    def mid(values) -> float:
        return round(float(median(values)), DIGITS)

    baseline = {
        "gaze": {"yaw": mid(r.gaze.yaw for r in usable), "pitch": mid(r.gaze.pitch for r in usable)},
        "head": {"yaw": mid(r.head.yaw for r in usable), "pitch": mid(r.head.pitch for r in usable)},
    }
    logger.info("stage=%s usable=%d result=ok durationMs=%d", STAGE_BASELINE, len(usable), _ms(started))
    return baseline
