"""아직 없는 공개 함수 2개의 임시 구현 (1차 design §9, 결정 6).

backend/interview_stub.py(PR #31 반영본)와 같은 입출력이다. backend/를 import하지 않고 동작을 옮겨 적었다.
배포해도 백엔드의 카메라 호출에서 면접이 깨지지 않게 하려는 것이다.
음성 함수 3개는 2차(voice.py, #74), generate_report는 3차(report.py, #92)에서 실제 구현으로 바뀌었다.

실제 구현과 다른 점:
- 모두 고정 값을 돌려준다. Rekognition을 부르지 않는다.
- 이 값으로 태도 점수를 만들면 가짜 점수가 되므로 3차 리포트는 태도를 미측정으로 둔다.
"""


def analyze_face(image_bytes):
    """임시 구현, 4차 PR에서 Rekognition으로 교체. 고정 각도를 돌려준다."""
    if not image_bytes:
        return {"valid": False, "reason": "NO_FACE", "gaze": None, "head": None, "eyesOpen": None}
    return {"valid": True, "reason": None, "gaze": {"yaw": 1.5, "pitch": -2.0}, "head": {"yaw": 0.5, "pitch": 3.0},
            "eyesOpen": {"value": True, "confidence": 98.5}}


def compute_baseline(results):
    """임시 구현, 4차 PR에서 교체. 유효 3장 미만이면 None (태도 미측정, C 명세), 아니면 고정 기준값."""
    valid = [r for r in results if r.get("valid")]
    if len(valid) < 3:
        return None
    return {"gaze": {"yaw": 0.0, "pitch": 0.0}, "head": {"yaw": 0.0, "pitch": 0.0}}
