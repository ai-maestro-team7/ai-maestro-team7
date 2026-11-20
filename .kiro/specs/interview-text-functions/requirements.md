# Requirements Document

## Introduction

AI 모의면접 함수의 1차 단계(이슈 #25)다. 텍스트 답변으로 면접 한 바퀴(기본 질문 3개 + 기본 질문당 꼬리질문 최대 1개 → 리포트 단계 도달)가 도는 함수를 `ai/interview/`에 만들어, `backend/interview_api.py`가 대역(`backend/interview_stub.py`) 대신 쓸 수 있게 한다.

근거와 전제:
- 기준 문서: C = `docs/개발계획서3.md` (PR #19 반영본) ★ 함수 명세·§4.2·§5.2·§7·§8·§9, `docs/architecture.md` §6·§9·§10-5, `docs/api.md` §5·§6.2·§6.6, `docs/db-schema.md` v1.3.1 §2.4, `AGENTS.md`, 결정 기록(`.kiro/specs/common-foundation/requirements.md`).
- 1차 범위는 C §9 2~5h(Strands 에이전트, 프롬프트 A·B, `start_interview`, 텍스트 답변용 `process_answer`)다.
- 백엔드는 `import interview as impl`로 패키지를 불러오고, 패키지가 있으면 대역을 쓰지 않는다 (`backend/interview_api.py` 30~37행, `infra/package.sh` 13~17행). 그래서 1차 머지 뒤 배포해도 깨지지 않도록 아직 없는 함수 6개를 임시 구현으로 함께 내보낸다.
- 이 스펙은 `main` `a556a31`(PR #26, #27, #29, #31 포함) 기준이다.
  - #29: 배포 Lambda 환경변수에 `MODEL_ID`가 들어갔다. 기본값은 `global.anthropic.claude-haiku-5-5`이고, 시연 때는 Sonnet으로 바꿔 다시 배포한다 (`infra/config.sh` 22~23행, `infra/setup-api.sh` 20행, `docs/team-guide.md` §4).
  - #31: 백엔드가 바뀐 C 명세를 반영했다. `start_transcription`을 인자 5개로 부르고(387행), `analyze_face`의 `eyesOpen`을 저장하며(421~425행), `compute_baseline`의 `None`을 그대로 둔다(284~288행). 대역(`backend/interview_stub.py`)도 같은 동작으로 바뀌었다.
  - #26: 계약 패키지 `team07_contracts`(`contracts/src/team07_contracts/`, D-18)가 들어왔다. `profile`은 `CareerProfileSummary`(소유 A, 소비 C·BACKEND), `job`은 `InterviewJobContext`(소유 C)로 정해졌다. `infra/package.sh`가 이 패키지를 배포 묶음에 넣는다.

이 스펙에 반영한 결정 (2026-11-20, C 담당):
1. 샘플 자소서는 데이터 분석 직무로 만든다 (D-37, api.md §6.2). C §3·§7도 이 작업에서 같이 고친다.
2. 자소서 민감정보 마스킹(architecture.md §9의 A F-01 7단계)은 C에 적용하지 않는다 (팀 확인 완료).
3. 지식 패키지 `06_MOCK_INTERVIEW.md`의 제약(가짜 기출 금지, 직무와 무관한 요소 평가 금지)을 프롬프트 A·B에 넣는다 (architecture.md §10-5).
4. `generate_questions`는 `session` 없이 직무·자소서·면접 유형만 받는 독립 함수로 만든다 (architecture.md §5.3 2단계 재사용 대비).
5. 1차는 환경변수 `MODEL_ID` 하나만 쓴다.
6. 아직 없는 함수 6개는 `ai/interview/` 안에 `backend/interview_stub.py`(PR #31 반영본)와 같은 동작의 임시 구현으로 만들어 내보낸다. `backend/`를 import하지 않는다.
7. `requirements.txt`에는 `strands-agents`, `pydantic`만 적는다.
8. `session`에 `modelId`, `promptVersion`, `currentQuestion`을 기록한다 (AGENTS.md "AI·데이터 규칙", design §4.2).
9. C ★ 주요 데이터 형식의 `session` 예시에 `modelId`, `promptVersion`, `currentQuestion`을 이 작업에서 같이 넣는다.
10. C §5 API 예시의 직무를 데이터 분석으로 바꾼다.

범위에서 제외:
- 음성 합성·변환과 전달력 측정 (2차), 설정 파일·내용 평가·점수·리포트 (3차), 시선 분석·정면 보정 (4차). 이 함수들은 임시 구현만 둔다.
- `backend/`, `infra/`, `contracts/`, `docs/db-schema.md` 수정 (각 담당)
- AWS 자원 생성·권한 변경·배포
- 챗 질문 연습 도구(architecture.md §10-5 2단계) 자체. 이 스펙은 `generate_questions`를 재사용할 수 있게만 만든다.
- 응답 문구 금지 패턴 검사(architecture.md §9 "문구 검사")와 근거 인용 대조. 피드백·평가를 만드는 3차에서 다룬다.

## Glossary

- **Interview_Package**: `ai/interview/` 폴더의 Python 패키지. 배포 묶음에서는 `interview` 패키지가 된다 (`infra/package.sh`)
- **Backend_Caller**: 면접 함수를 부르는 `backend/interview_api.py`
- **Public_Function**: Backend_Caller가 부르는 함수 8개. `start_interview`, `process_answer`, `synthesize_question`, `start_transcription`, `get_transcription_result`, `analyze_face`, `compute_baseline`, `generate_report` (C ★ "백엔드가 부르는 함수")
- **Temporary_Implementation**: 2~4차에 실제 구현으로 바꿀 Public_Function 6개의 임시 구현 (`synthesize_question`, `start_transcription`, `get_transcription_result`, `analyze_face`, `compute_baseline`, `generate_report`)
- **Contract_Package**: 파트 간 데이터 계약 패키지 `team07_contracts` (`contracts/src/team07_contracts/`, D-18)
- **Career_Profile_Summary**: Contract_Package의 `CareerProfileSummary`. `start_interview`의 `profile` 형식이다 (`projects`, `skills`, `needsConfirmation` 필수, `profileId`, `profileVersion` 선택)
- **Session**: Interview_Package가 만들고 갱신하는 세션 데이터. Backend_Caller는 받은 그대로 저장하고 다음 호출에 그대로 넘긴다 (C ★ 주요 데이터 형식)
- **Answer_Result**: `process_answer`에 넘기는 답변 결과 (`answerId`, `timeLimitReached`, `transcription`)
- **Base_Question**: 면접마다 3개 만드는 기본 질문 (`q1`~`q3`)
- **Follow_Up_Question**: Base_Question 하나에 붙는 꼬리질문. Base_Question당 최대 1개
- **Interviewer_Agent**: Strands Agents SDK로 만든 면접관 에이전트. 1차에서는 질문 생성과 꼬리질문 판단만 한다
- **LLM_Client**: Interviewer_Agent 호출을 감싼 인터페이스. 테스트에서는 Fake_LLM으로 바꾼다
- **Fake_LLM**: 미리 정한 응답 문자열을 돌려주는 테스트용 LLM_Client
- **Prompt_A**: 질문 생성 프롬프트 (`generate_questions`)
- **Prompt_B**: 꼬리질문 판단 프롬프트 (`judge_follow_up`)
- **Sample_Data**: `ai/interview/samples/`의 가상 자소서·세션·답변·LLM 응답
- **Evaluable**: 답변이 평가 가능한지 여부. 평가 불가 사유는 `NO_ANSWER`(말이 없음) 또는 `TRANSCRIBE_FAILED`(변환 실패) (C §4.2)

## Requirements

### Requirement 1: 패키지 구성과 공개 함수

**User Story:** 백엔드 담당으로서, `import interview` 한 줄로 면접 함수 8개를 모두 꺼내 쓰고 싶다. 그래야 대역을 걷어내도 기존 호출 코드가 그대로 동작한다.

근거: C ★ "백엔드가 부르는 함수"·"백엔드와의 약속", `backend/interview_api.py` 31·234·244·255·270·288·291·387·421행, `infra/package.sh` 13~34행, architecture.md §3 "배포 단위"

#### Acceptance Criteria

1. THE Interview_Package SHALL `__init__.py`에서 Public_Function 8개와 `InterviewError`를 내보낸다.
2. THE Interview_Package SHALL 패키지 안의 모듈끼리 상대 import(`from .models import ...`)만 쓴다.
3. THE Interview_Package SHALL `backend/` 아래 모듈(`interview_stub`, `common` 등)을 import하지 않는다. Contract_Package(`team07_contracts`)는 import할 수 있다.
4. THE Interview_Package SHALL 환경변수 `MODEL_ID`가 없어도, `strands-agents`가 설치되지 않은 환경에서도 `import interview`가 성공한다. 모델이 필요한 첫 호출에서만 설정을 읽는다.
5. THE Interview_Package SHALL Public_Function을 Backend_Caller의 현재 호출 형태(위치 인자 개수와 순서)로 부를 수 있다.
6. THE Interview_Package SHALL `requirements.txt`에 `strands-agents`, `pydantic`만 적는다. 테스트 전용 의존성은 별도 파일(`requirements-dev.txt`)에 둔다.

### Requirement 2: 오류

**User Story:** 백엔드 담당으로서, 면접 함수의 실패 원인을 코드 하나로 받아 팀 공통 오류 형식으로 바꾸고 싶다.

근거: C ★ "백엔드와의 약속", C §5.1 오류 코드 표, `backend/interview_api.py` 302~314·450~454행

#### Acceptance Criteria

1. THE Interview_Package SHALL 실패를 `InterviewError(code, message, retryable)`로만 밖에 알린다. `code`, `message`, `retryable`은 속성으로 읽을 수 있다.
2. THE Interview_Package SHALL `code`로 `INVALID_INPUT`, `AI_OUTPUT_INVALID`, `AWS_SERVICE_ERROR` 세 가지만 쓴다.
3. THE Interview_Package SHALL `retryable` 기본값을 `INVALID_INPUT`은 false, `AI_OUTPUT_INVALID`와 `AWS_SERVICE_ERROR`는 true로 한다 (C §5.1).
4. THE Interview_Package SHALL `message`를 사용자에게 보여 줄 수 있는 한국어 문장으로 쓰고, 자소서·답변·LLM 출력 원문을 넣지 않는다.

### Requirement 3: 데이터 계약

**User Story:** 백엔드 담당으로서, 받은 Session을 그대로 저장했다가 다시 넘기기만 하면 되도록 입출력 형식이 고정되어 있으면 좋겠다.

근거: C ★ "주요 데이터 형식"·"백엔드와의 약속", C §5.2 필드 규칙, AGENTS.md "코딩 규칙"(Pydantic v2)·"AI·데이터 규칙"(modelId, promptVersion), 결정 8·9

#### Acceptance Criteria

1. THE Interview_Package SHALL 함수 입력, Session, Answer_Result, `process_answer` 출력, LLM 출력을 Pydantic v2 모델로 정의하고 검사한다.
2. THE Interview_Package SHALL 함수 입력 인자 이름은 snake_case로, 돌려주는 데이터의 키는 카멜 표기로 한다.
3. THE Interview_Package SHALL Session에 C ★ 예시의 필드(`sessionId`, `job`, `interviewType`, `cameraConsent`, `resumeText`, `profile`, `scoringVersion`, `questions`, `currentIndex`, `followUpUsed`, `answers`, `baseline`)와 `modelId`, `promptVersion`, `currentQuestion`을 담는다.
4. WHEN 입력이 Pydantic 검사를 통과하지 못하면, THE Interview_Package SHALL `INVALID_INPUT`을 던진다.
5. THE Interview_Package SHALL 인자로 받은 Session·Answer_Result 객체를 바꾸지 않고, 갱신한 값은 새 객체로 돌려준다.
6. THE Interview_Package SHALL 돌려주는 Session을 JSON으로 직렬화할 수 있는 값(문자열, 정수, 불리언, null, 리스트, 객체)으로만 채운다. 1차에서는 실수 값을 Session에 넣지 않는다.

### Requirement 4: 면접관 에이전트와 모델 설정

**User Story:** C 담당으로서, 모델 ID를 코드에 넣지 않고 환경변수로 바꿔 끼우고, 모델 호출 내용이 로그에 새지 않게 하고 싶다.

근거: C ★ "설정"·§2.3, architecture.md §6·§9, api.md §6.6, `infra/config.sh` 22~23행(#29), `docs/team-guide.md` §4, AGENTS.md "노션 허브 자료"(모델 클라이언트 한 번, Agent 요청마다), `examples/strands_hello.py`

#### Acceptance Criteria

1. THE Interviewer_Agent SHALL 모델 ID를 환경변수 `MODEL_ID` 하나에서만 읽는다. 코드에 모델 ID 기본값을 두지 않는다. 배포 기본값(Haiku)과 시연 값(Sonnet)은 `infra/config.sh`가 정한다.
2. IF 모델 호출이 필요한데 `MODEL_ID`가 비어 있으면, THEN THE Interviewer_Agent SHALL `AWS_SERVICE_ERROR`(retryable false)를 던진다.
3. THE Interviewer_Agent SHALL 리전은 환경변수 `AWS_REGION`을 쓰고, 값이 없으면 `ap-northeast-2`를 쓴다.
4. THE Interviewer_Agent SHALL `max_tokens` 상한을 설정에서 읽어 모델에 넘긴다.
5. THE Interviewer_Agent SHALL 모델 클라이언트는 프로세스에서 한 번 만들어 재사용하고, Strands Agent는 호출마다 새로 만든다. 서로 다른 세션의 대화가 섞이지 않는다.
6. THE Interviewer_Agent SHALL 도구 없이 동작하고, 스트리밍 출력을 표준 출력에 쓰지 않는다.
7. THE Interview_Package SHALL 질문 생성과 꼬리질문 판단에만 LLM을 쓴다. 면접 진행 규칙(질문 수, 꼬리질문 수, 평가 불가 처리, 다음 행동)은 일반 코드가 정한다 (C §2.3).

### Requirement 5: LLM 출력 검사

**User Story:** C 담당으로서, LLM이 형식이 틀린 답을 주어도 조용히 통과시키지 않고, 한 번 다시 시도한 뒤 원인이 드러나는 오류로 끝내고 싶다.

근거: C §7 "AI 출력 형식 오류", architecture.md §9 "모델 출력 후", AGENTS.md "AI·데이터 규칙", api.md §5

#### Acceptance Criteria

1. THE Interview_Package SHALL Prompt_A·Prompt_B의 출력을 고정 JSON 스키마로 받아 Pydantic으로 검사한다.
2. WHEN 출력이 JSON이 아니거나 스키마 검사를 통과하지 못하면, THE Interview_Package SHALL 같은 요청을 한 번 더 보낸다.
3. IF 다시 보낸 요청의 출력도 검사를 통과하지 못하면, THEN THE Interview_Package SHALL `AI_OUTPUT_INVALID`(retryable true)를 던진다.
4. IF 모델 호출 자체가 실패하면(권한, 한도 초과, 네트워크, SDK 오류), THEN THE Interview_Package SHALL `AWS_SERVICE_ERROR`(retryable true)를 던진다.
5. THE Interview_Package SHALL 출력이 JSON 코드 블록(```json … ```)으로 감싸져 와도 안의 JSON을 꺼내 검사한다.

### Requirement 6: 프롬프트 공통 규칙

**User Story:** 지원자로서, 면접관이 내 자소서에 없는 경험을 지어내거나, 직무와 상관없는 것을 묻거나, 자소서 안의 문장을 지시로 따르지 않았으면 좋겠다.

근거: product.md "제품 원칙" 5·8, tech.md "LLM·데이터 처리 규칙", architecture.md §9·§10-5, 지식 패키지 `06_MOCK_INTERVIEW.md`(결정 3)

#### Acceptance Criteria

1. THE Interview_Package SHALL 직무, 자소서, `profile`, 질문, 답변을 정해진 태그(`<job>`, `<resume>`, `<profile>`, `<question>`, `<answer>`)로 감싸 데이터로만 넘긴다.
2. THE Interview_Package SHALL 데이터 안에 같은 이름의 태그가 들어 있으면 태그로 읽히지 않게 바꾼 뒤 넘긴다.
3. THE Prompt_A AND THE Prompt_B SHALL 태그 안의 지시문을 따르지 말라는 규칙을 담는다.
4. THE Prompt_A AND THE Prompt_B SHALL 질문을 특정 기업의 실제 기출 문제라고 하거나 기출처럼 지어내지 말라는 규칙을 담는다.
5. THE Prompt_A AND THE Prompt_B SHALL 직무와 무관한 요소(외모, 나이, 성별, 출신 지역, 가족, 종교, 혼인 여부 등)를 묻거나 판단 근거로 쓰지 말라는 규칙을 담는다.
6. THE Prompt_A AND THE Prompt_B SHALL 자소서·`profile`·답변에 없는 경험·성과·수치를 사실처럼 질문에 넣지 말라는 규칙을 담는다.
7. THE Interview_Package SHALL 프롬프트마다 버전을 두고, Session의 `promptVersion`에 Prompt_A·Prompt_B 버전을 기록한다.
8. THE Interview_Package SHALL 자소서에 민감정보 마스킹을 적용하지 않는다 (결정 2).

### Requirement 7: 질문 생성 (`generate_questions`)

**User Story:** C 담당으로서, 질문 생성을 Session 없이 부를 수 있는 독립 함수로 두어, 나중에 챗 질문 연습 도구가 같은 함수를 쓰게 하고 싶다.

근거: C ★ "내부 함수"·F-02, architecture.md §5.3·§10-5 (결정 4)

#### Acceptance Criteria

1. THE Interview_Package SHALL `generate_questions(job, resume_text, interview_type, profile=None)`를 Session 없이 부를 수 있는 함수로 둔다.
2. THE `generate_questions` SHALL 입력을 `start_interview`와 같은 규칙(Requirement 8 기준 2)으로 검사한다.
3. THE `generate_questions` SHALL Prompt_A로 Base_Question 3개를 만들고, 각 질문에 `questionId`(`q1`, `q2`, `q3`), `questionType`(`experience` / `knowledge` / `situation`), `question`을 담아 돌려준다.
4. THE `generate_questions` SHALL `questionId`를 코드가 순서대로 붙인다. LLM이 준 ID는 쓰지 않는다.
5. IF LLM이 질문을 3개가 아닌 개수로 주거나, 정해진 유형이 아니거나, 빈 질문이나 같은 질문을 주면, THEN THE `generate_questions` SHALL 그 출력을 스키마 검사 실패로 다룬다 (Requirement 5).

### Requirement 8: 면접 시작 (`start_interview`)

**User Story:** 백엔드 담당으로서, `/start` 뒤에서 `start_interview`를 한 번 부르면 초기 Session과 첫 질문을 받고 싶다.

근거: C ★ `start_interview`, C §5.2 필드 규칙, Contract_Package `InterviewJobContext`·`CareerProfileSummary`(#26, D-12·D-18), `backend/interview_api.py` 242~245행, `docs/db-schema.md` §2.4

#### Acceptance Criteria

1. THE Interview_Package SHALL `start_interview(session_id, job, resume_text, interview_type, camera_consent, profile=None)`를 제공한다.
2. WHEN `session_id`가 비어 있거나, `job`이 앞뒤 공백을 뺀 1~50자가 아니거나, `resume_text`가 50~5,000자가 아니거나, `interview_type`이 `PERSONALITY` / `JOB` / `MIXED`가 아니거나, `camera_consent`가 불리언이 아니거나, `profile`이 null도 아니고 Career_Profile_Summary 검사도 통과하지 못하면, THE `start_interview` SHALL `INVALID_INPUT`을 던진다.
3. THE `start_interview` SHALL `profile` 검사에 Contract_Package의 `CareerProfileSummary`를 쓴다. 같은 규칙을 Interview_Package 안에 따로 만들지 않는다.
4. THE `start_interview` SHALL `generate_questions`로 Base_Question 3개를 만든다.
5. THE `start_interview` SHALL `{"session": ..., "nextQuestion": ...}`를 돌려준다. `nextQuestion`은 `{"questionId": "q1", "answerId": "a-q1-1", "text": ..., "isFollowUp": false}`다.
6. THE `start_interview` SHALL 초기 Session을 `currentIndex` 0, `followUpUsed` false, `answers` 빈 목록, `baseline` null, `scoringVersion` `v1.0`, `modelId`는 `MODEL_ID` 값, `promptVersion`은 Prompt_A·Prompt_B 버전, `currentQuestion`은 첫 질문으로 만든다.
7. THE `start_interview` SHALL 검사를 통과한 `profile`을 카멜 키로 Session에 담고, 질문 생성의 참고 자료로만 쓴다. `needsConfirmation`은 "확인이 필요한 역량"이고 부족이 확정된 역량이 아니다 (Contract_Package `career_summary.py`).

### Requirement 9: 답변 처리 (`process_answer`)

**User Story:** 백엔드 담당으로서, 변환 결과를 넘기면 면접 규칙을 몰라도 다음 행동과 다음 질문을 받고 싶다.

근거: C ★ `process_answer`·"주요 데이터 형식", C §4.2 고정 규칙, C §7 시나리오, `backend/interview_api.py` 248~277행

#### Acceptance Criteria

1. THE Interview_Package SHALL `process_answer(session, answer_result)`를 제공하고 `{"session", "action", "nextQuestion", "lastAnswer"}`를 돌려준다. `action`은 `FOLLOW_UP` / `NEXT_QUESTION` / `REPORT` 중 하나다.
2. IF Session이 이미 끝났거나(기본 질문 3개 처리 완료), `answer_result.answerId`가 Session `currentQuestion.answerId`와 다르거나, `transcription.status`가 `COMPLETED` / `FAILED`가 아니면, THEN THE `process_answer` SHALL `INVALID_INPUT`을 던진다.
3. WHEN `transcription.status`가 `FAILED`이면, THE `process_answer` SHALL 답변을 평가 불가(`TRANSCRIBE_FAILED`)로 기록한다.
4. WHEN `transcription.status`가 `COMPLETED`이고 `text`가 비어 있거나 공백뿐이면, THE `process_answer` SHALL 답변을 평가 불가(`NO_ANSWER`)로 기록한다.
5. WHEN Base_Question의 답변이 Evaluable이고 그 Base_Question에 Follow_Up_Question을 아직 쓰지 않았으면, THE `process_answer` SHALL `judge_follow_up`으로 꼬리질문 필요 여부를 판단한다.
6. WHEN `judge_follow_up`이 꼬리질문이 필요하다고 판단하면, THE `process_answer` SHALL `action` `FOLLOW_UP`과 `nextQuestion` `{"questionId": "{기본 질문 ID}-f", "answerId": "a-{기본 질문 ID}-2", "text": ..., "isFollowUp": true}`를 돌려주고 `followUpUsed`를 true로, `currentQuestion`을 그 꼬리질문으로 바꾼다.
7. THE `process_answer` SHALL Base_Question 하나에 Follow_Up_Question을 최대 1개만 낸다. Follow_Up_Question의 답변 뒤에는 꼬리질문 판단을 하지 않는다.
8. WHEN Base_Question의 답변이 평가 불가이면, THE `process_answer` SHALL 꼬리질문 판단 없이 다음 Base_Question으로 넘어간다.
9. WHEN 다음 Base_Question으로 넘어가고 남은 Base_Question이 있으면, THE `process_answer` SHALL `action` `NEXT_QUESTION`과 `nextQuestion` `{"questionId": "q{n}", "answerId": "a-q{n}-1", "text": ..., "isFollowUp": false}`를 돌려주고 `followUpUsed`를 false로 되돌리고 `currentQuestion`을 그 질문으로 바꾼다.
10. WHEN 3번째 Base_Question(꼬리질문이 있으면 그 답변까지)의 처리가 끝나면, THE `process_answer` SHALL `action` `REPORT`와 `nextQuestion` null을 돌려주고 `currentQuestion`을 null로 바꾼다.
11. THE `process_answer` SHALL `lastAnswer`를 `{"answerId", "evaluable", "reason"}`으로 돌려준다. `reason`은 Evaluable이면 null, 아니면 `NO_ANSWER` 또는 `TRANSCRIBE_FAILED`다.
12. THE `process_answer` SHALL 답변마다 `answerId`, `questionId`, 질문 문장, 꼬리질문 여부, 답변 텍스트, Evaluable, 평가 불가 사유, `timeLimitReached`를 Session `answers`에 쌓는다. 단어별 시간(`words`)은 1차에서 Session에 넣지 않는다.

### Requirement 10: 꼬리질문 판단 (`judge_follow_up`)

**User Story:** 지원자로서, 답변이 추상적이거나 자소서와 다를 때만 짧은 꼬리질문을 받고 싶다.

근거: C F-07, C §7 "꼬리질문 2개 이상 요청 (AI 출력)"

#### Acceptance Criteria

1. THE `judge_follow_up` SHALL 직무, 자소서, Base_Question, 답변 텍스트를 받아 Prompt_B로 꼬리질문 필요 여부를 판단한다.
2. THE Prompt_B SHALL 답변이 추상적이거나(구체적 행동·결과가 없음) 자소서 내용과 다를 때만 꼬리질문이 필요하다고 판단하게 한다.
3. WHEN LLM이 꼬리질문을 2개 이상 주면, THE `judge_follow_up` SHALL 첫 번째 하나만 쓴다.
4. IF LLM이 꼬리질문이 필요하다고 하면서 질문을 하나도 주지 않으면, THEN THE `judge_follow_up` SHALL 그 출력을 스키마 검사 실패로 다룬다 (Requirement 5).

### Requirement 11: 아직 없는 함수의 임시 구현

**User Story:** 백엔드 담당으로서, 1차가 머지된 뒤 배포해도 음성·리포트·카메라 함수 호출에서 면접이 깨지지 않았으면 좋겠다.

근거: 결정 6, `backend/interview_stub.py`(PR #31 반영본) 36~99행, `backend/interview_api.py` 234·255·284~291·387·421~425행, `docs/db-schema.md` §2.4

#### Acceptance Criteria

1. THE Interview_Package SHALL Temporary_Implementation 6개를 `backend/interview_stub.py`의 같은 이름 함수와 같은 입출력으로 둔다.
2. THE `start_transcription` Temporary_Implementation SHALL `(s3_uri, job_name, media_format, output_bucket, output_key)` 5개 인자를 받고, 대역과 같이 `output_bucket`의 `output_key`에 가짜 변환 결과 JSON을 쓴 뒤 `job_name`을 돌려준다.
3. THE `analyze_face` Temporary_Implementation SHALL `valid`, `reason`, `gaze`, `head`, `eyesOpen`을 돌려준다. 빈 이미지면 `valid` false, `reason` `NO_FACE`, 나머지는 null이다.
4. THE `compute_baseline` Temporary_Implementation SHALL 받은 목록 중 `valid`가 true인 항목이 3개 미만이면 `None`을, 3개 이상이면 고정 기준값을 돌려준다.
5. THE Temporary_Implementation SHALL `start_transcription`의 S3 쓰기 외에는 AWS 서비스를 부르지 않는다.
6. THE Temporary_Implementation SHALL 2~4차에서 바꿀 함수임을 코드 설명에 적고, 실제 구현과 다른 점(고정 값을 돌려줌, `get_transcription_result`가 S3 결과 파일을 읽지 않음)을 적는다.

### Requirement 12: 로그

**User Story:** 지원자로서, 내 자소서와 답변이 로그에 남지 않았으면 좋겠다.

근거: C §8, architecture.md §9 "로그", AGENTS.md "환경·보안"

#### Acceptance Criteria

1. THE Interview_Package SHALL 로그에 단계 이름, 처리 시간, 시도 횟수, 오류 코드만 남긴다.
2. THE Interview_Package SHALL 로그와 예외 메시지에 자소서, 답변, 질문 문장, `profile`, LLM 입력·출력 원문을 남기지 않는다.
3. THE Interview_Package SHALL `print`를 쓰지 않고 표준 `logging`만 쓴다.

### Requirement 13: 샘플 데이터

**User Story:** C 담당으로서, Bedrock과 DB 없이 같은 데이터로 함수를 반복 시험하고 싶다.

근거: C §7 "함수 단위 테스트", 결정 1(D-37), api.md §6.2, Contract_Package `contracts/fixtures/valid/CareerProfileSummary.json`, product.md "제품 원칙" 7

#### Acceptance Criteria

1. THE Sample_Data SHALL 데이터 분석 직무 가상 자소서 1명분(50~5,000자)을 담는다.
2. THE Sample_Data SHALL 실명, 연락처, 주민번호, 실제 학교·회사 이름처럼 실존 인물을 특정할 수 있는 정보를 담지 않는다.
3. THE Sample_Data SHALL 정상 답변, 무응답(빈 텍스트), 변환 실패 답변의 Answer_Result를 담는다.
4. THE Sample_Data SHALL Fake_LLM이 돌려줄 Prompt_A·Prompt_B 응답(정상, 꼬리질문 2개 이상, 형식 오류)을 담는다.
5. THE Sample_Data SHALL Career_Profile_Summary 형식의 `profile` 예시를 담고, Contract_Package의 `data-analysis-demo` 예시와 같은 내용으로 맞춘다.

### Requirement 14: 테스트

**User Story:** C 담당으로서, Bedrock 없이 한 명령으로 1차 완료 조건을 확인하고 싶다.

근거: C §7, 이슈 #25 완료 조건, AGENTS.md "코딩 규칙"(mock·fixture)

#### Acceptance Criteria

1. THE Interview_Package SHALL 단위 테스트를 `ai/interview/tests/`에 두고, Fake_LLM과 가짜 S3 클라이언트로 Bedrock·AWS·네트워크 없이 돌린다.
2. THE 테스트 SHALL Sample_Data로 `start_interview` → `process_answer` 반복 → `REPORT`까지 한 바퀴를 확인한다.
3. THE 테스트 SHALL C §7 시나리오 중 무응답, Transcribe 실패, 꼬리질문 2개 이상 요청, AI 출력 형식 오류를 각각 확인한다.
4. THE 테스트 SHALL Public_Function 8개를 Backend_Caller의 현재 호출 형태(`start_transcription` 위치 인자 5개 포함)로 부를 수 있는지, Interview_Package가 `backend/`를 import하지 않는지 확인한다.
5. THE 테스트 SHALL 로그에 자소서·답변 원문이 남지 않는지 확인한다.
6. WHERE 개발자가 실제 Bedrock 확인을 켜면(환경변수로 명시), THE 테스트 SHALL 가상 자소서로 Prompt_A를 실제 모델에 보내 질문 3개를 받는다. 기본 실행에서는 이 테스트를 건너뛴다.

### Requirement 15: 명세 문서 갱신

**User Story:** 팀원으로서, C 명세의 예시와 시연 직무가 실제 Session 형식과 팀 결정(D-37)과 같았으면 좋겠다.

근거: 결정 1·9·10, `docs/개발계획서3.md` ★ 주요 데이터 형식, §3 "시연" 행, §5.2·§5.4 예시, §7 "질문 품질"

#### Acceptance Criteria

1. THE C 명세 SHALL ★ 주요 데이터 형식의 `session` 예시에 `modelId`, `promptVersion`, `currentQuestion`을 넣는다.
2. THE C 명세 SHALL ★ `session` 예시와 §5.2 `/start` 요청 예시, §5.4 리포트 예시의 직무(`job`, `targetJob`)를 데이터 분석으로 바꾼다.
3. THE C 명세 SHALL §3 사용 데이터의 시연 행을 "가상 자소서 1명분 (데이터 분석)"으로 고친다.
4. THE C 명세 SHALL §7의 질문 품질 확인 문장을 데이터 분석 직무 가상 자소서 기준으로 고친다.
5. THE C 명세 SHALL §5.2 `/start` 요청 예시의 `profile`을 Career_Profile_Summary 형식(`projects`, `skills`, `needsConfirmation`)으로 바꾼다.
