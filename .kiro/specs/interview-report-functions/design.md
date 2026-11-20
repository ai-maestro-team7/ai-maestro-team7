# Design Document

## 1. 개요

2차까지의 패키지(`ai/interview/`, `main` `1cfc69d`)에 내용 평가(C-1), 점수 계산, 피드백(C-2), 리포트 조립을 더한다 (이슈 #92). 공개 함수 `generate_report(session, frames)`의 이름·인자는 그대로다. 백엔드 코드는 바꾸지 않는다.

흐름 (C §2.2-5, 태도는 4차):
```
generate_report(session, frames)
  ├ Session 검사 (parse_input)
  ├ bundles = 묶음 만들기 (q1 + q1-f …)
  ├ 평가 가능한 묶음 0개 → 점수 없는 리포트 (LLM 부르지 않음)
  ├ 묶음마다 evaluate_content (C-1, LLM)   ← 근거 인용 대조
  ├ calculate_interview_scores (코드)      ← 내용·전달력·종합·등급, 태도 미측정
  ├ write_feedback (C-2, LLM, 1번)         ← 확정 점수만 근거
  └ 리포트 조립 (C §5.4)
```

## 2. 파일 변경

```
ai/interview/
  __init__.py            generate_report를 .report에서 import
  bundles.py             새 파일: Session 답변을 묶음으로 (결정 4)
  content.py             새 파일: evaluate_content, 근거 대조
  scoring.py             새 파일: calculate_interview_scores, 점수 변환 함수
  feedback.py            새 파일: write_feedback, 금지 표현 검사
  report.py              새 파일: generate_report
  models.py              ContentEvaluation, ScoreResult, FeedbackOutput, Report 등
  config.py              ScoringConfig에 새 값 검사 추가
  config/scoring_v1.json 노션 6-⑤ 값, grades 추가
  prompting.py           system_eval·C-1·C-2 프롬프트, 데이터 태그 추가
  prompts/system_eval_v1.md   새 파일 (결정 6)
  prompts/c1_content_v1.md    새 파일
  prompts/c2_feedback_v1.md   새 파일
  versions.py            PROMPT_C1_VERSION "C1-v1", PROMPT_C2_VERSION "C2-v1", REPORT_PROMPT_VERSION
  placeholders.py        generate_report 삭제 (analyze_face·compute_baseline만)
  samples/llm/           C-1·C-2 정상·오류 응답 예시
  tests/                 test_bundles.py, test_content.py, test_scoring.py, test_feedback.py, test_report.py 추가, 기존 테스트 수정
```

## 3. 묶음 (`bundles.py`)

```python
class Bundle(BaseModel):
    question: Question                 # 기본 질문 (questionId q1, questionType)
    base: AnswerRecord | None          # 기본 답변. 아직 없으면 None (면접이 덜 끝남)
    follow_up: AnswerRecord | None     # 꼬리 답변 (isFollowUp true)

    @property
    def evaluable(self) -> bool: return self.base is not None and self.base.evaluable
    def answer_records(self) -> list[AnswerRecord]: 평가 가능한 기본·꼬리 답변
    def answer_text(self) -> str: 평가 가능한 답변 텍스트를 줄바꿈으로 이은 값 (근거 대조용)
```
- `make_bundles(session)`: `session.questions` 순서대로, `answers[]`를 `questionId`(`q1`, `q1-f`)로 묶는다.
- 기본 답변이 평가 불가면 그 묶음은 제외한다. 꼬리 답변만 평가 불가면 기본 답변만으로 평가한다 (requirements 결정 4).

## 4. 내용 평가 (`content.py`, C-1)

### 4.1 평가표 키 (코드)
```python
RUBRIC = {
    "experience": ("relevance", "specificity", "structure", "outcome"),
    "knowledge":  ("accuracy", "relevance", "logic", "support"),
    "situation":  ("understanding", "reasoning", "process", "alternatives"),
}
```
- 항목 이름과 1·3·5점 기준 문장은 프롬프트 파일(`c1_content_v1.md`)에 노션 6-① 표 그대로 둔다. 키는 출력 검사용이라 코드에 둔다.

### 4.2 LLM 출력 (`ContentOutput`)
```json
{"items": [
  {"key": "relevance", "score": 4, "evidenceType": "quote", "evidence": "먼저 두 자료의 관광지 목록을 뽑아 비교했습니다"},
  {"key": "outcome", "score": 2, "evidenceType": "missing", "evidence": "배운 점 언급 없음"}
]}
```
- 검사: 키 집합이 그 유형의 4개와 정확히 같음, `score` 1~5 정수, `evidenceType` `quote`/`missing`, `evidence` 1~150자.
- 실패하면 `call_json`이 1회 재시도 후 `AI_OUTPUT_INVALID` (1차 §6.3, 출력 잘림도 같은 처리).

### 4.3 근거 대조
- `quote`면 공백을 정규화한 `evidence`가 공백을 정규화한 `bundle.answer_text()`의 부분 문자열인지 본다.
- 없으면 `evidenceVerified=false`, 리포트와 C-2 입력에서 그 인용을 뺀다. 점수는 남긴다 (requirements 2.4).
- `missing`은 인용이 아니므로 대조하지 않고 `evidenceVerified=true`.

### 4.4 프롬프트
- 시스템: `system_eval_v1.md`. 1차 `system_v1.md`의 데이터 규칙·06 제약은 그대로 옮기고, "점수를 말하지 않는다" 대신 "점수는 요청한 JSON 필드로만 낸다, 합격 가능성은 말하지 않는다"로 쓴다 (결정 6).
- 사용자 메시지 `c1_content_v1.md`: `{{JOB}}`, `{{RESUME}}`, `{{QUESTION_TYPE}}`, `{{QUESTION}}`, `{{ANSWER}}`, `{{FOLLOW_UP_QUESTION}}`, `{{FOLLOW_UP_ANSWER}}`, `{{RUBRIC}}`(유형에 맞는 평가표 표)
- 데이터 태그 추가: `question_type`, `follow_up_question`, `follow_up_answer`, `scores`, `evidence` (1차 `neutralize` 대상에도 추가)
- 지시: 2·4점은 중간, 수치 없어도 구체적이면 높게, 자소서와 다른 부분은 점수에 넣지 않음, 근거는 답변 문장을 그대로 인용하거나 빠진 요소를 적음

## 5. 점수 계산 (`scoring.py`)

```python
def calculate_interview_scores(session: Session, frames: list, config: ScoringConfig,
                               content: dict[str, ContentEvaluation]) -> ScoreResult
```
- `content`는 기본 질문 ID → C-1 결과. 평가 가능한 묶음만 들어 있다.
- 변환 함수는 따로 두고 단위 테스트한다:
  - `time_points(time_limit_reached, cfg)` → 10 또는 8
  - `speech_rate_points(rate, cfg)` → `full` 안 30, `half[0]` 이하·`half[1]` 이상 15, 그 사이 직선 (15 → 30, 30 → 15)
  - `long_pause_points(per_min, cfg)` → `full_max` 이하 30, `zero_min` 이상 0, 그 사이 직선
  - `answer_delivery_score(delivery, time_limit_reached, cfg)` → 0~100 또는 None(속도·침묵 둘 다 미측정, `delivery` 없음)
- 내용: 묶음 `sum(items) / 20 * 100` → 평균
- 전달력: 답변별 → 묶음 평균(측정된 답변만) → 측정된 묶음 평균. 없으면 미측정 `NOT_ENOUGH_SPEECH`
- 태도: 늘 미측정. `CAMERA_NOT_USED`(카메라 미동의) / `ATTITUDE_NOT_READY` (requirements 결정 1)
- 종합: 측정된 영역으로 `total_weights` 키 선택 → 가중 평균. 내용은 평가 가능한 묶음이 있으면 늘 측정됨
- 반올림: 내부는 float, 표시 값은 `Decimal(...).quantize(1, ROUND_HALF_UP)`로 정수. 등급은 반올림한 종합 점수로
- 계산 기준 문장 (코드 틀):

| 측정 영역 | `weightBasis` |
| --- | --- |
| 내용·전달력 | "내용 70% · 전달력 30% 기준" |
| 내용만 | "내용 100% 기준" |
| 평가 가능 기본 질문 1~2개 | 위 문장 + " · 평가 가능한 기본 질문 N/3개 기준" |

| 미측정 사유 코드 | 안내 문장 |
| --- | --- |
| `CAMERA_NOT_USED` | "카메라를 사용하지 않아 태도는 제외했어요." |
| `ATTITUDE_NOT_READY` | "카메라 분석은 다음 단계에서 제공돼 태도는 제외했어요." |
| `NOT_ENOUGH_SPEECH` | "말한 시간이 짧거나 숫자·영어가 많아 전달력은 제외했어요." |

```json
// ScoreResult (카멜)
{"totalScore": 78, "grade": "양호", "weightBasis": "내용 70% · 전달력 30% 기준",
 "areas": {"content": {"score": 80, "notMeasuredReason": null},
           "delivery": {"score": 72, "notMeasuredReason": null},
           "attitude": {"score": null, "notMeasuredReason": "ATTITUDE_NOT_READY"}},
 "notMeasuredMessages": ["카메라 분석은 다음 단계에서 제공돼 태도는 제외했어요."],
 "evaluatedBaseQuestions": 3,
 "bundles": [{"questionId": "q1", "contentScore": 80, "deliveryScore": 72.5}]}
```

## 6. 피드백 에이전트 (`feedback.py`, C-2, requirements 결정 7)

### 6.1 구조
```
write_feedback(context: FeedbackContext, *, llm=None) -> FeedbackOutput
  context = 점수 계산이 끝난 뒤의 고정 데이터 (frozen 모델)
            bundles(질문·답변·측정값), score_result, resume_text
  tools   = make_feedback_tools(context)  # 읽기 전용 함수 4개, context에 묶임
  output  = llm_module.call_json_with_tools(llm, system_prompt, user_prompt, tools, limits,
                                            schema=FeedbackOutput, stage="write_feedback")
```
- 사용자 메시지에는 평가 가능한 묶음의 `questionId`·질문 유형·질문 문장만 넣는다. 점수·답변·측정값은 에이전트가 툴로 가져온다.
- 툴은 일반 Python 함수(타입 힌트 + 설명 docstring)로 만든다. `StrandsLLMClient`가 실행할 때만 `strands.tool`로 감싼다. 그래서 단위 테스트는 strands 없이 가짜 클라이언트가 툴을 직접 부른다.

### 6.2 툴 (모두 조회만)
| 툴 | 인자 | 돌려주는 것 (사실 목록) |
| --- | --- | --- |
| `get_confirmed_scores` | `question_id` | `contentScore`, 항목별 `{key, score, evidence(검증된 것만)}`, `deliveryScore`, 영역 점수·미측정 사유 |
| `get_delivery_metrics` | `question_id` | `speechRate`, `longPausePerMin`, `longPauseCount`, `timeLimitReached`, 미측정 사유 |
| `get_answer_text` | `question_id` | 질문, 답변 원문, 꼬리질문·꼬리 답변 (평가 가능한 것만) |
| `find_resume_passages` | `keyword` | 자소서에서 키워드가 든 문장 최대 3개 (공백 정규화 후 부분 문자열, 문장당 200자까지) |

- 읽기 전용 보장:
  - `FeedbackContext`와 안의 모델은 `frozen=True`. 툴은 `model_dump()` 복사본만 돌려준다.
  - 점수를 쓰는 툴이 없다. 출력 스키마에 점수 필드가 없다.
  - 테스트가 에이전트 실행 전후의 `ScoreResult`가 같은지 확인한다.
- 잘못된 인자: 없는 `question_id` → `{"error": "UNKNOWN_QUESTION", "questionIds": [...]}`, 빈 키워드 → `{"error": "EMPTY_KEYWORD"}`. 예외를 던지지 않아 에이전트가 고쳐 부를 수 있다.
- 툴 호출 상한: `FEEDBACK_MAX_TOOL_CALLS`(12)를 넘으면 툴이 `{"error": "TOOL_LIMIT", "message": "지금까지 받은 정보로 답을 쓰세요"}`를 돌려준다.
- 사용자·세션 ID를 인자로 받지 않는다. 툴이 볼 수 있는 데이터는 이 리포트의 `context`뿐이다.

### 6.3 LLM 계층 변경 (`llm.py`)
- `ToolLLMClient` 프로토콜: `run_with_tools(*, system_prompt, user_prompt, tools, limits) -> str`
- `StrandsLLMClient.run_with_tools`: `Agent(model=_get_model(max_tokens=settings.feedback_max_tokens()), system_prompt, tools=[strands.tool(f) for f in tools], callback_handler=None)` → `agent(user_prompt, limits={"turns": …, "total_tokens": …})` → `str(result)`
  - strands 1.65 `Agent.__call__(limits=Limits)`: 상한에 닿으면 예외 없이 다음 턴 경계에서 멈추고 `stop_reason`이 `limit_turns` 등이 된다. 그때는 마지막 텍스트에 피드백 JSON이 없을 수 있어 출력 검사 실패로 이어진다 (재시도 1회 → `AI_OUTPUT_INVALID`).
  - `MaxTokensReachedException`은 1차처럼 `OutputTruncated`로 바꾼다.
- `_get_model`을 `max_tokens`별로 한 번씩 만들게 바꾼다 (질문·꼬리질문·C-1은 기본 1024, C-2는 `INTERVIEW_FEEDBACK_MAX_TOKENS` 기본 2048). 생각 끄기 설정은 같다.
- `call_json_with_tools`: `call_json`과 같은 재시도·오류 규칙. 공통 부분은 내부 함수로 묶는다.
- 로그: `stage=write_feedback attempt=… turns=… toolCalls=get_answer_text:3,get_confirmed_scores:3 stopReason=… durationMs=…`. 툴 입력·결과는 남기지 않는다. strands 자체 로그(`strands` 로거)는 DEBUG로 켜지 않는다.

### 6.4 출력과 검사
- `FeedbackOutput`: `{"questions": [{"questionId", "strengths": [..1~2], "improvements": [..1~2], "direction", "comment"}]}`. 점수 필드 없음.
- 강점·보완이 3개 이상이면 앞의 2개만 남긴다(버린 문장은 검사하지 않는다). 프롬프트에도 "1개 또는 2개만"을 적었다.
- 검사: 묶음 ID 집합이 평가 가능한 묶음과 같음(`call_json_with_tools`의 `check`), 문장 5~200자, 금지 표현(`settings.FEEDBACK_BANNED_WORDS`: 합격, 불합격, 확률) 없음. "떨어지다"는 일반 표현에도 쓰여 넣지 않았다.
- 프롬프트 `c2_feedback_v1.md`(시스템 `system_eval_v1.md`):
  - 묶음마다 `get_confirmed_scores`와 `get_answer_text`를 먼저 보라
  - 말 속도·멈춤을 말할 때는 `get_delivery_metrics` 값만 쓰라
  - 자소서와 연결할 때만 `find_resume_passages`를 쓰라
  - 툴 결과에 없는 사실은 쓰지 말라, 점수를 바꾸거나 새로 매기지 말라
  - 개선점은 "다음에 이렇게 해 보세요" 형태로, 마지막에 JSON 하나만 출력하라

### 6.5 시간·토큰 영향
- **시간 한도는 240초가 아니라 Lambda 300초다.**
  - 240초(`TRANSCRIBE_WAIT_SEC`)는 백엔드 `task_answer`가 변환을 기다리는 한도다.
  - 리포트는 마지막 답변의 `task_answer` 안에서 `make_report`로 이어서 만든다. 그래서 같은 Lambda 실행(300초) 안에 "변환 대기 + `process_answer` + 리포트"가 다 들어가야 한다.
- 추정 (Haiku 5.5, 생각 끔):
  - C-1: 묶음 3개 × 1~3초
  - C-2 에이전트: 턴 3~6번 × 1~3초. 툴은 한 턴에 여러 개를 같이 부를 수 있다
  - 리포트 전체 약 10~30초
  - 2차 수동 확인에서 1분 남짓한 답변의 변환은 10~13초였다. 합계는 300초 안에 넉넉하다
- 위험: 마지막 답변 변환이 240초 가까이 걸리면 리포트까지 300초를 넘어 Lambda가 끊길 수 있다. 끊기면 `run_task`의 실패 처리도 돌지 않아 세션이 `REPORT_GENERATING`에 남는다.
  - 상한으로 리포트 시간을 묶는다: 턴 6, 툴 호출 12, 총 토큰 30,000
  - 수동 확인에서 리포트 생성 시간을 잰다 (tasks 5)
  - 마지막 답변 처리와 리포트 생성을 별도 작업으로 나누는 것은 백엔드 담당과 따로 정한다
- 토큰:
  - 툴 결과(답변 원문 3개 약 1~2천 토큰)가 턴마다 다시 입력으로 들어간다. C-2 입력 합계는 약 1만~3만 토큰, 출력은 1~2천 토큰이다
  - 질문 3개 피드백 JSON은 1024 토큰을 넘을 수 있어 C-2만 `max_tokens` 2048로 둔다
  - Haiku 기준 비용 영향은 작다 (리포트 1건에 수 센트 이하)

## 7. 리포트 (`report.py`)

- `generate_report(session, frames, *, llm=None)` (`llm`은 키워드 전용, 테스트용. 백엔드는 넘기지 않음)
- 조립 규칙:
  - `questions[]`는 기본 질문 3개 순서. 꼬리 답변이 있으면 `followUp{question, answerText}`
  - `metrics`는 기본 답변 기준: `speechRate`, `longPausePerMin`(측정값 그대로, 미측정이면 null), `frontalRatio` null, `timeLimitReached`
  - 평가 불가 묶음: `contentScore` null, `strengths`·`improvements` [], `direction` null, `comment` 코드 안내("답변이 없어 평가하지 않았어요." / "음성을 변환하지 못해 평가하지 않았어요.")
  - `modelId`: 리포트 만들 때의 `settings.model_id()` (Session의 `modelId`는 질문 생성 때 값)
  - `promptVersion`: `"C1-v1/C2-v1"` (`versions.REPORT_PROMPT_VERSION`)
  - `notice`: "면접 점수는 실제 합격 확률이 아니에요. 연습용 참고 지표예요."
- 평가 가능한 묶음 0개: LLM을 부르지 않고 점수·등급 null, `weightBasis` "평가할 수 있는 답변이 없어요".
- `interviewDate`는 넣지 않는다 (백엔드 `make_report`가 `setdefault`).
- 실수는 `deliveryScore` 같은 내부 값만이고 리포트 표시 점수는 정수다. 측정값(`speechRate` 등)은 2차와 같이 실수이고 DynamoDB 왕복 뒤 int로 돌아와도 된다.

## 8. 설정 파일

```json
{
  "scoring_version": "v1.0",
  "recording_limit_sec": 120,
  "delivery": {
    "time_management": {"enabled": true, "weight": 10, "before_limit": 10, "at_limit": 8},
    "speech_rate": {"enabled": true, "weight": 30, "full": [240, 360], "half": [180, 420],
                    "min_answer_sec": 15, "max_non_hangul_ratio": 0.2},
    "long_pause_per_min": {"enabled": true, "weight": 30, "full_max": 1, "zero_min": 5,
                           "min_answer_sec": 15, "long_pause_sec": 2}
  },
  "attitude": {"gaze_yaw_limit": 15, "gaze_pitch_limit": 8, "head_angle_limit": 20,
               "eyes_closed_min_confidence": 80, "frontal_full_min": 80, "frontal_zero_max": 40,
               "min_valid_count": 10, "calibration_min_valid": 3},
  "total_weights": {"all": {"content": 50, "delivery": 25, "attitude": 25},
                    "no_attitude": {"content": 70, "delivery": 30},
                    "no_delivery": {"content": 75, "attitude": 25},
                    "content_only": {"content": 100}},
  "grades": [{"min": 90, "label": "우수"}, {"min": 75, "label": "양호"},
             {"min": 60, "label": "보통"}, {"min": 0, "label": "보완 필요"}]
}
```
- `attitude`는 3차에서 검사만 하고 쓰지 않는다 (4차).
- `enabled`가 false인 전달력 항목은 미측정처럼 분모에서 뺀다. 지금 값은 모두 true다.
- v1.0 파일은 3차 머지 뒤 값을 바꾸지 않는다. 바꾸려면 `scoring_v2.json` (requirements 결정 2).

## 9. 오류 처리

| 상황 | code | retryable |
| --- | --- | --- |
| Session 검사 실패, 질문 수 이상 | `INVALID_INPUT` | false |
| C-1·C-2 출력 2회 실패(형식·범위·금지 표현·잘림) | `AI_OUTPUT_INVALID` | true |
| Bedrock 호출 실패 | `AWS_SERVICE_ERROR` | true |
| 설정 파일 오류, `MODEL_ID` 없음 | `AWS_SERVICE_ERROR` | false |

- 실패하면 리포트를 돌려주지 않는다. 백엔드 `run_task`가 세션을 `FAILED`로 남기고 화면은 `retryable`로 안내한다. 리포트 다시 생성 흐름은 범위 밖이다 (requirements "범위에서 제외").

## 10. 로그

- 남김: `stage`, `durationMs`, `attempt`, `errorCode`, `bundles`(평가 묶음 수), `unverifiedEvidence`(대조 실패 개수)
- 남기지 않음: 질문, 답변, 근거 인용, 피드백 문장, 점수 문장

## 11. 테스트

실행 (저장소 루트):
```
uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q
```

| 파일 | 확인 내용 |
| --- | --- |
| `test_bundles.py` | q1·q1-f 묶기, 기본 평가 불가 제외, 꼬리만 평가 불가면 기본만, 면접 덜 끝난 Session |
| `test_content.py` | 유형별 키 검사, 점수 범위, 근거 대조(있음·없음·공백 차이), 재시도 후 `AI_OUTPUT_INVALID`, 프롬프트에 평가표·태그 |
| `test_scoring.py` | 경계값(속도 180·240·360·420, 침묵 1·5, 등급 60·75·90, 시간 8점), 미측정 제외, 둘 다 미측정 답변 제외, 1차 Session(`delivery` 없음), 비율 선택(70/30, 100), 반올림, 같은 입력 같은 결과 |
| `test_feedback.py` | 묶음 ID 일치, 금지 표현 → 재시도, 점수 필드 없음 |
| `test_report.py` | §5.4 형식, 평가 가능 0개(LLM 호출 없음), N/3개 기준, 카메라 미동의 사유, 평가 불가 묶음 안내, JSON·DynamoDB 왕복 |
| `test_backend_flow.py` (수정) | `make_report` 순서 재현, 실제 `generate_report` + Fake_LLM |
| `test_placeholders.py`, `test_package.py`, `test_logging.py` (수정) | `generate_report` 출처, 로그에 원문 없음 |
| `test_bedrock_manual.py` (추가 테스트) | `RUN_BEDROCK=1`일 때 샘플 면접 Session으로 실제 리포트 생성, 점수·등급 출력, 잘림 없음 |

## 12. 문서 변경 (`docs/개발계획서3.md`)

| 위치 | 바꿀 내용 |
| --- | --- |
| ★ 내부 함수 표 | `calculate_interview_scores` 입력에 `content`(C-1 결과) 추가 (결정 5) |
| §5.4 리포트 예시 | `modelId`, `promptVersion`, `notice` 추가, `attitude`의 3차 미측정 예시 |
| §4.3 | 등급 기준·전달력 구간을 설정 파일 기준으로 한 줄 |
| §11 | "평가표" 항목 체크 (노션 6-①을 프롬프트로 옮김) |

## 13. 열린 질문과 위험

| # | 내용 | 제안 |
| --- | --- | --- |
| 1 | 같은 답변에 C-1 항목 점수가 호출마다 조금 다를 수 있다 | 점수 계산은 같은 입력에 같은 결과. C-1 흔들림은 수동 테스트로 확인하고, 크면 평가 호출에만 temperature 0을 검토 (별도 결정) |
| 2 | C-1 3번 + C-2 에이전트 턴 최대 6번. 변환 대기와 같은 Lambda 실행(300초) 안이다 | §6.5. 상한으로 묶고 수동 테스트에서 리포트 생성 시간을 잰다 |
| 3 | C-2가 실패하면 점수는 있는데 리포트가 없다 | 3차는 오류로 끝낸다. 피드백 없이 점수만 주는 대체 경로는 필요해지면 따로 정한다 |
| 6 | 에이전트가 툴을 안 부르고 바로 쓰거나, 툴 결과에 없는 사실을 쓸 수 있다 | 프롬프트로 툴 사용을 지시하고, 출력 검사(묶음 ID·금지 표현)로 거른다. 사실 대조(피드백 문장이 툴 결과와 맞는지)는 3차 범위 밖이다. 수동 확인에서 로그의 툴 호출을 본다 |
| 4 | 태도 미측정이 데모에서 "점수가 빠졌다"로 보일 수 있다 | `notMeasuredMessages`로 이유를 보여 준다. 4차에서 채운다 |
| 5 | 노션 6 값은 저장소에 없다 | 이 스펙과 설정 파일에 옮겨 적었다. PR 참고 사항에 노션과 대조했다고 적는다 |
