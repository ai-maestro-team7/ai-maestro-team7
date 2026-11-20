# Implementation Plan

기준: 이 폴더의 `requirements.md`, `design.md`, 이슈 #109. 브랜치 `feat/be/#109-follow-up-agent` (최신 `main` `48297ea`에서). 테스트는 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q`.

규칙: 코드는 `ai/interview/` 안에서만 바꾼다 (예외 `.kiro/specs/`, `docs/개발계획서3.md`). 커밋마다 전체 테스트 결과와 바뀐 파일 목록을 남긴다. AWS는 부르지 않는다.

- [x] 0. 스펙
  - [x] 0.1 requirements·design·tasks (결정 1~8)
  - 커밋: `docs: 꼬리질문 판단 에이전트 스펙 추가`

- [x] 1. 공통 모듈 분리 (동작 변경 없음)
  - [x] 1.1 `tools.py` `search_resume`, `ToolUsage` (design §3). `feedback.py`가 불러 쓰고 기존 이름을 다시 내보낸다
  - [x] 1.2 `test_tools.py`, 기존 `test_feedback.py`·`test_llm.py` 그대로 통과
    - _Requirements: 1.1, 1.7, 7.4_
  - 커밋: `refactor: 자소서 문장 찾기와 툴 호출 횟수 세기를 공통 모듈로 분리` (590 passed 5 skipped)

- [ ] 2. 길이 제한·대체 경로·판단 결과 기록 (아직 한 번 호출 방식)
  - [ ] 2.1 `settings.FOLLOW_UP_QUESTION_MAX` 150, `models.FollowUpOutput` 후보 버리기 (design §6)
  - [ ] 2.2 `models.AnswerRecord.follow_up_check`, `flow.process_answer` 판단을 기록 추가 전으로, `followUpCheck` 기록 (design §5)
  - [ ] 2.3 `follow_up.judge_follow_up` `AI_OUTPUT_INVALID` → JUDGE_FAILED 대체 (design §4.3)
  - [ ] 2.4 `test_models.py`·`test_flow.py`·`test_samples.py`·`test_backend_flow.py` 수정, 대체 경로 테스트
    - _Requirements: 4.1~4.4, 5.1~5.5, 6.1~6.3, 7.1~7.3_
  - 커밋: `feat: 꼬리질문 길이 제한과 판단 실패 시 꼬리질문 없이 진행`

- [ ] 3. 판단 에이전트
  - [ ] 3.1 `llm.py` `run_with_tools(max_tokens)`, `call_json_with_tools(max_tokens)`, `settings` 상한·`follow_up_max_tokens()` (design §4.4·§8)
  - [ ] 3.2 `follow_up.py` `FollowUpContext`, `build_follow_up_context`, `make_follow_up_tools`, `judge_follow_up` 에이전트 (design §4)
  - [ ] 3.3 `prompts/b_follow_up_v2.md`, `prompting.follow_up_prompt(question_type)`, `versions` B-v2 (design §7)
  - [ ] 3.4 `fakes.FakeLLM.run_with_tools`, `test_follow_up.py`, `test_llm.py`·`test_prompting.py`·`test_flow.py`·`test_settings.py`·`test_logging.py` 수정
    - _Requirements: 1.2~1.7, 2.1~2.5, 3.1~3.6, 8.1~8.2_
  - 커밋: `feat: 꼬리질문 판단을 툴 쓰는 에이전트로 보강`

- [ ] 4. 수동 확인 준비 (실행은 나중, 사람이)
  - [ ] 4.1 `test_bedrock_manual.py`에 꼬리질문 판단 테스트 추가 (`RUN_BEDROCK=1`일 때만)
    - 샘플: 자소서와 모순된 답변, 지식 질문에 원리를 설명한 답변, 추상적인 경험 답변
    - 출력: 판단 결과, 시간, 턴·툴 호출, 꼬리질문 길이
    - _Requirements: 8.3_
  - 커밋: `test: 꼬리질문 판단 수동 확인 테스트 추가`

- [ ] 5. 문서와 PR
  - [ ] 5.1 `docs/개발계획서3.md` ★·§2.3·§4.1 F-07·§4.2·§7 (design §11)
  - [ ] 5.2 전체 테스트, PR 본문 (노션과 다른 점, 배포 되돌림 위험, 지연 추정)
  - 커밋: `docs: 꼬리질문 판단 에이전트 명세 반영`
  - PR 제목 `feat: 모의면접 꼬리질문 판단을 툴 쓰는 에이전트로 보강`, 라벨 `feat`·`be`, 본문 `Closes #109`
