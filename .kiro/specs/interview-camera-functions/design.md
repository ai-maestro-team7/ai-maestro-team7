# Design Document

## 1. 개요

3차까지의 패키지(`ai/interview/`, `main` `197a024`)에서 카메라 임시 구현(`placeholders.py`)을 Rekognition 실제 호출로 바꾸고 태도 점수를 채운다 (이슈 #108). 공개 함수 이름·인자는 그대로다. 백엔드 코드는 바꾸지 않는다.

흐름 (C §2.2, 백엔드 `h_frame`·`make_report`):
```
[면접 중] h_frame (2초마다, 보정은 0.5초 간격 3초)
  └ analyze_face(image_bytes) → Face_Result → 백엔드가 FRAME으로 저장 (이미지는 버림)

[리포트] make_report
  ├ compute_baseline(보정 Face_Result 목록) → session.baseline (유효 3장 미만이면 None)
  └ generate_report(session, answer_frames)
       ├ … C-1 (3차)
       ├ calculate_interview_scores
       │    └ measure_attitude(session, frames, config)  ← 4차: 정면 비율 → 태도 점수
       ├ … C-2 (3차)
       └ 조립: metrics.frontalRatio 채움
```

## 2. 파일 변경

```
ai/interview/
  camera.py              새 파일: analyze_face, judge_face, compute_baseline (Rekognition)
  attitude.py            새 파일: measure_attitude, is_frontal, attitude_points
  placeholders.py        삭제
  __init__.py            analyze_face·compute_baseline을 .camera에서 import
  config/scoring_v2.json 새 파일: v1 값 + face_check (requirements 결정 1)
  config.py              FaceCheckConfig, SCORING_CONFIG_PATH → v2
  versions.py            SCORING_VERSION "v2.0"
  models.py              Angle, EyesOpen, Baseline, Frame, AttitudeResult, QuestionFrontal, AreaReason 갱신
  scoring.py             태도를 measure_attitude로, 안내 문장 갱신
  report.py              frontalRatio 채움, 평가 0개일 때 태도 사유, frames 목록 검사
  tests/                 test_camera.py, test_attitude.py, test_camera_manual.py 추가. fakes.py에 FakeRekognition.
                         test_placeholders.py 삭제, test_scoring·test_report·test_backend_flow·test_package·test_config 등 수정
```

## 3. 설정 파일 v2 (`config/scoring_v2.json`)

v1 내용 그대로 + 아래 절. `scoring_version` `v2.0`.

```json
"face_check": {
  "min_face_confidence": 90,
  "min_eye_direction_confidence": 50,
  "occluded_min_confidence": 80,
  "min_brightness": 20,
  "min_sharpness": 10
}
```

| 키 | 제안값 | 이유 (수동 확인으로 조정) |
| --- | --- | --- |
| `min_face_confidence` | 90 | 정면 얼굴은 보통 99 이상. 뒤 배경의 사진·포스터처럼 낮은 신뢰도 얼굴을 "여러 명"으로 세지 않게 같은 값을 쓴다 |
| `min_eye_direction_confidence` | 50 | 고개를 돌리면 시선 신뢰도가 떨어질 수 있다. 높게 잡으면 "고개 돌림"이 감점 대신 분석 제외가 되어 버린다. 낮게 두고 수동 확인에서 고개 돌림 사진의 값을 본다 |
| `occluded_min_confidence` | 80 | 눈 감음 기준(80)과 같은 방식: Rekognition이 가림이라고 하고 확신도가 높을 때만 뺀다 |
| `min_brightness` | 20 | Quality.Brightness 0~100. 일반 실내 노트북 카메라를 빼지 않을 만큼 낮게 |
| `min_sharpness` | 10 | Quality.Sharpness 0~100. 웹캠 JPEG는 선명도가 낮게 나오는 편이라 낮게 |

- `config.py`: `FaceCheckConfig`(모든 값 0 초과 100 이하, extra forbid). `ScoringConfig.face_check` 필수.
- `SCORING_CONFIG_PATH`는 `scoring_v2.json`. `read_scoring_config`는 버전이 `SCORING_VERSION`과 다르면 실패하므로 v1 파일은 기록으로만 남는다.
- `scoring_v1.json`은 바꾸지 않는다.

## 4. 얼굴 분석 (`camera.py`)

### 4.1 구조
```python
def analyze_face(image_bytes) -> dict:          # 공개, 백엔드 h_frame
    cfg = load_scoring_config().face_check       # 설정 오류는 예외 (requirements 결정 2)
    if not image_bytes: → INVALID_IMAGE
    try: details = _rekognition_client().detect_faces(Image={"Bytes": image_bytes},
                                                     Attributes=list(ATTRIBUTES))["FaceDetails"]
    except: → INVALID_IMAGE(형식·크기) / ANALYSIS_FAILED(그 밖)
    return judge_face(details, cfg)

def judge_face(details: list[dict], cfg: FaceCheckConfig) -> dict   # 순수 함수, 테스트 중심
```
- `ATTRIBUTES = ("EYE_DIRECTION", "EYES_OPEN", "FACE_OCCLUDED")`. 테스트가 `EMOTIONS`·`AGE_RANGE`·`GENDER`·`ALL`이 없는지 확인한다.
- 클라이언트는 `voice._client("rekognition")`를 쓴다 (프로세스에서 한 번, 지연 import). 테스트는 `camera._rekognition_client`를 가짜로 바꾼다.

### 4.2 판정 순서 (`judge_face`)
1. `details`가 비었으면 `NO_FACE`
2. `strong = [d for d in details if d.Confidence >= min_face_confidence]`
3. `len(strong) >= 2` → `MULTIPLE_FACES`
4. `strong`이 비었으면 `LOW_CONFIDENCE`
5. `face = strong[0]`. `EyeDirection`·`Pose`에 Yaw·Pitch가 없으면 `ANALYSIS_FAILED`
6. `EyeDirection.Confidence < min_eye_direction_confidence` → `LOW_CONFIDENCE`
7. `FaceOccluded.Value and FaceOccluded.Confidence >= occluded_min_confidence` → `FACE_OCCLUDED`
8. `Quality.Brightness < min_brightness` → `TOO_DARK`
9. `Quality.Sharpness < min_sharpness` → `BLURRY`
10. 통과: `valid: true`, 각도·확신도 소수 첫째 자리 반올림. `EyesOpen`이 없으면 `eyesOpen: null` (점수 단계에서 눈 감음 아님으로 본다)

- 눈 감음은 판정하지 않는다 (★ 약속). `Quality`·`FaceOccluded`가 응답에 없으면 그 검사는 건너뛴다(값이 없다고 빼지 않음).
- 출력 키는 늘 5개: `valid`, `reason`, `gaze`, `head`, `eyesOpen`. `valid: false`면 뒤의 셋은 `null`.

### 4.3 오류
| 상황 | 결과 |
| --- | --- |
| 빈 bytes, bytes가 아님 | `INVALID_IMAGE` (호출 안 함) |
| `InvalidImageFormatException`, `ImageTooLargeException`, `InvalidParameterException` | `INVALID_IMAGE` |
| 그 밖의 ClientError, 연결 오류, boto3 없음, 응답 형식 오류 | `ANALYSIS_FAILED` |
| 설정 파일 오류 | `InterviewError(AWS_SERVICE_ERROR, retryable=False)` |

- 재시도하지 않는다. 2초 뒤 다음 캡처가 온다.

### 4.4 로그
`stage=analyze_face valid=… reason=… faces=… durationMs=…` (+ 실패 시 `awsError=코드`). 각도·확신도·품질 값과 이미지는 남기지 않는다.

## 5. 정면 기준값 (`compute_baseline`)

```python
def compute_baseline(results) -> dict | None:
    cfg = load_scoring_config().attitude
    usable = [FaceResult 검사 통과 and valid and gaze and head]   # 형식 오류는 건너뜀
    if len(usable) < cfg.calibration_min_valid: return None
    return {"gaze": {"yaw": median, "pitch": median}, "head": {"yaw": median, "pitch": median}}  # 소수 첫째 자리
```
- 중앙값(`statistics.median`)이라 보정 중 한 번 깜빡이거나 흔들린 캡처의 영향이 작다.
- 눈 감음은 보정에서 따로 빼지 않는다 (명세에 없음, 중앙값이 흡수).
- 로그: `stage=compute_baseline usable=… result=none|ok durationMs=…`

## 6. 태도 측정 (`attitude.py`)

### 6.1 데이터 모델 (`models.py`)
```python
class Angle(_CamelModel):  yaw: float; pitch: float
class EyesOpen(_CamelModel):  value: bool; confidence: float (0~100)
class Baseline(_CamelModel):  gaze: Angle; head: Angle          # Session.baseline: Baseline | None
class FaceResult(BaseModel, extra="ignore"):  valid, reason, gaze, head, eyesOpen   # compute_baseline 입력 검사
class Frame(FaceResult):  type, questionId, answerId, capturedAt, accepted
    # valid=true면 gaze·head 필수. 모르는 키는 무시한다 (백엔드가 키를 더해도 캡처가 빠지지 않게)
class QuestionFrontal(_CamelModel, frozen):  question_id; frontal_ratio: int
class AttitudeResult(_CamelModel, frozen):
    score: float | None; reason: AttitudeReason | None
    used_frames: int; frontal_frames: int
    by_question: tuple[QuestionFrontal, ...]      # 측정됐을 때만, Used_Frame이 있는 묶음만
```
- `AttitudeReason = Literal["CAMERA_NOT_USED", "CALIBRATION_FAILED", "NOT_ENOUGH_FRAMES"]`
- `AreaReason`은 `ATTITUDE_NOT_READY`를 빼고 위 두 코드를 더한다.

### 6.2 계산
```python
def measure_attitude(session: Session, frames: list, config: ScoringConfig) -> AttitudeResult
```
1. `camera_consent` false → `CAMERA_NOT_USED`
2. `baseline` None → `CALIBRATION_FAILED`
3. 캡처 고르기: `parse_frames(frames)`(형식 오류는 빼고 개수만 셈) → `type == "ANSWER" and accepted and valid` → `answerId`가 `session.answers`에 있는 것 → 눈 감음(`eyesOpen.value is False and confidence >= 80`) 제외
4. Used_Frame < `min_valid_count` → `NOT_ENOUGH_FRAMES`
5. `is_frontal(frame, baseline, cfg)`: `|Δgaze.yaw| <= 15`, `|Δgaze.pitch| <= 8`, `|Δhead.yaw| <= 20`, `|Δhead.pitch| <= 20`
   - 차이는 `round(abs(a - b), 6)`으로 비교한다 (부동소수 오차로 15가 15.000000000000002가 되는 것을 막음)
6. 비율 `frontal * 100 / used` → `attitude_points(ratio, cfg)`: `>= 80` 100, `<= 40` 0, 사이 `(ratio - 40) / (80 - 40) * 100`
7. 문항별: `answerId` → 답변의 `questionId`에서 `-f`를 뗀 기본 질문 ID → 묶음별 같은 비율 → `round_half_up`

- 순수 함수. 같은 입력이면 같은 결과.
- 로그: `stage=measure_attitude reason=… usedFrames=… eyesClosed=… badFrames=… durationMs=…` (비율·각도는 남기지 않는다).

## 7. 점수·리포트 연결

### 7.1 `scoring.py`
- `reasons["attitude"]` 고정값 대신 `measure_attitude` 결과. 측정되면 `raw["attitude"] = result.score`.
- `weights = config.total_weights.for_areas(set(raw))`는 그대로라 50/25/25 · 70/30 · 75/25 · 100이 자동으로 고른다.
- `ScoreResult`에 `frontal_ratios: tuple[QuestionFrontal, ...]`를 더한다 (리포트 `metrics`용).
- `NOT_MEASURED_MESSAGES`: `ATTITUDE_NOT_READY` 삭제, `CALIBRATION_FAILED`·`NOT_ENOUGH_FRAMES` 추가 (requirements 5.2).

### 7.2 `report.py`
- `frames`가 `list`가 아니면 `INVALID_INPUT` (`parse_input`과 같은 로그·메시지).
- `_metrics(bundle, frontal)`: `frontalRatio`는 `score.frontal_ratios`에서 찾고 없으면 null.
- 평가 0개: 태도 사유 `CAMERA_NOT_USED` 또는 `NO_EVALUABLE_ANSWER`, `frontalRatio` null.

### 7.3 피드백 (C-2)
- 프롬프트는 바꾸지 않는다 (`C2-v1`). `get_confirmed_scores`의 `areas`에 태도 점수가 실린다.

## 8. 시간·비용

- DetectFaces는 캡처마다 1번. 2분 답변이면 약 60장, 면접 한 번(질문 3 + 꼬리 1, 보정 6장)에 약 250장 안쪽이다. 서울 리전 DetectFaces 요금은 이미지 1,000장당 약 1달러(첫 100만 장 구간)라 면접 1회 약 0.25달러 이하다. 팀 크레딧 200달러 안에서 시연·연결 테스트에 충분하다. 정확한 단가는 요금 페이지로 다시 확인한다.
- 응답 시간은 수동 확인에서 잰다. `/frame`은 동기 응답이라 API Gateway 30초 안이어야 한다 (Rekognition은 보통 1초 안쪽).

## 9. 테스트

실행 (저장소 루트):
```
uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q
```

| 파일 | 확인 내용 |
| --- | --- |
| `test_camera.py` | 요청 속성(감정·나이·성별 없음, 이미지 bytes만), 정상 출력 형식·반올림, 사유 코드 8개, 눈 감음은 valid, "눈만 내림" 응답은 valid, 호출 실패 → `ANALYSIS_FAILED`·`INVALID_IMAGE`, boto3 없음, 로그에 각도 없음, `compute_baseline` 2/3장·중앙값·형식 오류 건너뜀·DynamoDB 왕복 |
| `test_attitude.py` | 경계값(시선 15/15.1·8/8.1, 고개 20/20.1, 눈 감음 79/80, 유효 9/10, 비율 40/80), 사유 순서, accepted false·valid false·모르는 answerId 제외, 형식 오류 캡처 제외, 문항별 비율, 같은 입력 같은 결과 |
| `test_scoring.py` (수정) | 50/25/25, 75/25(전달력 미측정 + 태도 측정), 70/30(보정 실패), 안내 문장 |
| `test_report.py` (수정) | `frontalRatio` 채움, 3개 영역 점수, 보정 실패·카메라 미동의, frames 목록 아님 → `INVALID_INPUT` |
| `test_backend_flow.py` (수정) | 가짜 Rekognition으로 h_frame → make_report 한 바퀴, 눈만 내린 캡처 포함, DynamoDB 왕복 |
| `test_package.py`·`test_config.py`·`test_models.py` 등 (수정) | 모듈 출처 `interview.camera`, v2 설정, Baseline 형식 |
| `test_camera_manual.py` (추가) | `RUN_AWS_CAMERA=1`, `CAMERA_TEST_DIR`일 때만. 사진마다 시간·판정·각도·품질 출력, `calib*` 사진으로 기준값을 만들고 나머지 사진의 정면 판정 출력 |

## 10. 문서 변경 (`docs/개발계획서3.md`)

| 위치 | 바꿀 내용 |
| --- | --- |
| ★ `analyze_face`·`compute_baseline` | 사유 코드, 호출 실패 시 `ANALYSIS_FAILED`, baseline 형식 |
| §4.3 | 3차 태도 미측정 문장을 4차 기준으로 |
| §5.4 리포트 예시 | 태도 점수, `frontalRatio`, 미측정 사유 코드 |
| §5.5 | 분석 제외 사유 코드 |
| §11 | Rekognition 항목에 4차 수동 확인 결과 |

`docs/db-schema.md` §2.4 FRAME의 `reason`·`eyesOpen`, `baseline` 형식은 백엔드 담당에게 PR로 알린다 (범위 밖).

## 11. 열린 질문과 위험

| # | 내용 | 제안 |
| --- | --- | --- |
| 1 | 분석 제외 기준값은 노션에 없는 제안값이다 | 수동 확인 결과로 맞추고 PR에 숫자를 적는다. 바꾸면 v2 머지 전이므로 v2 파일을 고친다 |
| 2 | 고개를 크게 돌리면 얼굴·시선 신뢰도가 떨어져 "분석 제외"가 될 수 있다 (감점 회피) | 시선 신뢰도 기준을 낮게(50) 두고 수동 확인에서 고개 돌림 사진을 본다 |
| 3 | 안경 반사·조명으로 시선 값이 흔들릴 수 있다 | 기준값을 중앙값으로 잡고, 문항별 비율로 이상한 문항을 찾는다. 기준 조정은 v2 안에서 |
| 4 | 백엔드 FRAME에 `reason`을 저장하지만 `make_report`가 `generate_report`에 넘기지 않는다 | 점수에는 필요 없다. 바꾸지 않는다 |
| 5 | 진행 중인 세션의 `scoringVersion`이 `v1.0`일 수 있다 | 리포트는 리포트를 만든 때의 설정(v2.0)을 남긴다. v1과 v2의 점수 기준값은 같다 |
