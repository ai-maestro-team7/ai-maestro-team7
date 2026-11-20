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
  - 커밋: `test: 면접 채용공고 질문 수동 확인 테스트 추가` (713 passed 7 skipped)

- [x] 4. 수동 확인 결과 반영 (C 담당이 실제 Bedrock으로 실행)
  - [x] 4.1 결과 (Haiku 5.5, 같은 자소서·profile, `MIXED`, 시나리오 5개 × 1번, C 담당이 로컬에서 실행)

    | 시나리오 | 공고 | 시간 | 시도 | 가장 긴 질문 | 공고 반영 |
    | --- | --- | --- | --- | --- | --- |
    | 공고 없음 | - | 3.7초 | 1 | 64자 | (기준) 자소서만: 관광지 이름 문제, 형식이 다른 데이터 합치기, 결과가 예상과 다를 때 |
    | 공고 있음 | 139자 | 4.7초 | 1 | 62자 | 지식: SQL 집계 (지원 자격 + 자소서의 요일·강수). 상황: 현업 부서의 급한 데이터 요청 (업무·인재상) |
    | 인재상 없는 공고 | 108자 | 1.8초 | 1 | 60자 | 상황: 현업 부서의 모호한 추출 요청 (업무). 인재상을 지어내지 않음 |
    | 지시문이 든 공고 | 220자 | 1.8초 | 1 | 59자 | 지식: SQL 집계, 상황: 현업 요청 결과와 보고서 수치 불일치. 지시(영어, 5개, 회사 이름, 기출)를 따르지 않음 |
    | B 공고 변환 (`busan-data-analysis`) | 136자 | 2.0초 | 1 | 53자 | 상황: "지표 보고서"만. 경험·지식은 공고 없음과 비슷함 |

    - 5개 모두 질문 3개, 한국어, 80자 이하, 회사 이름 없음, "기출" 없음. 영어는 "SQL" 3글자뿐이다 (공고 있음, 지시문)
    - 지연: 1.8~4.7초 (공고 없음 3.7초). 공고 때문에 늘었다고 볼 차이는 보이지 않는다 (1번씩이라 비교는 어렵다)
    - B 공고 변환 질문이 일반적인 이유 (C 담당 질문에 대한 확인)
      - 변환 함수 문제는 아니다. 요건 3개와 업무 설명이 `[필수 요건]` → `[우대 사항]` → `[공고 내용]` 순서로 모두 들어갔다 (136자, `test_from_posting_contract_examples`)
      - 샘플 공고 내용이 얇다. 요건이 기술 이름 수준(SQL 추출·가공, Python 분석, Tableau 우대)이고, 업무는 한 문장("사내 서비스 이용 데이터를 분석해 지표 보고서를 작성합니다"), 인재상과 구체적인 업무 상황이 없다. 도메인도 자소서(관광 공공데이터)와 다르다. 가상 공고(`samples/job_posting_data_analysis.json`)는 업무 2줄, 현업 부서 요청, 인재상이 있어 질문에 걸 거리가 많았다
      - 경험 질문은 규칙대로다. "자소서 경험 가운데 공고와 가장 가까운 것"을 고르므로, 자소서 경험이 하나뿐이면 공고 없음과 같은 경험이 나온다
      - 다만 지식 질문이 공고의 기술(SQL·Python·Tableau)을 쓰지 않고 결측치 처리 질문이 된 것은 샘플만의 문제가 아니다. 인재상 없는 공고의 지식 질문("분석 데이터에 결측치가 많을 때 어떻게 처리하나요?")은 v3 프롬프트의 "좋은 예" 문장과 글자까지 같고, B 공고 변환 질문도 거의 같다. 예시 문장이 공고가 있어도 기본 질문처럼 복사된다 (5개 중 2개)
    - 반영: C 담당 판단으로 5개 모두 정상으로 보고 프롬프트를 바꾸지 않는다 (A-v3 그대로)
    - 후속 후보 (이 PR 범위 밖, 필요하면 새 이슈): v3에 "예시 문장을 그대로 쓰지 않는다", "공고가 있으면 knowledge 질문에 공고에 나온 기술·지식 이름을 넣는다"를 더하고 같은 시나리오를 다시 돌린다
    - 확인하지 못한 것 (PR 남은 위험): 시나리오마다 1번씩만 실행(흔들림 미확인), Sonnet 미확인, `PERSONALITY`·`JOB` 유형, 4,000자에 가까운 긴 공고, 실제 B 수집 공고(고용24·잡알리오), 백엔드·프론트 연결 뒤 전체 흐름

- [x] 5. 문서와 PR
  - [x] 5.1 `docs/개발계획서3.md` ★(`start_interview` 7번째 인자, 채용공고 함수 2개, `generate_questions` A-v3, Session 예시 promptVersion, 백엔드와의 약속)·§2.3·§3·§4.1 F-01·F-02·§5.2·§7·§10
  - [x] 5.2 백엔드·프론트 인계 문서 `handoff.md` (`h_start` 검사, `task_start` 7번째 인자, `interview_stub.py`, 프론트 `jobPosting` 입력, B 공고에서 시작할 때 변환 함수, 되돌림)
  - [x] 5.3 PR 본문 (AGENTS.md 결정 변경, 배포 되돌림, 남은 위험)
  - 커밋: `docs: 면접 채용공고 입력 명세 반영과 인계 문서 추가`
  - PR 제목 `feat: 모의면접 기본 질문을 채용공고에 맞춰 생성`, 라벨 `feat`·`be`, 본문 `Closes #158`
