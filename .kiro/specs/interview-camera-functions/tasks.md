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

- [ ] 3. 수동 확인 (실제 Rekognition, 사람이 실행)
  - [ ] 3.1 `test_camera_manual.py` (`RUN_AWS_CAMERA=1`, `CAMERA_TEST_DIR`)
  - [ ] 3.2 노트북 카메라 사진(보정 `calib*` 3장 이상, 정면, 눈만 내림, 고개 돌림)으로 실행. 응답 시간·각도·품질 값을 PR 참고 사항에 적고 기준값 확인. 사진은 커밋하지 않고 S3에 올리지 않는다
    - _Requirements: 8.6_
  - 커밋: `test: 카메라 수동 확인 테스트 추가`

- [ ] 4. 문서와 PR
  - [ ] 4.1 `docs/개발계획서3.md` ★·§4.3·§5.4·§5.5·§11 갱신 (design §10)
  - [ ] 4.2 전체 테스트 통과 확인, PR 본문 작성 (결정 1~7, 제안값, db-schema 알림)
  - 커밋: `docs: 카메라 분석·태도 점수 명세 반영`
  - PR 제목 `feat: 모의면접 카메라 시선 분석과 태도 점수 구현`, 라벨 `feat`·`be`, 본문 `Closes #108`
