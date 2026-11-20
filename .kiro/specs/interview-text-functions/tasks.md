# Implementation Plan

기준: `requirements.md`, `design.md` (`main` `a556a31` 기준). 브랜치 `feat/be/#25-interview-text-functions`. 테스트 실행은 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q` (design §12).

- [x] 1. 패키지 뼈대와 오류
  - [x] 1.1 `ai/interview/` 뼈대를 만든다
    - `__init__.py`(빈 `__all__`), `requirements.txt`(`strands-agents`, `pydantic`), `requirements-dev.txt`(`-r requirements.txt`, `-r ../../contracts/requirements.txt`, `pytest`), `tests/conftest.py`(`ai/`와 `contracts/src/`를 `sys.path` 앞에 추가), `.gitkeep` 삭제
    - _Requirements: 1.1, 1.2, 1.6, 14.1_
  - [x] 1.2 `errors.py`에 `InterviewError(code, message, retryable=None)`와 코드 3개를 만든다. `retryable`을 주지 않으면 코드별 기본값을 쓴다
    - `tests/test_errors.py`: 코드별 기본값, `code`·`message`·`retryable` 속성
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 2. 설정과 데이터 모델
  - [x] 2.1 `settings.py`, `versions.py`를 만든다
    - `model_id()`(비면 `AWS_SERVICE_ERROR` retryable false), `region()`, `max_tokens()`(`INTERVIEW_MAX_TOKENS`, 기본 1024), 입력·출력 길이 상수, `SCORING_VERSION`, `PROMPT_A_VERSION`, `PROMPT_B_VERSION`, `PROMPT_VERSION`
    - 값은 호출할 때 읽는다
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.7_
  - [x] 2.2 `models.py`에 Pydantic v2 모델을 만든다 (design §4)
    - `StartInterviewInput`(`profile`은 `team07_contracts.CareerProfileSummary`), `Question`, `NextQuestion`, `AnswerRecord`, `Session`(`modelId`, `promptVersion`, `currentQuestion` 포함), `Word`, `Transcription`, `AnswerResult`, `GeneratedQuestion`, `QuestionsOutput`, `FollowUpOutput`
    - 카멜 별칭, Session·Answer_Result는 `extra="forbid"`
    - 계약 검사 실패를 `INVALID_INPUT`으로 바꾸는 변환 함수 (실패 필드 이름만 로그)
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 8.3_
  - [x] 2.3 `tests/test_models.py`를 쓴다
    - 카멜 직렬화, 모르는 키 거절, `job`·`resume_text` 경계값, `camera_consent` 엄격 불리언, `profile` 계약 검사(정상, C §5.2 예시 형식 거절, 항목 수 초과 거절), `QuestionsOutput` 개수·중복, `FollowUpOutput`의 필요=true·질문 0개 거절
    - _Requirements: 3.4, 7.5, 8.2, 8.3, 10.4_

- [x] 3. 임시 구현과 공개 함수 내보내기
  - [x] 3.1 `placeholders.py`에 Temporary_Implementation 6개를 만든다 (design §9)
    - `backend/interview_stub.py`(PR #31 반영본)와 같은 입출력
    - `start_transcription`은 인자 5개, `_s3_client()`로 가짜 결과 JSON을 `output_bucket`·`output_key`에 쓴다 (`boto3` 지연 import)
    - `analyze_face`는 `eyesOpen` 포함, `compute_baseline`은 유효 3개 미만이면 `None`
    - 함수 설명에 "임시 구현, N차 PR에서 교체"와 실제 구현과 다른 점
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_
  - [x] 3.2 `__init__.py`에서 공개 함수 8개와 `InterviewError`를 내보낸다. `start_interview`·`process_answer`는 이 단계에서 `flow.py`의 빈 함수(`NotImplementedError`)로 둔다
    - _Requirements: 1.1_
  - [x] 3.3 `tests/test_package.py`, `tests/test_placeholders.py`를 쓴다
    - `__all__` 이름, 백엔드 호출 형태로 `inspect.signature().bind`(`start_interview` 위치 인자 6개, `start_transcription` 5개 등), AST로 `backend`·`interview_stub`·`common` import 없음, `MODEL_ID`를 지운 상태에서 `import interview` 성공
    - 임시 구현의 반환 값, 가짜 S3 클라이언트에 기록된 `put_object` 인자, `compute_baseline` 유효 2개 → `None`·3개 → 기준값
    - _Requirements: 1.3, 1.4, 1.5, 11.2, 11.3, 11.4, 11.5, 14.1, 14.4_

- [x] 4. LLM 계층
  - [x] 4.1 `llm.py`에 `LLMClient` 인터페이스, `extract_json`, `call_json`(1회 재시도)을 만든다 (design §6.1, §6.3)
    - 모델 호출 예외는 `AWS_SERVICE_ERROR`(retryable true), 2회 검사 실패는 `AI_OUTPUT_INVALID`(retryable true)
    - 로그는 stage·attempt·errorCode·durationMs만
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 12.1_
  - [x] 4.2 `StrandsLLMClient`를 만든다 (design §6.2)
    - `strands`는 지연 import, `BedrockModel`은 프로세스에서 한 번, `Agent`는 호출마다 새로 만들고 `tools=[]`, `callback_handler=None`
    - 설치된 `strands-agents` 버전에서 `callback_handler=None`과 `str(result)` 동작을 확인한다. 다르면 design §6.2를 고친다
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_
  - [x] 4.3 `tests/fakes.py`에 Fake_LLM과 가짜 S3 클라이언트, `tests/test_llm.py`를 쓴다
    - 코드 블록 JSON 추출, 첫 실패 후 성공, 2회 실패, 호출 예외, `MODEL_ID` 없음, `StrandsLLMClient`가 `strands` 없이 import되는지
    - _Requirements: 4.2, 5.2, 5.3, 5.4, 5.5, 14.1_

- [x] 5. 프롬프트
  - [x] 5.1 `prompts/system_v1.md`, `a_questions_v1.md`, `b_follow_up_v1.md`를 쓴다 (design §7)
    - 데이터 태그 규칙, 06 제약(가짜 기출 금지, 직무 무관 요소 금지), 지어내지 않기, `needsConfirmation`은 확인 질문 소재로만, JSON만 출력, 출력 예시
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 8.7, 10.2_
  - [x] 5.2 `prompting.py`에 `wrap`(태그 무력화), `profile` JSON 삽입, 프롬프트 파일 읽기·자리표시 채우기를 만든다. `Path(__file__).parent / "prompts"`로 읽는다
    - _Requirements: 6.1, 6.2, 6.8_
  - [x] 5.3 `tests/test_prompting.py`를 쓴다
    - 데이터 안 `</resume>` 무력화, 완성된 프롬프트에 06 제약·데이터 규칙 문장이 들어 있는지, `profile` JSON이 `<profile>` 안에 들어가는지, `PROMPT_VERSION` 값
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.7_

- [x] 6. 샘플 데이터
  - [x] 6.1 `samples/`를 만든다 (design §13)
    - 데이터 분석 가상 자소서(실명·연락처·실제 학교·회사 이름 없음), `profile_data_analysis.json`(계약 예시 `data-analysis-demo`와 같은 내용), 답변 4종, LLM 응답 7종
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [x] 7. 질문 생성과 면접 시작
  - [x] 7.1 `questions.py`에 `generate_questions(job, resume_text, interview_type, profile=None, *, llm=None)`를 만든다
    - 입력 검사(`StartInterviewInput`과 같은 규칙), Prompt_A 호출, `questionId` `q1`~`q3` 부여
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 7.2 `tests/test_questions.py`를 쓴다
    - Session 없이 호출, 질문 3개와 ID, 질문 2개 응답 2번이면 `AI_OUTPUT_INVALID`, 잘못된 입력은 LLM을 부르지 않고 `INVALID_INPUT`
    - _Requirements: 7.1, 7.3, 7.4, 7.5_
  - [x] 7.3 `flow.py`에 `start_interview`를 만든다 (design §5.1)
    - 초기 Session(`currentIndex` 0, `followUpUsed` false, `answers` [], `baseline` null, `scoringVersion`, `modelId`, `promptVersion`, `currentQuestion` q1, 검사한 `profile`)과 `nextQuestion`
    - _Requirements: 8.1~8.7, 3.3_

- [ ] 8. 꼬리질문 판단과 답변 처리
  - [ ] 8.1 `follow_up.py`에 `judge_follow_up`을 만든다. 꼬리질문이 여러 개면 첫 번째만 쓴다
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [ ] 8.2 `flow.py`에 `process_answer`를 만든다 (design §5.2)
    - 끝난 면접·`answerId` 불일치·`IN_PROGRESS`는 `INVALID_INPUT`, `TRANSCRIBE_FAILED`·`NO_ANSWER` 처리, 꼬리질문 최대 1개, `FOLLOW_UP`/`NEXT_QUESTION`/`REPORT`, `currentQuestion` 갱신, `answers` 기록, 입력 Session 불변
    - _Requirements: 9.1~9.12, 3.5_
  - [ ] 8.3 `tests/test_flow.py`를 쓴다 (design §12 시나리오 대응)
    - 시작(`profile` 있음·없음), 한 바퀴(q1 꼬리질문 포함 → `REPORT`), 무응답, 변환 실패, 꼬리질문 2개 이상, 꼬리질문 답변 뒤 판단 없음, 평가 불가 기본 질문 뒤 판단 없음, 끝난 면접, `answerId` 불일치, 꼬리질문 판단 형식 오류 시 `AI_OUTPUT_INVALID`, 입력 Session 불변
    - _Requirements: 8.6, 9.1~9.12, 10.3, 14.2, 14.3_

- [ ] 9. 백엔드 흐름 재현과 로그
  - [ ] 9.1 `tests/test_backend_flow.py`를 쓴다
    - `start_interview` → `synthesize_question` → `start_transcription`(가짜 S3) → `get_transcription_result` 결과로 `process_answer` 반복 → `compute_baseline` → `generate_report`. 단계마다 `json.dumps`/`json.loads` 왕복
    - _Requirements: 1.5, 3.6, 11.1, 14.2_
  - [ ] 9.2 `tests/test_logging.py`를 쓴다. `caplog`으로 샘플 자소서·답변·질문 문장·`profile` 항목이 로그에 없는지, `print`를 쓰지 않는지(AST) 확인한다
    - _Requirements: 12.1, 12.2, 12.3, 14.5_

- [ ] 10. 실제 Bedrock 확인
  - [ ] 10.1 `tests/test_bedrock_manual.py`를 쓴다. `RUN_BEDROCK=1`과 `MODEL_ID`가 있을 때만 실행하고 기본은 건너뛴다
    - _Requirements: 14.6_
  - [ ] 10.2 사용자 확인 후 `aws login` 상태에서 `MODEL_ID=global.anthropic.claude-haiku-5-5`(`infra/config.sh` 기본값)로 10.1을 실행하고, 질문 3개가 샘플 자소서 내용을 반영하는지 본다. 결과 문장은 커밋하지 않고 PR 본문에 요약만 적는다
    - _Requirements: 14.6_

- [ ] 11. 명세 문서 (`docs/개발계획서3.md`, design §14)
  - [ ] 11.1 ★ 주요 데이터 형식의 `session` 예시에 `modelId`, `promptVersion`, `currentQuestion`을 넣고 `job`을 데이터 분석으로 바꾼다
    - _Requirements: 15.1, 15.2_
  - [ ] 11.2 §5.2 `/start` 요청 예시의 `job`·`targetJob`, §5.4 리포트 예시의 `job`을 데이터 분석으로 바꾼다
    - _Requirements: 15.2_
  - [ ] 11.3 §3 시연 행과 §7 질문 품질 문장을 데이터 분석으로 고친다
    - _Requirements: 15.3, 15.4_
  - [ ] 11.4 §5.2 `/start` 요청 예시의 `profile`을 계약 `CareerProfileSummary` 형식(`projects`, `skills`, `needsConfirmation`, 계약 예시 `data-analysis-demo`와 같은 내용)으로 바꾸고, 필드 규칙 표의 `profile` 행을 계약 이름으로 고친다
    - _Requirements: 15.5_

- [ ] 12. 마무리
  - [ ] 12.1 전체 테스트를 실행하고 결과(통과 수, 건너뛴 수)를 PR 본문용으로 기록한다
    - _Requirements: 14.1~14.5_
  - [ ] 12.2 PR 참고 사항에 백엔드 담당 요청을 적는다
    - 머지 뒤 배포하면 `/health`의 `interviewImpl`이 `interview`인지 확인
    - Session에 새 필드 3개(`modelId`, `promptVersion`, `currentQuestion`)가 생김 (백엔드 코드 변경 없음)
    - 백엔드 담당 요청: `/start`에서 `profile`을 `team07_contracts.CareerProfileSummary`로 먼저 검사해 400 `INVALID_INPUT`을 돌려주기. 지금은 검사 없이 202를 주고(`backend/interview_api.py` 336행), 뒤에서 `start_interview`가 거절하면 세션이 `FAILED`가 된다 (design §15 열린 질문 1)
    - _Requirements: 1.5, 8.3_
