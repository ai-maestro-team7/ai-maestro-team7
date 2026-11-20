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

- [x] 2. 길이 제한·대체 경로·판단 결과 기록 (아직 한 번 호출 방식)
  - [x] 2.1 `settings.FOLLOW_UP_QUESTION_MAX` 150, `models.FollowUpOutput` 후보 버리기 (design §6)
  - [x] 2.2 `models.AnswerRecord.follow_up_check`, `flow.process_answer` 판단을 기록 추가 전으로, `followUpCheck` 기록 (design §5)
  - [x] 2.3 `follow_up.judge_follow_up` `AI_OUTPUT_INVALID` → JUDGE_FAILED 대체 (design §4.3)
  - [x] 2.4 `test_models.py`·`test_flow.py`·`test_backend_flow.py`·`test_logging.py` 수정, 대체 경로 테스트
    - `test_samples.py`는 바꿀 곳 없음 (`follow_up_multiple.json` 후보 3개 모두 150자 이하)
    - 기존 `test_follow_up_invalid_output_raises_and_session_unchanged`는 대체 경로 테스트로 바꿨다 (예외 → NEXT_QUESTION)
    - _Requirements: 4.1~4.4, 5.1~5.5, 6.1~6.3, 7.1~7.3_
  - 커밋: `feat: 꼬리질문 길이 제한과 판단 실패 시 꼬리질문 없이 진행` (617 passed 5 skipped)

- [x] 3. 판단 에이전트
  - [x] 3.1 `llm.py` `run_with_tools(max_tokens)`, `call_json_with_tools(max_tokens)`, `settings` 상한·`follow_up_max_tokens()` (design §4.4·§8)
  - [x] 3.2 `follow_up.py` `FollowUpContext`, `build_follow_up_context`, `make_follow_up_tools`, `judge_follow_up` 에이전트 (design §4)
  - [x] 3.3 `prompts/b_follow_up_v2.md`, `prompting.follow_up_prompt(question_type)`, `versions` B-v2 (design §7)
  - [x] 3.4 `fakes.FakeLLM.run_with_tools`, `test_follow_up.py`, `test_llm.py`·`test_prompting.py`·`test_flow.py`·`test_settings.py` 수정
    - 로그 원문 확인은 `test_follow_up.py`에 넣어 `test_logging.py`는 바꾸지 않았다
    - `build_follow_up_context`는 질문 문장을 인자로 따로 받는다 (`pending.text`, 기본 질문 문장과 같음)
    - _Requirements: 1.2~1.7, 2.1~2.5, 3.1~3.6, 8.1~8.2_
  - 커밋: `feat: 꼬리질문 판단을 툴 쓰는 에이전트로 보강` (641 passed 5 skipped)

- [x] 4. 수동 확인 (C 담당이 실제 Bedrock으로 실행)
  - [x] 4.1 `test_bedrock_manual.py`에 꼬리질문 판단 테스트 추가 (`RUN_BEDROCK=1`일 때만, `FOLLOW_UP_RUNS`로 반복)
    - 시나리오 4개: q1 경험·추상적(ABSTRACT), q1 경험·자소서와 모순(INCONSISTENT), q2 지식·원리 설명(SUFFICIENT), q2 지식·용어만(ABSTRACT)
    - 출력: 기대·결과·MATCH/DIFF, 시간, 판단·에이전트 로그(시도·툴 호출·stopReason), 꼬리질문 문장과 길이, 요약(일치 수, 평균·최대 시간)
    - 가짜 클라이언트로 오프라인 실행해 출력 형식 확인 (AWS 호출 없음)
    - `samples/session_after_start.json` promptVersion을 A-v2/B-v2로
  - [x] 4.2 실제 Bedrock 실행 결과 (Haiku 5.5, 시나리오 4개 × 2번, C 담당이 로컬에서 실행)

    | 항목 | 1차 (`7c04b32` 프롬프트) | 2차 (`52e87f1` 프롬프트) |
    | --- | --- | --- |
    | 판단 일치 | 6/8 | 8/8 |
    | 평균·최대 시간 | 5.3초 · 6.6초 | 4.6초 · 7.5초 |
    | 멈춘 이유·시도 수 | 모두 end_turn · 1번 | 모두 end_turn · 1번 |
    | 툴 호출 (판단 1번) | 2~3개 | 2~3개. 이전 답변·남은 질문은 8번 모두, 자소서 찾기는 5번 |
    | 꼬리질문 길이 | 61~132자 | 65~91자 (버린 후보 0개) |
    | 영어 단어 | "resume" 1번 | 없음 ("자소서"·"답변"으로 씀) |

    - 1차에서 틀린 2번: q2 지식·원리 설명이 2번 다 ABSTRACT. 답변에 방법·판단 근거·본인 예시가 다 있는데, 이미 말한 내용을 "왜 그렇게 했나"로 더 파고드는 꼬리질문을 냈다 → 프롬프트 기준이 엄격하다고 판단
    - 보강 (B-v2 안에서, 머지 전이라 버전 유지)
      - `f1ffbb0`: 지식 기준 "원리·이유와 예시가 둘 다 없을 때만", "더 물어볼 거리만으로는 ABSTRACT 아님", 길이·두 가지 묻기·자소서 옮겨 적기의 나쁜 예/좋은 예, "자소서"·"답변"으로 쓰고 영어 단어 금지
      - `52e87f1`: 길이 문구를 "공백 포함 120자 이내" 하나로 (C 담당 결정, 스키마 상한 150자 그대로)
    - 2차 꼬리질문 예 (모순): "자소서에는 네 명이 함께한 팀 프로젝트로 나오는데, 답변에서는 혼자 진행했다고 하셨습니다. 실제로 맡은 역할은 무엇이었나요?" (69자)
    - 2차에 남은 작은 문제: 두 가지를 이어 묻는 문장 2개("어떻게 달랐고, 그중 무엇을 기준으로…", "어떤 기준으로… 예시와 함께"), 자소서를 길게 옮긴 91자 문장 1개. 길이 상한 안이고 질문으로 어색하지 않아 더 고치지 않았다
    - 지연: 기본 답변마다 3.2~7.5초(지금까지 1~3초). 판단은 기본 답변 3번에서만 하므로 면접 1회 약 10~20초 증가 (design §9 추정 6~20초 안)
    - 확인하지 못한 것 (PR 남은 위험): 시나리오 수가 적음(4개 × 2번), Sonnet 미확인, 상황 판단 질문, 앞 답변과 모순, 남은 기본 질문과 겹치기 쉬운 답변, 실제 Bedrock에서 판단 출력 실패(대체 경로는 단위 테스트로만)
    - _Requirements: 8.3_
  - 커밋: `test: 꼬리질문 판단 수동 확인 테스트 추가` (641 passed 6 skipped), 결과 반영 `fix: 꼬리질문 지식 판단 기준과 길이·용어 규칙 보강`, `fix: 꼬리질문 길이 문구를 공백 포함 120자 이내로 변경`

- [x] 5. 문서와 PR
  - [x] 5.1 `docs/개발계획서3.md` ★(내부 함수 `judge_follow_up`, Session 예시 promptVersion·`followUpCheck`)·§2.3·§4.1 F-07·§4.2·§7 (design §11)
  - [x] 5.2 전체 테스트, PR 본문 (노션과 다른 점, 배포 되돌림 위험, 지연, 남은 위험)
  - 커밋: `docs: 꼬리질문 판단 에이전트 명세 반영`
  - PR 제목 `feat: 모의면접 꼬리질문 판단을 툴 쓰는 에이전트로 보강`, 라벨 `feat`·`be`, 본문 `Closes #109`
