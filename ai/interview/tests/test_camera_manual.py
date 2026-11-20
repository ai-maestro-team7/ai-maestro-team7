"""실제 Rekognition DetectFaces 확인 (camera tasks 3, Requirement 8.6). 기본 실행에서는 건너뛴다.

켜는 방법 (aws login 뒤, -s로 이 파일만):
- RUN_AWS_CAMERA=1   켤 때
- CAMERA_TEST_DIR    로컬 사진 폴더 (jpg·jpeg·png). 이름이 calib로 시작하는 사진으로 정면 기준값을 만든다

사진은 이 폴더에서 읽기만 한다. 커밋하지 않고 S3에 올리지 않으며 어디에도 복사하지 않는다 (DetectFaces는 bytes로 부름).
출력: 사진마다 응답 시간, 판정(valid·reason), 각도, 눈 뜸, 품질 값(밝기·선명도·신뢰도·가림)과
기준값 대비 차이·정면 판정. 기준값(config/scoring_v2.json face_check·attitude)을 맞추는 데 쓴다.
결과는 커밋하지 않고 PR 참고 사항에 숫자만 적는다. 출력 문자는 콘솔 인코딩 문제를 피하려고 영문만 쓴다.
"""

import os
import time
from pathlib import Path

import pytest

from interview import attitude, camera
from interview.config import load_scoring_config
from interview.models import Baseline, Frame

pytestmark = pytest.mark.skipif(os.environ.get("RUN_AWS_CAMERA") != "1",
                                reason="실제 Rekognition 호출은 RUN_AWS_CAMERA=1일 때만")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _num(part, key):
    value = (part or {}).get(key)
    return f"{value:.1f}" if isinstance(value, (int, float)) else "-"


def _quality(details) -> str:
    if not details:
        return "faces=0"
    d = details[0]
    occ = d.get("FaceOccluded") or {}
    return (f"faces={len(details)} conf={_num(d, 'Confidence')} gazeConf={_num(d.get('EyeDirection'), 'Confidence')} "
            f"bright={_num(d.get('Quality'), 'Brightness')} sharp={_num(d.get('Quality'), 'Sharpness')} "
            f"occluded={occ.get('Value')}/{_num(occ, 'Confidence')}")


def test_detect_faces_on_local_photos():
    folder = Path(os.environ.get("CAMERA_TEST_DIR", "").strip() or ".")
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES) if folder.is_dir() else []
    if not photos:
        pytest.skip("CAMERA_TEST_DIR에 jpg·png 사진이 있어야 한다")
    cfg = load_scoring_config()

    results = {}
    print()
    for path in photos:
        image = path.read_bytes()
        started = time.monotonic()
        details = camera.detect_faces(image)  # 실패하면 예외 (수동 확인에서는 원인을 바로 본다)
        seconds = time.monotonic() - started
        face = camera.judge_face(details, cfg.face_check)
        results[path.name] = face
        print(f"[CAMERA] {path.name} seconds={seconds:.2f} kb={len(image) // 1024} valid={face['valid']} "
              f"reason={face['reason']} gaze={face['gaze']} head={face['head']} eyesOpen={face['eyesOpen']}")
        print(f"[CAMERA]   {_quality(details)}")

    calib = [results[name] for name in results if name.lower().startswith("calib")]
    baseline = camera.compute_baseline(calib)
    print(f"[CAMERA] baseline from {len(calib)} calib photos = {baseline}")
    if baseline is None:
        pytest.skip("유효한 calib 사진이 3장 미만이라 정면 판정을 볼 수 없다")
    base = Baseline.model_validate(baseline)
    a = cfg.attitude
    for name, face in results.items():
        if name.lower().startswith("calib") or not face["valid"]:
            continue
        frame = Frame.model_validate({"type": "ANSWER", "accepted": True, "answerId": "a-q1-1", **face})
        delta = {"gazeYaw": frame.gaze.yaw - base.gaze.yaw, "gazePitch": frame.gaze.pitch - base.gaze.pitch,
                 "headYaw": frame.head.yaw - base.head.yaw, "headPitch": frame.head.pitch - base.head.pitch}
        print(f"[CAMERA] {name} delta={ {k: round(v, 1) for k, v in delta.items()} } "
              f"frontal={attitude.is_frontal(frame, base, a)} eyesClosed={attitude.eyes_closed(frame, a)} "
              f"(limits gaze {a.gaze_yaw_limit}/{a.gaze_pitch_limit}, head {a.head_angle_limit})")
