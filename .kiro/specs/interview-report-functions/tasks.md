# Implementation Plan

기준: 이 폴더의 `requirements.md`, `design.md`, 이슈 #92. 브랜치 `feat/be/#92-interview-report` (최신 `main` `1cfc69d`에서). 테스트는 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q`.

- [x] 1. 설정 파일과 점수 계산
  - [x] 1.1 `config/scoring_v1.json`에 노션 6-⑤ 값과 `grades`를 넣고 `config.py` 검사를 늘린다 (design §8)
    - `test_config.py`: 새 값, `full`이 `half` 안, 비율 합 100, 등급 내림차순
    - _Requirements: 1.1~1.4_
  - [x] 1.2 `bundles.py` `make_bundles` (design §3), `test_bundles.py`
  - [x] 1.3 `models.py`에 `ContentEvaluation`, `ScoreResult`, `scoring.py` `calculate_interview_scores`와 변환 함수 (design §5)
    - `test_scoring.py`: 경계값, 미측정, 비율 선택, 반올림, 같은 입력 같은 결과
    - _Requirements: 3.1~3.9_
  - 커밋: `feat: 면접 점수 계산과 점수 설정 추가` (`4e0c23d`)

- [x] 2. 내용 평가 (C-1)
  - [x] 2.1 `prompts/system_eval_v1.md`, `prompts/c1_content_v1.md`(노션 6-① 평가표), `prompting.py`에 태그·프롬프트 함수, `versions.py`
  - [x] 2.2 `content.py` `evaluate_content`, 근거 대조 (design §4), `samples/llm/` C-1 예시
  - [x] 2.3 `test_content.py`
    - _Requirements: 2.1~2.7_
  - 커밋: `feat: 면접 답변 내용 평가 추가` (`db6917e`, 묶음 A 421 passed 3 skipped)

- [x] 3. 피드백 에이전트 (C-2, Strands 툴 사용)
  - [x] 3.1 `llm.py`: `ToolLLMClient`, `StrandsLLMClient.run_with_tools`(strands `tool`·`limits`), `_get_model` max_tokens별 캐시, `call_json_with_tools` (design §6.3). `settings.py`에 상한·`feedback_max_tokens()`
  - [x] 3.2 `feedback.py`: `FeedbackContext`(frozen), `make_feedback_tools` 읽기 전용 툴 4개, `write_feedback`, 금지 표현 검사 (design §6.1·§6.2·§6.4). `prompts/c2_feedback_v1.md`
  - [x] 3.3 `tests/fakes.py`에 툴을 차례로 부르는 `FakeToolLLM`, `test_feedback.py`
    - 툴 결과가 복사본이고 실행 뒤 점수가 그대로인지, 없는 질문 ID·빈 키워드 오류 사실, 툴 호출 상한, 금지 표현 → 재시도, 상한에 닿아 JSON 없음 → `AI_OUTPUT_INVALID`
    - `test_llm.py`: 가짜 strands로 `tools`·`limits`·`max_tokens` 2048이 넘어가는지, 설치된 strands로 `strands.tool` 감싸기
    - _Requirements: 4.1~4.9_
  - 커밋: `feat: 면접 피드백 에이전트 추가` (`f54abe4`)

- [x] 4. 리포트 연결
  - [x] 4.1 `report.py` `generate_report` (design §7), `__init__.py` 연결, `placeholders.py`에서 `generate_report` 삭제
  - [x] 4.2 `test_report.py`, `test_backend_flow.py`·`test_placeholders.py`·`test_package.py` 수정 (`test_logging.py`는 바꿀 곳 없음, 리포트 로그는 `test_report.py`에서 확인)
    - _Requirements: 5.1~5.8, 6.1~6.2, 7.1~7.5_
  - 커밋: `feat: 면접 결과 리포트를 실제 구현으로 연결` (`0862aa9`, 묶음 B 461 passed 3 skipped)

- [ ] 5. 수동 확인 (실제 Bedrock, 사람이 실행)
  - [x] 5.1 `test_bedrock_manual.py`에 리포트 생성 테스트 추가 (`RUN_BEDROCK=1`일 때만, `REPORT_RUNS=2`면 두 번)
  - [ ] 5.2 Haiku로 실행해 점수·등급·리포트 생성 시간, 잘림 여부, C-2 에이전트의 턴 수·툴 호출을 PR 참고 사항에 적는다. 같은 Session으로 두 번 돌려 C-1 점수 차이를 본다 (design §6.5, §13-1)
    - _Requirements: 7.6_
  - 커밋: `test: 리포트 수동 확인 테스트 추가` (`1adcb30`)

- [ ] 6. 문서와 PR
  - [x] 6.1 `docs/개발계획서3.md` ★ 내부 함수 표, §2.3, §4.1 F-09, §4.3, §5.4 예시, §11 갱신 (design §12)
  - [ ] 6.2 전체 테스트 통과 확인, PR 본문 작성 (노션 6과 대조했음, 태도 미측정 이유, 결정 2·5·7)
  - [ ] 6.3 리포트 형식이 프론트 화면과 맞는지 프론트 담당에게 확인 요청, PR 링크를 팀 채널에 알린다
  - 커밋: `docs: 채점·리포트 단계 명세 반영`
  - PR 제목 `feat: 모의면접 답변 채점과 결과 리포트 구현`, 라벨 `feat`·`be`, 본문 `Closes #92`
