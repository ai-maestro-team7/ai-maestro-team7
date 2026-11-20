# Requirements Document

## Introduction

AI 모의면접 함수의 4차 단계다 (이슈 #108). 임시 구현인 `analyze_face`·`compute_baseline`을 Rekognition 실제 호출로 바꾸고, 답변 중 정면 응시 비율로 태도 점수를 계산해 3차의 "태도 미측정"을 해제한다. 리포트 세 영역(내용·전달력·태도)이 모두 채워지는 것이 목표다 (C §9 10~13h).

기준 커밋: `main` `197a024` (1차 #51·#69, 2차 #89, 3차 #106 반영).

근거:
- C = `docs/개발계획서3.md` ★ 함수 명세(`analyze_face`, `compute_baseline`, 내부 `measure_attitude`)·백엔드와의 약속(눈 감음 판단, baseline None), §2.3(정면 보정 필수, 시선 위아래 ±8°), §4.3, §5.5 `/frame`, §5.6 캡처 간격, §7, §11 Rekognition 사전 확인
- 노션 "AI 모의면접 에이전트 기능" 6-③ 태도 기준("감정 분석은 사용하지 않음", 답변 중 캡처만 사용), 6-⑤ attitude 설정 (값은 3차에서 `config/scoring_v1.json`에 옮김)
- 백엔드 호출부: `backend/interview_api.py` `h_frame`(`analyze_face(image)` → FRAME 저장), `make_report`(보정 캡처 → `compute_baseline` → `session.baseline` → `generate_report(session, answer_frames)`). 권한: `infra/iam/lambda-role-policy.json` InterviewAI `rekognition:DetectFaces`
- 3차 스펙: `.kiro/specs/interview-report-functions/` (태도 미측정 결정 1, 설정 파일 버전 결정 2)
- Rekognition DetectFaces API 문서: `Attributes`에 `EYE_DIRECTION`, `EYES_OPEN`, `FACE_OCCLUDED`를 주면 기본 속성(`BoundingBox`, `Confidence`, `Pose`, `Quality`, `Landmarks`)과 함께 돌려준다. 이미지 bytes로 부르면 Rekognition이 데이터를 남기지 않는다(stateless)

이 스펙의 결정 (이슈 #108 본문 기준):
1. **분석 제외 기준값(흐림·어두움·신뢰도)은 노션에 없다.** 설정 파일에 제안값을 두고 수동 확인으로 맞춘다. 새 기준값이 생기므로 `config/scoring_v2.json`을 만들고 `scoring_version`을 `v2.0`으로 올린다. `scoring_v1.json`은 바꾸지 않는다 (3차 결정 2).
2. **Rekognition 호출이 실패해도 `analyze_face`는 예외를 던지지 않는다.** `valid: false` + 사유 `ANALYSIS_FAILED`를 돌려준다. 캡처 한 장 실패로 면접이 끊기지 않게 한다 (C 담당 확인). 설정 파일 오류는 배포 오류라 예외(`AWS_SERVICE_ERROR`)로 둔다.
3. **태도 미측정 사유 코드를 나눈다.** 카메라 미동의 `CAMERA_NOT_USED`(그대로), 정면 보정 없음 `CALIBRATION_FAILED`, 유효 캡처 부족 `NOT_ENOUGH_FRAMES`. 3차의 `ATTITUDE_NOT_READY`는 쓰지 않는다 (프론트·백엔드에서 이 코드를 쓰는 곳이 없음을 확인했다).
4. **답변 중 캡처는 평가 불가 답변의 것도 쓴다.** 노션 6-③ 기준(`type=ANSWER`, `accepted=true`, `valid=true`)만 적용한다. 답을 하지 않은 시간에도 화면을 보는 태도는 볼 수 있기 때문이다. 단, 평가 가능한 답변이 하나도 없으면 3차처럼 점수 없는 리포트를 만든다.
5. **형식이 어긋난 캡처 하나는 그 캡처만 뺀다.** 리포트 전체를 `INVALID_INPUT`으로 실패시키지 않는다. 뺀 개수는 로그에 남긴다. `frames`가 목록이 아니면 `INVALID_INPUT`이다.
6. **`session.baseline` 형식을 정한다** (3차까지 `dict | None`): `{"gaze": {"yaw", "pitch"}, "head": {"yaw", "pitch"}}` 또는 `None`. 임시 구현이 돌려주던 모양과 같아 백엔드 변경이 없다.
7. **분석 결과는 `analyze_face` ★ 형식 그대로다** (`valid`, `reason`, `gaze{yaw, pitch}`, `head{yaw, pitch}`, `eyesOpen{value, confidence}`). 흐림·밝기 같은 원본 값은 돌려주지 않는다. `valid: false`면 각도·눈 뜸은 `null`이다.

범위에서 제외:
- `backend/`, `infra/`, `frontend/`, `docs/db-schema.md` 수정, AWS 자원·권한 변경, 배포 (FRAME의 `reason` 필드 기록은 db-schema 담당에게 알린다)
- 감정·나이·성별 분석 (노션 6-③)
- 캡처 간격·보정 시간 변경 (C §5.6, 프론트)
- 피드백 프롬프트(C-2) 변경. 태도 점수는 `get_confirmed_scores`의 영역 점수로만 보인다

## Glossary

- **Face_Result**: `analyze_face` 출력 (★ 형식)
- **Baseline**: `compute_baseline` 출력. 정면 보정 캡처의 시선·고개 각도 중앙값
- **Frame**: 백엔드가 Face_Result에 `type`, `questionId`, `answerId`, `capturedAt`, `accepted`를 붙여 저장한 캡처 기록 (C ★ frames)
- **Used_Frame**: 태도 계산에 쓰는 Frame. `type=ANSWER`, `accepted=true`, `valid=true`, 면접에 기록된 답변의 `answerId`, 눈 감음 제외 뒤
- **Frontal**: Baseline 대비 시선 좌우·위아래, 고개 좌우·위아래 차이가 모두 기준 안
- **Attitude_Result**: `measure_attitude` 출력 (태도 점수 또는 미측정 사유, 문항별 정면 비율)

## Requirements

### Requirement 1: 설정 파일 v2

#### Acceptance Criteria
1. THE `config/scoring_v2.json` SHALL v1 값을 모두 그대로 담고 `scoring_version`은 `v2.0`이다.
2. THE 파일 SHALL 분석 제외 기준 `face_check`를 더한다: `min_face_confidence`(얼굴 신뢰도), `min_eye_direction_confidence`(시선 신뢰도), `occluded_min_confidence`(가림 판정 확신도), `min_brightness`(어두움), `min_sharpness`(흐림). 값은 제안값이고 수동 확인으로 맞춘다 (결정 1).
3. THE `load_scoring_config` SHALL v2 파일을 읽고 `face_check` 값이 0~100 범위인지 검사한다. 어긋나면 `AWS_SERVICE_ERROR`(retryable false).
4. THE `scoring_v1.json` SHALL 바뀌지 않는다. `versions.SCORING_VERSION`은 `v2.0`이다. 새 Session의 `scoringVersion`과 리포트의 `scoringVersion`이 `v2.0`이 된다.

### Requirement 2: 얼굴 분석 (`analyze_face`)

#### Acceptance Criteria
1. THE 함수 SHALL `analyze_face(image_bytes)` 형태로 Rekognition `DetectFaces`를 이미지 bytes로 부른다. S3에 올리거나 이미지를 저장하지 않는다.
2. THE 요청 SHALL `Attributes=["EYE_DIRECTION", "EYES_OPEN", "FACE_OCCLUDED"]`만 쓴다. 기본 속성(`Pose`, `Quality`, `Confidence`)은 함께 온다. 감정·나이·성별(`EMOTIONS`, `AGE_RANGE`, `GENDER`, `ALL`)은 요청하지 않는다 (노션 6-③).
3. THE 출력 SHALL ★ 형식이다: `valid`, `reason`, `gaze{yaw, pitch}`(EyeDirection), `head{yaw, pitch}`(Pose), `eyesOpen{value, confidence}`(EyesOpen). 각도·확신도는 소수 첫째 자리로 반올림한다.
4. IF 아래 중 하나면 THEN THE 함수 SHALL `valid: false`와 사유 코드를 돌려준다 (감점 아님, 검사 순서대로 첫 번째 사유):
   - 이미지가 비었거나 bytes가 아님 → `INVALID_IMAGE` (Rekognition을 부르지 않음)
   - 얼굴 없음 → `NO_FACE`
   - 신뢰도 `min_face_confidence` 이상인 얼굴이 2개 이상 → `MULTIPLE_FACES`
   - 얼굴은 있지만 모두 신뢰도 미달, 또는 시선 신뢰도가 `min_eye_direction_confidence` 미만 → `LOW_CONFIDENCE`
   - `FaceOccluded.Value`가 true이고 확신도 `occluded_min_confidence` 이상 → `FACE_OCCLUDED`
   - `Quality.Brightness`가 `min_brightness` 미만 → `TOO_DARK`
   - `Quality.Sharpness`가 `min_sharpness` 미만 → `BLURRY`
   - 시선·고개 각도가 응답에 없음 → `ANALYSIS_FAILED`
5. THE 함수 SHALL 눈 감음만으로 `valid: false`를 주지 않는다. 눈 뜸 값은 `eyesOpen`으로 넘기고 점수 단계에서 판단한다 (★ 백엔드와의 약속).
6. IF Rekognition 호출이 실패하면(권한, 한도, 네트워크, SDK 없음) THEN THE 함수 SHALL 예외 대신 `valid: false`, 사유 `ANALYSIS_FAILED`를 돌려준다. 이미지 형식·크기 오류(`InvalidImageFormatException`, `ImageTooLargeException`, `InvalidParameterException`)는 `INVALID_IMAGE`다 (결정 2).
7. THE `valid: false` 결과 SHALL `gaze`, `head`, `eyesOpen`이 `null`이다 (결정 7).

### Requirement 3: 정면 기준값 (`compute_baseline`)

#### Acceptance Criteria
1. THE 함수 SHALL `compute_baseline(results)` 형태로 보정용 Face_Result 목록을 받는다.
2. THE 함수 SHALL `valid: true`이고 시선·고개 각도가 있는 결과만 쓴다. 형식이 어긋난 항목은 건너뛴다.
3. IF 쓸 수 있는 결과가 `calibration_min_valid`(3) 미만이면 THEN THE 함수 SHALL `None`을 돌려준다 (태도 미측정, 백엔드는 대체값을 넣지 않음).
4. OTHERWISE THE 함수 SHALL `{"gaze": {"yaw", "pitch"}, "head": {"yaw", "pitch"}}`를 돌려준다. 각 값은 중앙값이고 소수 첫째 자리로 반올림한다.
5. THE 결과 SHALL DynamoDB 저장·조회(실수 → Decimal → int/float) 뒤에도 Session 검사를 통과한다.

### Requirement 4: 태도 측정 (`measure_attitude`)

#### Acceptance Criteria
1. THE 함수 SHALL `(session, frames, config)`를 받아 Attitude_Result를 돌려주는 순수 함수다. AWS·LLM을 부르지 않고 같은 입력이면 같은 결과다.
2. THE 사유 SHALL 다음 순서로 정한다:
   - `cameraConsent`가 false → `CAMERA_NOT_USED` (캡처가 있어도)
   - `session.baseline`이 None → `CALIBRATION_FAILED`
   - Used_Frame이 `min_valid_count`(10) 미만 → `NOT_ENOUGH_FRAMES`
3. THE Used_Frame SHALL `type=ANSWER`, `accepted=true`, `valid=true`이고 `answerId`가 Session 답변에 있는 캡처다 (노션 6-③, 결정 4). 형식이 어긋난 캡처는 뺀다 (결정 5).
4. THE 눈 감음 SHALL `eyesOpen.value`가 false이고 확신도 `eyes_closed_min_confidence`(80) 이상일 때만 Used_Frame에서 뺀다. 79면 빼지 않는다.
5. THE Frontal SHALL Baseline 대비 차이의 절댓값이 시선 좌우 `gaze_yaw_limit`(15) 이하, 시선 위아래 `gaze_pitch_limit`(8) 이하, 고개 좌우·위아래 `head_angle_limit`(20) 이하일 때다. 기준값과 같으면 정면이다.
6. THE 정면 응시 비율 SHALL `Frontal 개수 ÷ Used_Frame 개수 × 100`이다 (모든 문항을 합친 비율).
7. THE 태도 점수 SHALL 비율 `frontal_full_min`(80) 이상 100점, `frontal_zero_max`(40) 이하 0점, 그 사이 직선이다.
8. THE 문항별 정면 비율 SHALL 기본+꼬리 묶음(질문 ID `q1`)마다 같은 방식으로 계산한다. 그 묶음에 Used_Frame이 없거나 태도가 미측정이면 null이다.

### Requirement 5: 점수·리포트 연결

#### Acceptance Criteria
1. THE `calculate_interview_scores` SHALL 태도를 `measure_attitude`로 계산한다. 종합 비율은 측정 영역에 맞춰 `all`(50/25/25), `no_attitude`(70/30), `no_delivery`(75/25), `content_only`(100)다. 계산 기준 문장은 3차와 같은 틀이다(예: "내용 50% · 전달력 25% · 태도 25% 기준").
2. THE 미측정 안내 문장 SHALL 사유 코드마다 코드가 정한다:
   - `CAMERA_NOT_USED`: "카메라를 사용하지 않아 태도는 제외했어요."
   - `CALIBRATION_FAILED`: "정면 보정이 되지 않아 태도는 제외했어요."
   - `NOT_ENOUGH_FRAMES`: "얼굴이 확인된 캡처가 적어 태도는 제외했어요."
3. THE 리포트 `questions[].metrics.frontalRatio` SHALL 문항별 정면 비율(정수 반올림)이다.
4. IF 평가 가능한 답변이 0개면 THEN THE 리포트 SHALL 3차처럼 점수 없이 만들고, 태도 사유는 카메라 미동의면 `CAMERA_NOT_USED`, 아니면 `NO_EVALUABLE_ANSWER`이며 `frontalRatio`는 null이다.
5. THE `generate_report` SHALL `frames`가 목록이 아니면 `INVALID_INPUT`이다.
6. THE 리포트 SHALL JSON 직렬화와 DynamoDB 저장·조회 변환 뒤에도 같은 형식이다.

### Requirement 6: 패키지

#### Acceptance Criteria
1. THE `placeholders.py` SHALL 삭제한다. `__init__.py`는 실제 구현(`camera.py`)을 내보내고, `__all__` 9개 이름과 백엔드 호출 시그니처는 그대로다.
2. THE `import interview` SHALL boto3 없이도 된다 (Rekognition 클라이언트는 처음 호출할 때 만든다).

### Requirement 7: 로그·안전

#### Acceptance Criteria
1. THE 로그 SHALL 단계(`analyze_face`, `compute_baseline`, `measure_attitude`), 처리 시간, 유효 여부, 사유 코드, 얼굴 수, 캡처 개수, AWS 오류 코드만 남긴다. 각도·확신도 값, 이미지, 이미지 크기 외 원본 응답은 남기지 않는다.
2. THE 함수 SHALL 이미지를 파일·S3·전역 변수 어디에도 남기지 않는다.

### Requirement 8: 테스트

#### Acceptance Criteria
1. THE 단위 테스트 SHALL AWS 없이 가짜 Rekognition 응답으로 통과한다.
2. THE 경계값 테스트 SHALL 확인한다: 시선 좌우 15°/15.1°, 위아래 8°/8.1°, 고개 20°/20.1°, 눈 감음 확신도 79/80, 유효 캡처 9/10장, 정면 비율 40/80%, 보정 유효 2/3장.
3. THE 시나리오 테스트 SHALL C §7을 확인한다: "눈만 아래로 내려 메모 보기 → 정면 아님(분석 제외 아님)", "정면 보정 실패(유효 3장 미만) → 태도 미측정, 내용 70% + 전달력 30%", "카메라 미동의", "정상 진행 → 3개 영역 점수".
4. THE `test_backend_flow.py` SHALL 백엔드 순서(`h_frame` → `analyze_face`, `make_report` → `compute_baseline` → `generate_report`) 한 바퀴를 가짜 Rekognition으로 돌리고, DynamoDB 저장·조회 변환 뒤에도 형식이 유지되는지 본다.
5. THE 로그 테스트 SHALL 각도 값과 이미지 bytes가 로그에 없는지 본다.
6. THE 수동 테스트 SHALL `RUN_AWS_CAMERA=1`과 사진 폴더 환경변수가 있을 때만 로컬 사진으로 실제 DetectFaces를 부르고 응답 시간·각도·품질 값을 출력한다. 사진은 커밋하지 않고 S3에 올리지 않는다.
