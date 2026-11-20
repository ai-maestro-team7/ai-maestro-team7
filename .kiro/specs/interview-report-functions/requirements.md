# Requirements Document

## Introduction

AI 모의면접 함수의 3차 단계다 (이슈 #92). 면접이 끝나면 답변 내용과 전달력을 채점하고 결과 리포트를 만든다. 지금 `generate_report`는 점수 없는 임시 구현이다(`placeholders.py`). 데모 가능한 최소 버전이 목표다 (C §9 7~10h).

기준 커밋: `main` `1cfc69d` (1차 #51·#69, 2차 #89 반영).

근거:
- C = `docs/개발계획서3.md` ★ 함수 명세(내부 함수 `evaluate_content`·`write_feedback`·`calculate_interview_scores`)·백엔드와의 약속, §2.2-5, §4.3, §5.4 리포트 예시, §7, §9
- 노션 "AI 모의면접 에이전트 기능" 6 점수 체계 ①~⑤ (평가표, 전달력 구간, 태도 기준, 종합 비율, 등급, 설정 파일). C §4.3이 "기능 정리 페이지 6번을 따른다"고 정함. 함수 인터페이스는 C ★절을 따른다 (AGENTS.md "C 기능 정리 페이지")
- 백엔드 호출부: `backend/interview_api.py` `make_report` (`compute_baseline` → `generate_report(session, answer_frames)` → `report.setdefault("interviewDate", …)` → `#REPORT` 저장)
- 1·2차 스펙: `.kiro/specs/interview-text-functions/`, `.kiro/specs/interview-voice-functions/`

핵심 원칙 (노션 6): 내용 항목별 평가는 AI, 지표 측정·점수 변환·합산은 코드. AI는 확정된 점수로 피드백만 작성한다. 미측정은 0점으로 넣지 않고 제외한다.

이 스펙의 결정 (C 담당 확인):
1. **태도는 3차에서 늘 미측정이다.** 지금 `analyze_face`·`compute_baseline`은 고정 값을 돌려주는 임시 구현이라, 이 값으로 계산하면 정면 응시 약 100%라는 가짜 점수가 나온다(제품 원칙 1, "가짜 숫자 금지"). 태도 계산은 4차에서 Rekognition과 함께 넣는다. 3차 종합은 `no_attitude`(내용 70 + 전달력 30) 또는 `content_only`(내용 100)다.
2. **설정값 사본은 Session에 저장하지 않는다.** 노션 6-⑤는 "세션마다 설정값 사본 저장"이지만, 대신 설정 파일을 버전별로 고정한다. 값을 바꾸면 `scoring_v2.json`을 새로 만들고 `v1.0` 파일은 바꾸지 않는다. 리포트에는 `scoringVersion`을 남긴다. Session 형식이 바뀌지 않아 백엔드 변경이 없다.
3. **`model_id`는 설정 파일에 넣지 않는다** (1차 결정 5, `MODEL_ID` 환경변수). 2차에서 넣은 `long_pause_sec: 2`(노션 6-② 표 "2초 이상 공백")는 유지한다. 등급 기준은 노션에서 표에만 있지만, 코드에 숫자를 박지 않으려고 설정 파일에 넣는다.
4. **묶음(기본 질문 + 꼬리질문)의 평가 가능 기준**: 기본 답변이 평가 불가면 그 묶음은 제외한다(이때는 꼬리질문이 없다, 1차 규칙). 꼬리 답변만 평가 불가면 기본 답변만으로 평가한다.
5. **`calculate_interview_scores`는 C-1 결과를 인자로 더 받는다.** C ★는 `(session, frames, config)`지만 내용 항목 점수는 Session에 없다(C-1이 리포트 시점에 만든다). `(session, frames, config, content)`로 두고 C ★ 내부 함수 표를 고친다. 내부 함수라 백엔드 계약에는 영향이 없다.
6. **평가용 시스템 프롬프트를 따로 둔다.** 1차 `system_v1.md`에 "점수를 말하지 않는다"가 있어 C-1(항목 점수 출력)과 충돌한다. C-1·C-2는 `system_eval_v1.md`를 쓴다.
7. **`write_feedback`(C-2)은 Strands 툴 사용 에이전트로 만든다.** 점수는 코드가 먼저 확정하고, 에이전트는 읽기 전용 툴 4개(확정 점수 조회, 전달력 수치, 답변 원문, 자소서 관련 부분 찾기)를 골라 부른 뒤 피드백을 쓴다.
   - 툴은 계산·AWS 호출·저장을 하지 않고, 이미 확정된 값의 복사본만 돌려준다. 점수를 바꾸는 툴은 없다.
   - C §2.3("AWS 서비스 호출·점수 계산은 에이전트 툴이 아닌 일반 코드")과 tech.md("AWS 호출·측정·점수 계산은 에이전트 툴이 아닌 일반 코드")를 지킨다. 툴은 조회만 한다.
   - 사용자·세션 ID는 툴 인자로 받지 않는다. 툴은 리포트 하나의 데이터에 묶여 만들어진다 (AGENTS.md "Agent 도구는 userId를 모델 파라미터로 받지 않는다").
   - 통합 멘토링 Agent와는 별개다. C의 면접관 에이전트 안에서만 쓰고 Action Group으로 내보내지 않는다 (C §10).
   - 반복 상한(턴 수·토큰)과 호출당 `max_tokens`를 둔다 (AGENTS.md "노션 허브 자료": 도구 반복 상한).

범위에서 제외:
- 태도 점수 계산, `analyze_face`·`compute_baseline` 실제 구현 (4차)
- `backend/`, `infra/`, `docs/db-schema.md` 수정, AWS 자원·권한 변경, 배포
- 리포트 다시 생성·재시도 흐름 (백엔드·프론트와 따로 정함)
- 질문 유형이 내용과 안 맞는 문제 (#69 후속, 별도 이슈)

## Glossary

- **Bundle(묶음)**: 기본 질문 하나와 그 꼬리질문(있으면)의 답변들. `questionId` `q1`과 `q1-f`가 한 묶음
- **Evaluable_Bundle**: 기본 답변이 평가 가능한 묶음 (결정 4)
- **Content_Evaluation**: C-1이 한 묶음에 대해 돌려주는 4개 항목 점수(1~5)와 근거
- **Score_Result**: `calculate_interview_scores`가 돌려주는 영역별·종합 점수, 등급, 미측정 사유, 계산 기준 문장
- **Report**: `generate_report`가 돌려주는 C §5.4 `report` 객체

## Requirements

### Requirement 1: 설정 파일 확장

#### Acceptance Criteria
1. THE `config/scoring_v1.json` SHALL 노션 6-⑤ 값을 담는다: `recording_limit_sec` 120, `time_management`(`before_limit` 10, `at_limit` 8), `speech_rate`(`full` [240, 360], `half` [180, 420]), `attitude`(시선 좌우 15, 위아래 8, 고개 20, 눈 감음 확신도 80, 정면 비율 만점 80·0점 40, 유효 캡처 10, 보정 3), `total_weights`(`all` 50/25/25, `no_attitude` 70/30, `no_delivery` 75/25, `content_only` 100).
2. THE 파일 SHALL 등급 기준 `grades`(90 우수, 75 양호, 60 보통, 그 아래 보완 필요)를 담는다 (결정 3).
3. THE `load_scoring_config` SHALL 새 값을 검사한다: `full`이 `half` 안에 있음, `total_weights` 각 묶음의 합이 100, `grades` 기준이 내림차순, 마지막 등급의 최소값 0. 어긋나면 `AWS_SERVICE_ERROR`(retryable false).
4. THE 파일 SHALL `model_id`를 담지 않고, `scoring_version`은 `v1.0`이다 (결정 2·3).

### Requirement 2: 내용 평가 (`evaluate_content`, 프롬프트 C-1)

#### Acceptance Criteria
1. WHEN Evaluable_Bundle 하나를 받으면 THE 함수 SHALL 질문 유형별 4개 항목을 1~5 정수로 평가한 Content_Evaluation을 돌려준다. 항목은 노션 6-① 평가표다.
   - experience(경험·인성): `relevance` 질문 관련성, `specificity` 행동의 구체성, `structure` 설명 구조, `outcome` 결과·배운 점
   - knowledge(지식): `accuracy` 정확성, `relevance` 질문 관련성, `logic` 논리성, `support` 근거·예시
   - situation(상황): `understanding` 문제 이해, `reasoning` 판단 근거, `process` 해결 과정, `alternatives` 대안·한계 고려
2. THE 함수 SHALL 기본 질문과 꼬리질문 답변을 한 묶음으로 평가한다 (노션 6-①).
3. THE 항목마다 근거 SHALL 답변 속 문장(`quote`) 또는 빠진 요소(`missing`) 중 하나다.
4. IF `quote`가 묶음의 답변 텍스트에 없으면(공백 정규화 후 부분 문자열 비교) THEN THE 함수 SHALL 그 인용을 근거로 쓰지 않는다. 점수는 남기고 `evidenceVerified: false`로 표시한다 (AGENTS.md "AI·데이터 규칙").
5. THE 프롬프트 SHALL 다음을 지시한다: 2·4점은 인접 기준의 중간, 수치가 없어도 본인 행동과 결과가 구체적이면 높게, 자소서와 다른 부분은 점수에 넣지 않음, 답변에 없는 경험을 지어내지 않음.
6. THE 출력 SHALL 고정 JSON으로 받아 Pydantic으로 검사한다 (항목 키가 유형의 4개와 정확히 같음, 점수 1~5 정수). 실패하면 1회 재시도 후 `AI_OUTPUT_INVALID` (1차 `call_json`).
7. THE 답변·질문·자소서 SHALL 데이터 태그로 감싸 넘긴다 (1차 Requirement 6).

### Requirement 3: 점수 계산 (`calculate_interview_scores`)

#### Acceptance Criteria
1. THE 함수 SHALL `(session, frames, config, content)`를 받아 Score_Result를 돌려주는 순수 함수다. AWS·LLM을 부르지 않고, 같은 입력이면 같은 결과다 (결정 5).
2. THE 내용 점수 SHALL 묶음별 `항목 합계 ÷ 20 × 100`의 평가 가능한 묶음 평균이다.
3. THE 답변별 전달력 SHALL `획득 점수 합 ÷ 측정된 항목 배점 합 × 100`이다.
   - 시간 관리: `timeLimitReached`가 false면 `before_limit`(10), true면 `at_limit`(8)
   - 발화 속도: `full` 구간 안이면 배점(30), `half[0]` 이하·`half[1]` 이상이면 배점의 절반(15), 그 사이는 직선
   - 긴 침묵: 분당 `full_max`(1) 이하면 배점(30), `zero_min`(5) 이상이면 0, 그 사이는 직선
   - 미측정 항목(`speechRate`·`longPausePerMin`이 null)은 분모에서 뺀다
4. IF 답변의 발화 속도와 긴 침묵이 둘 다 미측정이거나 `delivery`가 없으면(1차 Session) THEN THE 그 답변 SHALL 전달력 계산에서 제외한다 (시간 관리만으로 점수를 내지 않음).
5. THE 전달력 점수 SHALL 답변별 점수 → 묶음별 평균 → 측정된 묶음의 평균이다. 측정된 묶음이 없으면 전달력은 미측정이다.
6. THE 태도 SHALL 3차에서 늘 미측정이다. 사유는 `cameraConsent`가 false면 `CAMERA_NOT_USED`, true면 `ATTITUDE_NOT_READY`다 (결정 1). `frames`는 받기만 한다.
7. THE 종합 점수 SHALL 측정된 영역에 맞는 `total_weights` 묶음(`all`/`no_attitude`/`no_delivery`/`content_only`)으로 가중 평균한다.
8. THE 표시 점수 SHALL 정수로 반올림한다(0.5는 올림). 등급은 반올림한 종합 점수로 `grades`에서 고른다.
9. THE Score_Result SHALL 평가 가능한 기본 질문 수(`evaluatedBaseQuestions`)와 계산 기준 문장(`weightBasis`, 예: "내용 70% · 전달력 30%"), 미측정 이유 문장을 담는다. 문장은 코드가 정해진 틀로 만든다.
10. IF Evaluable_Bundle이 0개면 THEN THE `generate_report` SHALL 점수 함수를 부르지 않는다 (Requirement 5 기준 4).

### Requirement 4: 피드백 에이전트 (`write_feedback`, 프롬프트 C-2)

#### Acceptance Criteria
1. THE 함수 SHALL 점수 계산이 끝난 뒤에만 불리고, Evaluable_Bundle마다 `strengths`(1~2개), `improvements`(1~2개), `direction`(1문장), `comment`(1문장)를 돌려준다. 모델이 강점·보완을 3개 이상 쓰면 실패시키지 않고 앞의 2개만 남겨 검사한다 (수동 확인에서 3개를 써 스키마 실패가 났다).
2. THE 함수 SHALL Strands 에이전트에 읽기 전용 툴 4개를 주고, 에이전트가 필요한 툴을 골라 불러 정보를 모은 뒤 피드백 JSON을 쓰게 한다 (결정 7).
   - `get_confirmed_scores(question_id)`: 확정된 내용 점수, 항목별 점수와 검증된 근거, 전달력 점수
   - `get_delivery_metrics(question_id)`: 말 속도, 분당 긴 침묵, 시간 제한 도달, 미측정 사유
   - `get_answer_text(question_id)`: 질문과 답변 원문 (꼬리질문 포함)
   - `find_resume_passages(keyword)`: 자소서에서 키워드가 든 문장 최대 3개 (문자열 검색, LLM 없음)
3. THE 툴 SHALL 확정된 값의 복사본만 돌려주고 아무것도 바꾸지 않는다. 계산·AWS 호출·저장을 하지 않는다. 에이전트가 끝난 뒤 Score_Result가 호출 전과 같다.
4. IF 툴 인자가 없는 `question_id`이거나 빈 키워드면 THEN THE 툴 SHALL 예외 대신 오류 사실(`{"error": "UNKNOWN_QUESTION"}` 등)을 돌려준다.
5. THE 에이전트 SHALL 턴 수 상한(`settings.FEEDBACK_MAX_TURNS`), 토큰 상한(`FEEDBACK_MAX_TOTAL_TOKENS`), 툴 호출 상한(`FEEDBACK_MAX_TOOL_CALLS`), 호출당 `max_tokens`(`INTERVIEW_FEEDBACK_MAX_TOKENS`)를 둔다. 세 상한은 모두 에이전트 실행(시도)마다 새로 센다 (수동 확인에서 툴 상한을 두 시도가 같이 써 재시도가 실패했다). 상한에 닿아 피드백 JSON을 못 쓰면 출력 실패로 본다.
6. THE 출력 스키마 SHALL 점수 필드가 없다. 묶음 ID 집합이 평가 가능한 묶음과 같아야 한다.
7. THE 출력 SHALL 정답 제시, 합격·불합격 가능성 언급, 답변에 없는 경험·수치를 담지 않는다. 금지 표현(`합격`, `불합격`, `확률`)이 있으면 검사 실패로 보고 재시도한다 (제품 원칙 4, 문구 규칙). "떨어지다"는 일반 표현("집중이 떨어지다")에도 쓰여 넣지 않는다.
8. THE 출력 SHALL 고정 JSON + Pydantic 검사, 1회 재시도 후 `AI_OUTPUT_INVALID`다 (1차 `call_json`과 같은 규칙). 한 리포트에 에이전트 실행은 최대 2번이다.
9. THE 로그 SHALL 툴 이름과 호출 횟수, 턴 수, 멈춘 이유만 남긴다. 툴 입력·결과 원문은 남기지 않는다.

### Requirement 5: 리포트 (`generate_report`)

#### Acceptance Criteria
1. THE 함수 SHALL 백엔드 호출 형태 `generate_report(session, frames)` 그대로 C §5.4 `report`를 돌려준다.
2. THE 순서 SHALL Session 검사 → 묶음 만들기 → C-1(평가 가능한 묶음마다) → 점수 계산 → C-2 → 조립이다.
3. THE `report` SHALL `job`, `interviewType`, `evaluatedBaseQuestions`, `totalScore`, `grade`, `weightBasis`, `areas{content, delivery, attitude: {score, notMeasuredReason}}`, `notMeasuredMessages`(미측정 이유 문장), `questions[]`, `scoringVersion`, `modelId`, `promptVersion`, `notice`를 담는다. `interviewDate`는 백엔드가 넣는다.
   - `questions[]` 항목: `questionId`, `question`, `followUp{question, answerText}` 또는 null, `answerText`, `evaluable`, `reason`, `contentScore`, `strengths`, `improvements`, `direction`, `metrics{speechRate, longPausePerMin, frontalRatio, timeLimitReached}`, `comment`
   - `frontalRatio`는 3차에서 늘 null
   - `notice`: "면접 점수는 실제 합격 확률이 아니에요. 연습용 참고 지표예요."
4. IF Evaluable_Bundle이 0개면 THEN THE `report` SHALL `totalScore`·`grade`가 null이고, 각 영역 `score`가 null이며, `weightBasis`가 "평가할 수 있는 답변이 없어요"다. C-1·C-2를 부르지 않는다.
5. IF 평가 가능한 기본 질문이 1~2개면 THEN THE 점수는 그대로 계산하고 `weightBasis`에 "평가 가능한 기본 질문 N/3개 기준"을 덧붙인다 (감점 없음).
6. THE 평가 불가 묶음 SHALL `contentScore` null, 피드백 목록 비움, `comment`에 코드가 만든 안내(답변 없음 / 변환 실패)를 넣는다.
7. THE 결과 SHALL JSON 직렬화와 DynamoDB 저장·조회 변환(실수 → Decimal → int/float) 뒤에도 같은 형식이다.
8. THE `placeholders.py` SHALL `generate_report`를 지우고, `__init__.py`는 새 구현을 내보낸다. `__all__` 9개 이름과 시그니처는 그대로다.

### Requirement 6: 로그·안전

#### Acceptance Criteria
1. THE 로그 SHALL 단계(`evaluate_content`, `calculate_interview_scores`, `write_feedback`, `generate_report`), 처리 시간, 오류 코드, 평가 묶음 수만 남긴다. 질문·답변·근거 인용·피드백 원문은 남기지 않는다.
2. THE 리포트·피드백 SHALL 문구 규칙을 지킨다 (AGENTS.md "문구").

### Requirement 7: 테스트

#### Acceptance Criteria
1. THE 단위 테스트 SHALL AWS 없이 Fake_LLM으로 통과한다.
2. THE 경계값 테스트 SHALL 발화 속도 180·240·360·420, 긴 침묵 1·5, 등급 60·75·90, 시간 제한 도달 8점을 확인한다.
3. THE 시나리오 테스트 SHALL C §7을 확인한다: 정상 진행, 카메라 미동의(70/30), 평가 가능한 답변 0개, AI 출력 형식 오류, 15초 미만·숫자·영어 많은 답변의 미측정 처리, 평가 가능 기본 질문 1~2개.
4. THE C-1 항목 점수를 고정한 두 번의 계산 SHALL 같은 Score_Result를 낸다.
5. THE `test_backend_flow.py` SHALL `make_report` 순서(`compute_baseline` → `generate_report`)와 저장·조회 변환을 재현한다.
6. THE 수동 테스트 SHALL `RUN_BEDROCK=1`일 때만 실제 Bedrock으로 샘플 면접 리포트를 만들고, 출력 잘림이 없는지 확인한다.
