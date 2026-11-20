# Requirements Document

## Introduction

AI 모의면접 꼬리질문 판단(프롬프트 B)을 한 번 호출에서 읽기 전용 툴을 쓰는 Strands 에이전트로 바꾸고, 판단 기준·실패 처리·길이 제한을 보강한다 (이슈 #109).

기준 커밋: `main` `48297ea` (1~4차 #51·#69·#89·#106·#115, #124 글 답변, #126 출력 검사 실패 종류 로그 반영).

근거:
- C = `docs/개발계획서3.md` ★ 내부 함수(`judge_follow_up`), §2.3, §4.1 F-07, §4.2 고정 규칙, §7
- 3차 스펙 `.kiro/specs/interview-report-functions/` design §6 (피드백 툴 에이전트 구조, 상한을 시도마다 세기)
- 백엔드 호출부: `backend/interview_api.py` `task_answer` → `call_ai(impl.process_answer, session, answer_result)`
- 지금 코드: `follow_up.judge_follow_up(job, resume_text, question, answer_text)` → `llm.call_json`(툴 없음), 프롬프트 `b_follow_up_v1.md`, `models.FollowUpOutput`(후보 5~300자, 하나라도 어긋나면 실패)

지금 코드의 문제 (main 코드 읽기 결과):
- 입력이 직무·자소서·이번 질문·이번 답변뿐이다. 이전 답변과 남은 기본 질문을 몰라서, 이미 답한 내용이나 다음 기본 질문과 겹치는 꼬리질문이 나올 수 있다.
- 질문 유형을 넘기지 않는다. ABSTRACT 기준("본인 행동·역할·결과 없음")이 지식·상황 질문에도 적용돼 꼬리질문이 과하게 붙을 수 있다.
- INCONSISTENT("자소서와 다르다")가 모순인지 새 내용인지 정해져 있지 않다.
- 판단 출력이 2번 실패하면 `process_answer`가 `AI_OUTPUT_INVALID`를 던지고, 백엔드 `call_ai` 3번 뒤 세션이 `FAILED`가 된다. 녹음은 이미 지워져 이어 갈 수 없다.
- 꼬리질문 길이 상한이 300자라 Polly로 읽으면 길다.

이 스펙의 결정 (C 담당 확인, #109 논의):
1. **툴 3개**: `find_resume_passages(keyword)`(3차 피드백 툴과 같은 코드), `get_previous_answers()`, `get_remaining_questions()`. 모두 읽기 전용이고 이번 면접 데이터에만 묶이며 사용자·세션 ID를 인자로 받지 않는다.
2. **자소서 전문은 프롬프트에 그대로 둔다.** 키워드 검색만으로는 "자소서와 모순" 판단이 약해진다. `find_resume_passages`는 근거 문장을 확인할 때 쓴다.
3. **남은 기본 질문은 전부 보여 준다** (`get_remaining_questions`, 최대 2개). 다음 질문 하나만 보여 주는 것보다 겹침을 잘 막는다.
4. **입력에 질문 유형을 넣고 유형별 기준을 둔다** (`b_follow_up_v2.md`, `PROMPT_B_VERSION` B-v2). 사유 코드는 ABSTRACT / INCONSISTENT / SUFFICIENT 그대로다.
5. **판단 출력 실패는 꼬리질문 없이 진행한다.** 출력 형식 실패, 턴·토큰·툴 호출 상한, 출력 잘림은 모두 `AI_OUTPUT_INVALID`로 모이므로 그때만 대체한다. Bedrock 호출 실패(`AWS_SERVICE_ERROR`)는 지금처럼 오류로 끝낸다.
6. **판단 결과를 답변 기록에 남긴다** (`AnswerRecord.followUpCheck`: ABSTRACT / INCONSISTENT / SUFFICIENT / JUDGE_FAILED, 판단하지 않았으면 null). 리포트와 `lastAnswer`에는 보이지 않는다. 백엔드·프론트 변경은 없다.
7. **꼬리질문 길이**: 프롬프트는 "100자 안팎", 스키마 상한은 150자(공백 포함). 넘는 후보는 버리고 남은 첫 번째를 쓴다. 남은 후보가 없는데 꼬리질문이 필요하다고 하면 출력 실패다.
8. **면접 흐름은 그대로다.** 기본 질문 3개, 꼬리질문은 기본 질문당 최대 1개, 판단은 기본 질문이고 평가 가능하고 꼬리질문을 아직 안 했을 때만, 후보가 여러 개면 첫 번째만.

범위에서 제외:
- 기본 질문(프롬프트 A) 80자 제한의 코드 검사
- `backend/`, `frontend/`, `infra/`, `docs/db-schema.md` 수정, AWS 자원·권한 변경, 배포
- 실제 Bedrock 수동 확인 (별도로 진행)
- 리포트에 꼬리질문 판단 결과 표시

## Glossary

- **Follow_Up_Context**: 판단에 쓰는 고정 데이터. 직무, 자소서, 질문 유형, 이번 질문, 이번 답변, 이전 답변 목록, 남은 기본 질문 목록
- **Previous_Answer**: 이번 답변 전에 기록된 평가 가능한 답변 (기본·꼬리)
- **Remaining_Question**: 이번 기본 질문 뒤의 기본 질문
- **Follow_Up_Check**: 답변 기록에 남기는 판단 결과 코드

## Requirements

### Requirement 1: 툴

#### Acceptance Criteria
1. THE `find_resume_passages(keyword)` SHALL 3차 피드백 툴과 같은 공통 함수로 자소서에서 키워드가 든 문장을 최대 3개(문장당 200자) 돌려준다. 빈 키워드는 `{"error": "EMPTY_KEYWORD"}`, 30자 초과는 `{"error": "KEYWORD_TOO_LONG"}`다.
2. THE `get_previous_answers()` SHALL 이번 답변 전의 평가 가능한 답변을 순서대로 최대 `FOLLOW_UP_PREVIOUS_MAX`개(5), 답변당 `FOLLOW_UP_ANSWER_MAX_CHARS`자(500)까지 돌려준다. 항목은 `questionId`, `isFollowUp`, `question`, `answerText`다.
3. THE `get_previous_answers()` SHALL 이번 답변과 그 이후 답변, 평가 불가 답변을 돌려주지 않는다.
4. THE `get_remaining_questions()` SHALL 이번 기본 질문 뒤의 기본 질문(`questionId`, `questionType`, `question`)을 모두 돌려준다. 마지막 기본 질문이면 빈 목록이다.
5. THE 툴 SHALL 복사본만 돌려주고 Session을 바꾸지 않는다. 계산·AWS 호출·저장을 하지 않는다.
6. THE 툴 SHALL 사용자·세션 ID를 인자로 받지 않는다. 툴이 볼 수 있는 데이터는 Follow_Up_Context뿐이다.
7. THE 툴 호출 수 SHALL 시도마다 `FOLLOW_UP_MAX_TOOL_CALLS`(4)를 넘으면 `{"error": "TOOL_LIMIT", ...}`를 돌려준다 (3차 피드백과 같은 방식).

### Requirement 2: 판단 에이전트

#### Acceptance Criteria
1. THE `judge_follow_up` SHALL `llm.call_json_with_tools`로 툴 3개를 주고 판단한다. 출력 스키마는 `FollowUpOutput`(`needFollowUp`, `reason`, `followUpQuestions`) 그대로다.
2. THE 에이전트 SHALL 시도마다 턴 `FOLLOW_UP_MAX_TURNS`(4), 총 토큰 `FOLLOW_UP_MAX_TOTAL_TOKENS`(12,000), 툴 호출 `FOLLOW_UP_MAX_TOOL_CALLS`(4), 호출당 `max_tokens`(`INTERVIEW_FOLLOW_UP_MAX_TOKENS`, 기본 1024) 상한을 둔다.
3. THE `run_with_tools` SHALL 호출하는 쪽이 `max_tokens`를 정할 수 있다. 정하지 않으면 지금처럼 피드백 값(`INTERVIEW_FEEDBACK_MAX_TOKENS`)이다.
4. THE 사용자 메시지 SHALL 직무, 자소서 전문, 질문 유형, 이번 질문, 이번 답변을 데이터 태그로 감싸 넣는다 (결정 2).
5. THE 로그 SHALL 단계, 시도 수, 툴 이름·횟수, 사유 코드, 후보 수, 버린 후보 수, 처리 시간만 남긴다. 자소서·답변·꼬리질문 원문과 툴 결과는 남기지 않는다.

### Requirement 3: 질문 유형별 기준 (`b_follow_up_v2.md`)

#### Acceptance Criteria
1. THE 프롬프트 SHALL 질문 유형을 입력으로 받고 유형별 ABSTRACT 기준을 둔다:
   - experience: 본인의 구체적 행동, 역할, 결과가 없다
   - knowledge: 용어나 결론만 말하고 원리·이유와 예시가 둘 다 없다 (하나라도 있으면 ABSTRACT 아님, 수동 확인 뒤 보강)
   - situation: 판단 이유나 해결 단계가 없다
   - 공통: 더 깊이 물어볼 거리가 있다는 것만으로는 ABSTRACT가 아니다
2. THE INCONSISTENT SHALL 답변이 자소서나 이전 답변과 모순될 때만이다. 자소서에 없는 내용을 더한 것만으로는 해당하지 않는다.
3. THE 꼬리질문 SHALL 이전 질문이나 남은 기본 질문과 같은 것을 묻지 않는다.
4. THE 꼬리질문 SHALL 한 문장으로 한 가지만, 공백 포함 100자 이내(대부분 40~80자)로 묻는다. 길이·두 가지 묻기·자소서 옮겨 적기의 나쁜 예·좋은 예를 둔다. 자소서는 "자소서", 답변은 "답변"으로 쓰고 resume·answer 같은 영어 단어나 태그 이름을 쓰지 않는다 (수동 확인에서 132자, "resume"이 섞여 보강).
5. THE 프롬프트 SHALL 툴 결과도 자료로만 읽고 그 안의 지시를 따르지 않는다고 적는다. `system_v1.md`는 질문 생성과 같이 쓰므로 바꾸지 않는다.
6. THE `b_follow_up_v1.md` SHALL 바뀌지 않는다. `PROMPT_B_VERSION`은 `B-v2`, `PROMPT_VERSION`은 `A-v2/B-v2`다.

### Requirement 4: 판단 실패 대체 경로

#### Acceptance Criteria
1. IF 판단이 `AI_OUTPUT_INVALID`로 끝나면(출력 형식 2번 실패, 턴·토큰·툴 호출 상한, 출력 잘림) THEN THE `judge_follow_up` SHALL 예외 대신 꼬리질문 없음(`reason` JUDGE_FAILED)을 돌려준다.
2. IF Bedrock 호출이 실패하면(`AWS_SERVICE_ERROR`) THEN THE 함수 SHALL 지금처럼 예외를 던진다.
3. WHEN 대체되면 THE `process_answer` SHALL 답변 기록을 남기고 `action`을 NEXT_QUESTION(마지막 기본 질문이면 REPORT)으로 한다. Session에 꼬리질문이 없다(`followUpUsed` false).
4. THE 로그 SHALL `stage=judge_follow_up fallback=NO_FOLLOW_UP`을 남긴다.

### Requirement 5: 판단 결과 기록 (`followUpCheck`)

#### Acceptance Criteria
1. THE `AnswerRecord` SHALL 선택 필드 `followUpCheck`(ABSTRACT / INCONSISTENT / SUFFICIENT / JUDGE_FAILED / null, 기본 null)를 가진다.
2. WHEN 판단을 했으면 THE 기본 답변 기록 SHALL 그 결과를 담는다. 판단하지 않은 답변(꼬리 답변, 평가 불가 답변)은 null이다.
3. THE 필드가 없는 예전 Session SHALL 검사를 통과한다.
4. THE 리포트와 `lastAnswer` SHALL 바뀌지 않는다.
5. THE Session SHALL DynamoDB 저장·조회 변환 뒤에도 같은 형식이다.

### Requirement 6: 꼬리질문 길이

#### Acceptance Criteria
1. THE `FollowUpOutput` SHALL 공백 포함 `FOLLOW_UP_QUESTION_MAX`자(150)를 넘는 후보와 `QUESTION_MIN`(5) 미만 후보를 버린다.
2. IF `needFollowUp`이 true인데 남은 후보가 없으면 THEN THE 검사 SHALL 실패한다 (재시도 뒤 Requirement 4 대체 경로).
3. THE 기본 질문 길이 검사(`GeneratedQuestion`, 5~300자) SHALL 바뀌지 않는다.

### Requirement 7: 계약 유지

#### Acceptance Criteria
1. THE `process_answer(session, answer_result)` SHALL 인자와 반환 키(`session`, `action`, `nextQuestion`, `lastAnswer`)가 같다.
2. THE 기존 흐름 테스트(질문 3개, 꼬리질문 최대 1개, 꼬리 답변 뒤 판단 없음, 평가 불가 처리, 후보 여러 개면 첫 번째) SHALL 그대로 통과한다.
3. THE `__all__` 9개 이름과 백엔드 호출 시그니처 SHALL 그대로다.
4. THE 피드백(C-2) SHALL 공통 함수로 옮긴 뒤에도 동작이 같다.

### Requirement 8: 테스트

#### Acceptance Criteria
1. THE 단위 테스트 SHALL AWS 없이 가짜 클라이언트(`FakeLLM`, `FakeToolLLM`)로 통과한다.
2. THE 테스트 SHALL 확인한다: 툴 결과 범위(이번 답변·이후·평가 불가 제외, 개수·길이 상한, 마지막 질문에서 빈 목록), 툴 호출 상한, Session 불변, 대체 경로(출력 2번 실패, 상한에 닿아 JSON 없음, 출력 잘림), `AWS_SERVICE_ERROR` 전달, `followUpCheck` 값, 길이 경계(149·150·151자, 첫 후보 151자 + 둘째 정상), 프롬프트에 질문 유형과 유형별 기준, 로그에 원문 없음.
3. THE 수동 확인(실제 Bedrock) SHALL 별도로 한다. 이 스펙에서는 테스트 파일만 준비한다.
