# Implementation Plan

기준: 이 폴더의 `requirements.md`, `design.md`, 이슈 #108. 브랜치 `feat/be/#108-interview-attitude` (최신 `main` `197a024`에서). 테스트는 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q`.

- [x] 1. 설정과 얼굴 분석 (묶음 A)
  - [x] 1.1 `config/scoring_v2.json`(v1 + `face_check`), `config.py` `FaceCheckConfig`·경로, `versions.py` `v2.0` (design §3)
    - `test_config.py`, 버전 문자열을 보는 기존 테스트 수정
    - _Requirements: 1.1~1.4_
  - [x] 1.2 `models.py` `Angle`·`EyesOpen`·`Baseline`·`FaceResult`·`Frame`, `Session.baseline` 형식 (design §6.1)
  - [x] 1.3 `camera.py` `analyze_face`·`judge_face`·`compute_baseline` (design §4·§5), `placeholders.py` 삭제, `__init__.py` 연결
  - [x] 1.4 `fakes.py` `FakeRekognition`, `test_camera.py`, `test_placeholders.py` 삭제, `test_package.py` 수정
    - `test_backend_flow.py`도 가짜 Rekognition으로 바꿨다 (보정 캡처가 실제 판정을 거침)
    - _Requirements: 2.1~2.7, 3.1~3.5, 6.1~6.2, 7.1~7.2_
  - 커밋: `feat: 면접 카메라 얼굴 분석을 Rekognition으로 구현` (묶음 A 509 passed 4 skipped)

- [x] 2. 태도 점수와 리포트 (묶음 B)
  - [x] 2.1 `attitude.py` `measure_attitude` (design §6.2), `models.py` `AttitudeResult`·`QuestionFrontal`·`AreaReason`
  - [x] 2.2 `scoring.py`·`report.py` 연결 (design §7)
  - [x] 2.3 `test_attitude.py`, `test_scoring.py`·`test_report.py`·`test_feedback.py`·`test_backend_flow.py` 수정
    - `test_backend_flow.py`: 답변마다 정면 3·눈만 내림 1·빈 이미지 1 + 제출 뒤 도착 1장 → 정면 12/16 = 75% → 태도 88, 50/25/25
    - _Requirements: 4.1~4.8, 5.1~5.6, 8.1~8.5_
  - 커밋: `feat: 면접 태도 점수 계산과 리포트 연결` (묶음 B 570 passed 4 skipped)

- [x] 3. 수동 확인 (실제 Rekognition)
  - [x] 3.1 `test_camera_manual.py` (`RUN_AWS_CAMERA=1`, `CAMERA_TEST_DIR`)
  - [x] 3.2 노트북 카메라 사진(보정 `calib1~3`, 정면 `face`, 눈만 내림 `face_down`, 고개 돌림 `face_side`)으로 실행. 사진은 저장소 밖 로컬 폴더에서 읽기만 했다
    - 응답 0.40~0.55초 (첫 호출 1.61초, 연결 포함), 6장 모두 `valid`
    - 품질: 얼굴 신뢰도 100, 시선 신뢰도 99.6~100, 밝기 67.2~72.9, 선명도 73.3~83.1, 가림 false → 제안 기준(90·50·20·10)으로 빠지는 사진 없음
    - 기준값(보정 3장 중앙값): 시선 1.7/-14.5, 고개 2.0/5.5. 보정 3장의 시선 위아래가 -13.3~-17.0으로 3.7° 흔들림
    - 정면: 차이 시선 -3.5/4.6, 고개 -0.5/2.5 → 정면
    - 눈만 내림: 시선 -17.1/-5.1, 고개 -4.4/5.1, 눈 감음 확신도 57(빼지 않음) → 정면 아님. 위아래 차이는 ±8° 안이고 좌우 차이로 걸렸다 (design §11-6)
    - 고개 돌림: 시선 -42.0/7.0, 고개 -22.4/3.3, 시선 신뢰도 99.9 → 분석 제외 아니고 정면 아님 (design §11-2 우려는 이 사진에서는 없음)
    - _Requirements: 8.6_
  - 커밋: `test: 카메라 수동 확인 테스트 추가`

- [ ] 4. 문서와 PR
  - [x] 4.1 `docs/개발계획서3.md` ★·§3·§4.3·§5.4·§5.5·§6·§11 갱신 (design §10)
  - [x] 4.2 전체 테스트 통과 확인(570 passed, 5 skipped), PR 본문 작성 (결정 1~7, 제안값, db-schema 알림)
  - 커밋: `docs: 카메라 분석·태도 점수 명세 반영`
  - PR 제목 `feat: 모의면접 카메라 시선 분석과 태도 점수 구현`, 라벨 `feat`·`be`, 본문 `Closes #108`
