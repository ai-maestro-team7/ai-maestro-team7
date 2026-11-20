# Implementation Plan

기준: 이 폴더의 `requirements.md`, `design.md`, 이슈 #158. 브랜치 `feat/be/#158-interview-job-posting` (최신 `main` `a8f1c57`에서). 테스트는 저장소 루트에서 `uv run --no-project --python 3.13 --with-requirements ai/interview/requirements-dev.txt pytest ai/interview/tests -q`.

규칙: 코드는 `ai/interview/` 안에서만 바꾼다 (예외 `.kiro/specs/`, `docs/개발계획서3.md`). 그 밖의 파일(`AGENTS.md` 포함)은 먼저 묻는다. AWS는 부르지 않는다.

- [x] 0. 스펙
  - [x] 0.1 requirements·design·tasks (결정 1~8, AGENTS.md "job만 넘긴다" 결정이 #158 팀 합의로 바뀐 것 기록)
  - 커밋: `docs: 면접 채용공고 입력 스펙 추가`

- [x] 1. 입력 모델과 변환 함수
  - [x] 1.1 `settings.py` 공고 길이 값, `models.JobPostingInput`, `QuestionRequest.job_posting` (design §3)
  - [x] 1.2 `job_posting.py` `normalize_job_posting`, `job_posting_from_posting`, `__init__` 내보내기 (design §4)
  - [x] 1.3 `test_job_posting.py`, `test_models.py`·`test_package.py` 수정, `samples/job_posting_data_analysis.json`(가상 공고)
    - 설정 값 확인은 `test_job_posting.py`에 넣었다 (`test_settings.py`는 2에서 버전만 바꾼다)
    - _Requirements: 1, 2, 3, 6.1, 7.2, 7.3_
  - 커밋: `feat: 면접 채용공고 입력 모델과 변환 함수 추가` (690 passed 6 skipped)

- [x] 2. 공고에 맞춘 질문 생성 (A-v3)
  - [x] 2.1 `prompting` `DATA_TAGS`·`questions_prompt(job_posting)`, `prompts/a_questions_v3.md`, `versions` A-v3 (design §5·§6)
  - [x] 2.2 `questions.py`·`flow.start_interview` 7번째 인자, 로그 (design §1·§7)
  - [x] 2.3 `test_prompting.py`·`test_flow.py`·`test_questions.py`·`test_logging.py`·`test_settings.py`·`test_package.py` 수정, `samples/session_after_start.json` promptVersion
    - 입력 검사 실패 로그의 필드 이름은 `start_interview`에서 `job_posting.text`, `normalize_job_posting`에서 `text`다 (함수 인자 이름 기준)
    - _Requirements: 4, 5, 6.2~6.4, 7.4_
  - 커밋: `feat: 채용공고에 맞춘 면접 질문 생성(A-v3)` (713 passed 6 skipped)

- [x] 3. 수동 확인 준비
  - [x] 3.1 `test_bedrock_manual.py`에 공고 비교 테스트 `test_questions_with_job_posting_with_real_model` (같은 자소서, 공고 없음·공고 있음·인재상 없는 공고·지시문이 든 공고·B 공고 변환, `JOB_POSTING_RUNS`로 반복). 질문·유형·길이·시간·표시(>80, 회사, 기출, 영문) 출력
    - 가짜 클라이언트로 오프라인 실행해 출력 형식만 확인했다 (AWS 호출 없음). 실제 Bedrock 실행은 C 담당
    - _Requirements: 7.5_
  - 커밋: `test: 면접 채용공고 질문 수동 확인 테스트 추가`

- [ ] 4. 수동 확인 결과 반영 (C 담당이 실제 Bedrock으로 실행한 뒤)
  - [ ] 4.1 결과 표, 프롬프트 보강이 필요하면 A-v3 안에서 (머지 전이라 버전 유지)

- [ ] 5. 문서와 PR
  - [ ] 5.1 `docs/개발계획서3.md` ★ `start_interview` 인자·내보내기 함수, §4.1 F-01, §5.2 입력 한도
  - [ ] 5.2 백엔드·프론트 인계 문서 (`h_start` 검사, `task_start` 7번째 인자, 프론트 `jobPosting` 입력, `interview_stub.py`, B 공고에서 시작할 때 변환 함수)
  - [ ] 5.3 PR 본문 (AGENTS.md 결정 변경, 배포 되돌림, 남은 위험)
  - PR 제목 `feat: 모의면접 기본 질문을 채용공고에 맞춰 생성`, 라벨 `feat`·`be`, 본문 `Closes #158`
