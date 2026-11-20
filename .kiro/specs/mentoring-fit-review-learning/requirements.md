# Requirements Document

## Introduction

mentoring-fit-review-learning은 A 파트(`docs/개발계획서1.md`)의 둘째 후속 스펙이다. 첫 스펙(mentoring-profile-storybank)이 만든 역량 프로필과 경험 블록을 읽어 직무 적합도·지원자격(F-02), 역량 격차(F-04), 자기소개서·이력서 첨삭(F-03), 학습·자격·교육 경로(F-05)를 만든다. 데모 흐름은 A §14 Day 1~2와 product.md "A 데모"의 "부산 공고 선택 → 적합도 → 첨삭 → 학습 경로" 구간이다.

근거와 전제:
- 문서 표기: A = `docs/개발계획서1.md`, api = `docs/api.md`(v1.0), db = `docs/db-schema.md`(v1.3), 기반 = `.kiro/specs/common-foundation/`, 첫 스펙 = `.kiro/specs/mentoring-profile-storybank/requirements.md`, 계약 = `contracts/src/team07_contracts/`, 패키지 = 지식 패키지 `team7-career-mentor-knowledge-package-2026-11-20.zip`.
- 첫 스펙의 Requirement 1(패키지·입구), 2(사용자 식별·격리), 4 기준 5~7(작업 상태·멱등 실행), 11(외부 서비스 없는 테스트), 12(로그·지표)는 이 스펙에도 그대로 적용한다. 아래 기준은 이 스펙에서 새로 생기는 것만 적는다.
- 결정 기록에서 CONFIRMED인 결정을 따른다: API 규약(D-01~D-05), DB 4테이블(D-13), 공고 스냅샷 `SNAP#`·`LATEST`와 요건 `requirements[]{kind, weight, sourceQuote}`(D-09·D-10·D-34), 자격 판정 함수 하나(D-11), 워크스페이스 BACKEND(D-36), Lambda 비동기 자기 호출(D-19), 데모 직무 데이터 분석 NCS 20010105(D-37). PROPOSED 결정(D-39 스냅샷 추출 시점, D-41 판정 함수 위치)에 걸리는 기준은 ID를 붙인다.
- A §12.3은 공고를 `GET /internal/job-postings/{id}`로 받자고 했지만, db §3은 A가 `team07-catalog`의 `SNAP#{snapshotId}`를 직접 읽는 것으로 정했다 (db §3 "A의 스냅샷 요청 해결"). 이 스펙은 db §3을 따른다. 공고 데이터는 B 소유이고 A는 읽기만 한다.
- Knowledge Base(`team07-career-mentor-kb`)는 만들어져 동기화돼 있다 (PR #48, `infra/setup-kb.sh`). 2026-11-20 측정에서 패키지 `validation/sample_queries.jsonl` 25건의 Recall@5는 필터 없이 0.92, `job_role` 필터를 쓰면 0.96이다. KB ID는 저장소에 적지 않고 환경변수로 받는다.
- 이 스펙에 필요한 권한은 지금 실행 역할에 있다: `team07-*` 테이블 읽기·쓰기(catalog·reference 읽기 포함), career-docs 객체 읽기·쓰기, Bedrock 모델 호출, KB `Retrieve`, Secrets Manager `team07/*` 읽기, Lambda 자기 호출.

범위에서 제외:
- 통합 Agent·Action Group(F-06), 품질 평가셋 실행(F-07), 운영 알람(F-08): mentoring-agent-quality. 단, 이 스펙의 비즈니스 함수는 User_Id를 첫 인자로 받아 나중에 Agent 도구가 그대로 부를 수 있게 둔다 (첫 스펙 Requirement 1 기준 3).
- 공고·정책 수집, 요건 추출, `eligibilityRules[]` 저장: B (busan-opportunity-data)
- 워크스페이스 생성·지원 상태·지원서 최종본 버전 저장: BACKEND (D-36, api §6.0, A §12.4)
- 모의면접에 넘기는 역량 요약: 첫 스펙 Requirement 8 (D-12)
- 기업 인재상 비교: 공식 출처가 확인된 기업 자료가 없어 MVP에서 뺀다 (A F-03 처리 2단계 "출처가 없으면 공고 직무 요구사항만 사용")
- AWS 자원 생성, 권한 변경, 비밀정보 등록, 배포 (AGENTS.md "환경·보안")

## Glossary

- **Mentoring_API**, **Task_Runner**, **User_Id**, **Career_Profile**, **Evidence**, **Evidence_Level**, **Fact_Status**, **Story_Item**, **LLM_Port**, **MockLLM**, **Reference_Lookup**, **Error_Envelope**: 첫 스펙 Glossary와 같다
- **Posting_Snapshot**: `team07-catalog`의 `POSTING#{jobPostingId}` / `SNAP#{snapshotId}` 항목. 분석은 이 시점의 공고를 고정해 쓴다 (db §3, D-09)
- **Assessment_Mode**: 분석 기준. `POSTING`(특정 공고의 요건)과 `NCS_GENERAL`(NCS 표준 직무 정의) 두 가지 (A §12.3 "NCS 일반 직무 추천과 실제 지원 가능 판단을 `assessmentMode`로 분리")
- **Requirement_Item**: 분석에 쓰는 요건 하나. `POSTING`이면 공고의 `requirements[]` 항목, `NCS_GENERAL`이면 그 NCS 직무의 능력단위
- **Requirement_Link**: Requirement_Item 하나와 Career_Profile의 역량·Evidence를 잇는 연결과 그 Evidence_Level
- **Fit_Policy**: 참고점수 계산 규칙과 값(분류별 가중치, 근거 단계별 하한·상한 값)을 담은 설정. 버전 `scorePolicyVersion`을 가진다 (A F-02 "권장 참고점수 계산")
- **Job_Fit_Analysis**: F-02 결과. `ANALYSIS#{analysisId}` (db §2.1), 결과 계약 `JobFitResult` (A §4.5)
- **Gap_Result**: F-04 결과. 확인된 강점, 부분 증거, 미확인, 확인된 격차 4분류와 우선순위 행동 (A §4.5·F-04)
- **Eligibility_Fn**: 공고 자격 판정 함수 `evaluate_eligibility(profile, rules)` (`backend/eligibility.py`, D-11, api §6.1). A는 import하지 않고 백엔드가 넣어 준 것을 쓴다
- **Basic_Profile**: BACKEND 소유 기본 프로필 `PROFILE#BASIC` (학력, 전공, 경력 등, db §2.1, D-08). A는 읽기만 한다
- **Knowledge_Citation**: KB 검색 결과 하나. `documentId`, `title`, `sourceUrl`, `ncsCode`, `chunkText`, `retrievalScore`, `sourceReferenceDate`, `retrievedAt` (A §8.2)
- **Review**: F-03 첨삭 결과. `REVIEW#{reviewId}`, 본문은 S3 `resultKey` (db §2.1), 결과 계약 `ReviewResult` (A §4.5)
- **Learning_Path**: F-05 결과. `PATH#{pathId}` (db §2.1), 결과 계약 `LearningPathResult` (A §4.5)
- **Official_Data_Port**: 고용24 훈련과정, 국가자격 시험일정 같은 외부 공식 API를 감싼 인터페이스 (A §9 `OfficialDataPort`)
- **As_Of**: 날짜 계산의 기준 시각. 입구가 한 번 정해 비즈니스 함수에 넘긴다 (AGENTS.md "날짜는 `asOf`를 받아 계산")

## Requirements

### Requirement 1: 분석·첨삭·학습 경로 공통 처리

**User Story:** As a 프론트엔드 담당, I want 세 기능이 같은 방식으로 요청을 받고 상태를 알려 주기를, so that 화면 하나의 폴링 코드로 세 기능을 다 붙인다.

출처: A §6 "공통 정책"·§6.1, api §2·§4·§6.0, db §2.1·§2.5, D-05, D-19, D-31, 첫 스펙 Requirement 4 기준 5~7

#### Acceptance Criteria

1. THE Mentoring_API SHALL `POST /api/v1/mentoring/analyses`, `POST /api/v1/mentoring/reviews`, `POST /api/v1/mentoring/learning-paths`를 202로 받고 각각 `analysisId`, `reviewId`, `learningPathId`와 `taskId`, `status=PENDING`, `requestId`를 돌려준다. 작업 종류는 db §2.5의 `JOB_FIT`, `REVIEW`, `LEARNING_PATH`다 (A §6.1, db §2.5).
2. THE Mentoring_API SHALL `GET /api/v1/mentoring/analyses/{analysisId}`, `GET /api/v1/mentoring/reviews/{reviewId}`, `GET /api/v1/mentoring/learning-paths/{learningPathId}`로 상태와 완료된 결과를 돌려준다. 상태 값은 `PENDING`, `PROCESSING`, `REQUIRES_USER_REVIEW`, `PARTIAL_SUCCESS`, `COMPLETED`, `FAILED`뿐이다 (A §6 "공통 정책", D-05).
3. WHEN 같은 사용자가 같은 `Idempotency-Key`와 같은 본문으로 다시 POST하면, THE Mentoring_API SHALL 새 결과를 만들지 않고 처음 ID를 돌려준다. 같은 키에 다른 본문이 오면 409 `PRECONDITION_NOT_MET`이다 (api §2, D-31).
4. WHERE 요청에 `workspaceId`가 있으면, THE Mentoring_Package SHALL 결과 항목에 `GSI1PK = USER#{User_Id}#WS#{workspaceId}`, `GSI1SK = {ANALYSIS|REVIEW|PATH}#{createdAt}#{id}`를 넣는다. 워크스페이스를 만들거나 상태를 바꾸지 않는다 (api §6.0, A §12.4).
5. THE Mentoring_Package SHALL 세 결과를 수정하지 않는다. 같은 입력으로 다시 요청하면 새 ID의 결과를 만든다. 입력 프로필·문서·공고가 바뀌어도 이전 결과의 `profileVersion`, `documentVersion`, `snapshotId`는 그대로 둔다 (db §0 원칙 5, A §12.4, UT-19).
6. THE Mentoring_Package SHALL 모든 결과에 응답 기준일(`createdAt`)과 공식 자료 기준일(`sourceCheckedAt` 또는 출처별 `checkedAt`)을 따로 두고, `modelId`, `promptVersion`, `schemaVersion`, 해당하면 `scorePolicyVersion`과 `ruleVersion`을 남긴다 (A §4.5 "응답 기준일과 공식 자료 기준일을 분리", tech.md "결과에는 modelId…").
7. THE Mentoring_Package SHALL 날짜 계산(마감까지 남은 기간, 학습 주 수, 시험 일정 비교)을 As_Of 하나로 한다 (AGENTS.md "코딩 규칙").
8. WHEN 요청한 `analysisId`, `reviewId`, `learningPathId`, `profileId`, `documentId`, `storyId`가 없거나 다른 사용자 것이면, THE Mentoring_API SHALL 같은 404를 돌려준다 (첫 스펙 Requirement 2 기준 3, UT-15).

### Requirement 2: 직무 적합도 분석 요청과 입력 데이터

**User Story:** As a 사용자, I want 관심 공고나 희망 NCS 직무를 골라 내 역량 프로필과 비교받기를, so that 공고마다 무엇이 맞고 무엇을 확인해야 하는지 안다.

출처: A F-02 입력·처리 1~5단계, §6.3, §8.3, §12.3, db §3·§4, D-09, D-39(PROPOSED), UT-09·UT-19

#### Acceptance Criteria

1. WHEN 사용자가 `POST /analyses`에 `profileId`, 선택 `profileVersion`, `jobPostingId`와 `targetNcsCode` 중 하나 이상, 선택 `workspaceId`를 보내면, THE Mentoring_API SHALL 둘 다 없으면 400 `INVALID_INPUT`을 돌려주고, 있으면 Job_Fit_Analysis를 만든다. `profileVersion`이 없으면 그때의 최신 버전을 고정해 저장한다 (A F-02 입력·처리 1단계).
2. WHERE `jobPostingId`가 있으면, THE Task_Runner SHALL Assessment_Mode를 `POSTING`으로 두고, `LATEST`가 가리키는 Posting_Snapshot을 읽어 그 `snapshotId`를 결과에 저장한다. 요건(`requirements[]`)과 자격 조건(`eligibilityRules[]`)은 이 스냅샷 값만 쓰고 LLM으로 새로 만들거나 바꾸지 않는다 (db §3 "A는 분석에 `snapshotId`를 저장", tech.md "API에서 받은 값을 LLM 결과로 덮어쓰지 않는다").
3. IF Posting_Snapshot의 요건 추출이 끝나지 않았으면, THEN THE Task_Runner SHALL 분석을 `REQUIRES_USER_REVIEW`, 사유 코드 `POSTING_NOT_READY`로 두고 점수를 내지 않는다 [D-39 PROPOSED: 추출이 끝난 스냅샷만 분석에 쓴다].
4. WHERE 공고가 마감(`isExpired = true`)이면, THE Task_Runner SHALL 분석은 하고 결과 `warnings`에 마감 사실을 넣는다. 나중에 같은 분석을 조회하면 그때의 `snapshotId`와 `checkedAt`을 그대로 보여 준다 (A F-02 완료 기준 "공고 종료 상황 처리", UT-19).
5. WHERE `jobPostingId` 없이 `targetNcsCode`만 있으면, THE Task_Runner SHALL Assessment_Mode를 `NCS_GENERAL`로 두고 Reference_Lookup의 그 NCS 직무 능력단위를 Requirement_Item으로 쓴다. 이 모드의 결과는 특정 기업 지원 가능 여부를 말하지 않는다 (A F-02 처리 3·5단계, §12.3).
6. IF `targetNcsCode`가 Reference_Lookup에 없으면, THEN THE Mentoring_API SHALL 400 `INVALID_INPUT`을 돌려주고 분석을 만들지 않는다 (UT-09).
7. WHERE `POSTING` 모드에서 공고의 NCS 코드(`job.ncsCodes[]`, 없으면 `team07-reference`의 `MAP#WORK24#` 매핑)가 0개이거나 여러 개이면, THE Task_Runner SHALL 하나로 정하지 않고 결과에 `ncsCandidates[]`를 남긴다. 점수 계산은 공고 요건만으로 하고, NCS 코드가 필요한 KB 필터와 학습 경로는 사용자가 하나를 고른 뒤에 쓴다 (A F-02 처리 4단계, §8.3 "후보가 여러 개이면 한 개를 고정 확정하지 말고").
8. THE Task_Runner SHALL Career_Profile 버전, Posting_Snapshot, NCS 능력단위를 GetItem·Query로만 읽는다 (db §0 원칙 9).

### Requirement 3: 지원자격 판정

**User Story:** As a 사용자, I want 학력·경력·자격 같은 공고의 필수 조건 충족 여부를 점수와 따로 보기를, so that 기술 적합도가 높아도 지원 조건이 안 맞는 공고를 알아챈다.

출처: A F-02 처리 8단계·"INELIGIBLE이면 최우선 표시", api §6.1, db §3.2, D-11, D-41(PROPOSED), UT-05

#### Acceptance Criteria

1. WHERE Assessment_Mode가 `POSTING`이면, THE Task_Runner SHALL Basic_Profile과 Career_Profile의 자격(`certificates`, 사용자가 없다고 확인한 자격)을 합친 값과 Posting_Snapshot의 `eligibilityRules[]`로 Eligibility_Fn을 부르고, 반환된 `status`, 조건별 결과, `ruleVersion`을 결과에 저장한다 (db §3.2 "A는 분석 결과에 그때의 판정과 `ruleVersion`을 함께 저장").
2. THE Mentoring_Package SHALL 자격 판정 규칙을 따로 구현하지 않고, Eligibility_Fn을 의존성으로 받는다. `backend/`를 import하지 않는다. 백엔드가 B와 같은 방식으로 넣어 준다 (D-11, 첫 스펙 Requirement 1 기준 4, BE-8) [D-41 PROPOSED: 함수를 `team07_contracts`로 옮기면 그쪽을 쓴다].
3. WHERE Eligibility_Fn이 주어지지 않았거나 Basic_Profile이 없으면, THE Task_Runner SHALL `eligibilityStatus`를 `NEEDS_VERIFICATION`으로 두고 사유를 남긴다. `ELIGIBLE`이나 `INELIGIBLE`을 추측하지 않는다 (A §4.2 "NOT_FOUND ≠ 실력 없음", api §6.1).
4. WHERE Assessment_Mode가 `NCS_GENERAL`이면, THE Task_Runner SHALL 자격 판정을 하지 않고 `eligibilityStatus`를 비워 둔다 (A §12.3).
5. WHEN 판정이 `INELIGIBLE`이면, THE Mentoring_Package SHALL 점수는 그대로 계산해 두고, 결과에서 미충족 조건과 그 `sourceQuote`를 점수보다 앞에 둔다 (A F-02 "INELIGIBLE이면 … 최우선 표시", UT-05).

### Requirement 4: 요건과 근거 연결

**User Story:** As a 사용자, I want 공고 요건마다 내 이력서의 어느 근거가 연결됐는지 보기를, so that 적합도 숫자가 어디서 나왔는지 확인한다.

출처: A F-02 처리 6~7단계, §4.2·§4.3, F-07 계층별 검증, tech.md "근거 인용은 원문에 실제로 있는지 대조", UT-01·UT-02·UT-03

#### Acceptance Criteria

1. THE Task_Runner SHALL Requirement_Item마다 Career_Profile의 역량·Evidence와의 연결 후보를 LLM_Port에 묻되, 모델은 Career_Profile에 이미 있는 `skillId`와 `evidenceId` 중에서만 고르게 한다. 요건 문구와 이력서 내용은 태그로 감싸 데이터로만 넘긴다 (A F-02 처리 7단계, tech.md "외부 텍스트는 태그로 감싸").
2. THE Task_Runner SHALL 모델 출력을 고정 JSON 스키마로 받고 Pydantic으로 검사한다. 실패하면 한 번 다시 묻고, 다시 실패하면 분석을 `FAILED`, `AI_OUTPUT_INVALID`, `retryable=true`로 둔다 (tech.md "LLM 출력은 고정 JSON 스키마").
3. THE Task_Runner SHALL 모델이 고른 `skillId`·`evidenceId`가 그 Career_Profile 버전에 없으면 그 연결을 버리고 해당 요건을 `NOT_FOUND`로 둔다 (A §4.3 "실제 시연 문서에 없는 문구는 근거로 저장하지 않음").
4. THE Task_Runner SHALL Requirement_Link의 Evidence_Level을 모델이 정하지 않고, 연결된 역량에 저장된 Evidence_Level과 Fact_Status로 코드가 정한다. 사용자가 없다고 확인한 역량은 `USER_CONFIRMED_GAP`, 연결이 없으면 `NOT_FOUND`다 (A §4.2, 제품 원칙 3).
5. THE Mentoring_Package SHALL 서류에 없는 요건을 "부족"으로 표시하지 않고 `NOT_FOUND`(미확인)로 두며, 미확인 요건마다 사용자에게 물을 확인 질문을 하나 붙인다 (A §4.2, F-04 `verificationTasks`, 제품 원칙 5, UT-02).
6. FOR ALL 결과의 강점과 부분 증거 항목, 연결된 `evidenceId`가 그 Career_Profile 버전에 있어야 한다 (A F-07 품질 게이트 "Evidence quote 정합성 100%").

### Requirement 5: 적합도 참고점수

**User Story:** As a 사용자, I want 같은 서류와 같은 공고면 언제나 같은 적합도가 나오기를, so that 점수를 믿고 보완 전후를 비교한다.

출처: A F-02 "권장 참고점수 계산"·"정책 예시"·완료 기준, §6.3, api §6.3, product.md 제품 원칙 3·4, UT-06·UT-07·UT-08

#### Acceptance Criteria

1. THE Mentoring_Package SHALL 점수를 LLM 없이 규칙 코드로만 계산한다. 같은 Requirement_Link 목록과 같은 Fit_Policy면 언제나 같은 `fitScore`와 `potentialUpperBound`를 낸다 (A F-02 처리 9단계, UT-08).
2. THE Mentoring_Package SHALL Fit_Policy를 설정 파일에서 읽는다. 초기값은 A F-02 값이다: 분류별 가중치 필수 0.7·우대 0.2·관련 경험 근거 0.1, 하한 값 `EVIDENCED=1.0`·`PARTIAL=0.5`·`SELF_REPORTED=0.25`·`NOT_FOUND=0`·`USER_CONFIRMED_GAP=0`, 상한 값은 `NOT_FOUND`만 1.0이고 나머지는 하한과 같다. 불러올 때 가중치 합이 1인지, 모든 값이 0~1인지, 상한이 하한보다 작지 않은지 검사하고 어긋나면 멈춘다 (A F-02, tech.md "가중치·임계값은 설정 파일에서 읽고, 읽을 때 검증").
3. THE Mentoring_Package SHALL 분류마다 Requirement_Item의 `weight`로 가중평균을 내고, 요건이 없는 분류는 빼고 남은 분류의 가중치로 다시 나눈다. `fitScore = round(100 × 하한)`, `potentialUpperBound = round(100 × 상한)`이다. 반올림 방식은 design에서 정하고 테스트로 고정한다 (A F-02, UT-06).
4. FOR ALL 입력, `0 ≤ fitScore ≤ potentialUpperBound ≤ 100`이어야 한다.
5. WHEN A F-02 "정책 예시"(필수 2개: 근거 있음 1·미확인 1, 우대 1개: 자기보고, 관련 경험 1개: 근거 있음)를 넣으면, THE Mentoring_Package SHALL `fitScore = 50`, `potentialUpperBound = 85`를 낸다.
6. IF Requirement_Item이 0개이면, THEN THE Mentoring_Package SHALL `fitScore`와 `potentialUpperBound`를 `null`로, 사유를 `INSUFFICIENT_REQUIREMENTS`로 둔다 (A F-02, UT-07).
7. THE Mentoring_Package SHALL 결과에 `scoreType = DOCUMENT_BASED_MATCH`, `scorePolicyVersion`, 경고 문구 "적합도는 실제 합격 확률이 아닙니다"를 넣는다. 부산 근무 여부로 점수를 바꾸지 않는다 (A §6.3, api §6.3, 제품 원칙 4·6).
8. THE Mentoring_Package SHALL 결과의 자연어 요약에 합격 확률, 합격 가능성 퍼센트, "합격에 유리해요" 같은 표현이 들어가면 그 문장을 빼거나 다시 생성한다. 요약은 코드가 계산한 점수·분류를 바꾸지 않는다 (A F-02 완료 기준 "점수·합격 가능성을 혼동하는 자연어 출력 차단", 처리 10단계, product.md "문구 규칙").

### Requirement 6: 역량 격차 분류와 우선순위

**User Story:** As a 사용자, I want 강점·보완할 점·확인할 점·실제로 부족한 점을 나눠 보기를, so that 바로 공부할 것과 먼저 사실을 확인할 것을 구분한다.

출처: A F-04 "4가지 분류"·"우선순위 규칙"·완료 기준, §4.5 `GapResult`, §12.1 "관심 공고 상세"

#### Acceptance Criteria

1. THE Mentoring_Package SHALL F-02의 Requirement_Link만으로 Gap_Result를 만들고 따로 추측하지 않는다: `EVIDENCED`는 확인된 강점, `PARTIAL`·`SELF_REPORTED`는 부분 증거, `NOT_FOUND`는 미확인, `USER_CONFIRMED_GAP`과 Eligibility_Fn이 `NOT_MET`으로 판정한 자격 조건은 확인된 격차다 (A F-04 "F-02 계산을 재사용").
2. THE Mentoring_Package SHALL 우선순위를 공고 필수 요건, 공고 우대 요건, NCS 학습 목표 순으로 정하고, 확인된 격차만 "학습 필수"로 표시한다. 미확인 항목은 `verificationTasks`(확인 질문)로 따로 둔다 (A F-04 "우선순위 규칙").
3. FOR ALL Gap_Result, 한 요건은 네 분류 중 하나에만 들어가고, 확인 질문과 학습 과제 목록에 같은 항목이 중복되지 않는다 (A F-04 완료 기준).
4. FOR ALL Gap_Result, 분류별 항목 수는 같은 분석의 Requirement_Link 분포와 일치한다 (A F-04 완료 기준 "F-02 점수·요건·분류와 항상 일관").
5. THE Mentoring_Package SHALL Gap_Result에 근거가 된 NCS 능력단위 코드(`sourceNcsUnitCodes`)를 Reference_Lookup에 있는 코드만 넣는다 (A §4.5, tech.md "NCS 코드는 정형 데이터로 정확히 조회").

### Requirement 7: Knowledge Base 근거 검색

**User Story:** As a 사용자, I want 적합도·학습 경로 설명에 공식 직무 자료의 출처와 기준일이 붙기를, so that AI 설명이 어디에 근거했는지 확인한다.

출처: A F-02 처리 6단계, §8.2·§8.3, F-05 처리 5단계, UT-10·UT-16, AGENTS.md "지식 패키지"

#### Acceptance Criteria

1. THE Mentoring_Package SHALL KB 검색을 인터페이스 뒤에 두고, 운영 구현은 `bedrock-agent-runtime` `Retrieve`를 부른다. KB ID는 환경변수에서 읽는다 (A §8.2, BE-4).
2. WHERE NCS 직무가 하나로 정해졌으면, THE Mentoring_Package SHALL 메타데이터 `job_role`(그 NCS 직무 이름)과 `공통`으로 필터를 걸어 검색한다. 다른 직무의 `ncs_job_profile` 문서는 결과에 들어가지 않아야 한다 (A §8.1 9단계, UT-10).
3. THE Mentoring_Package SHALL 검색 결과를 Knowledge_Citation으로 바꾸고, `documentId`, `sourceUrl`, 기준일(`collected_at` 또는 `original_published_at`)이 없는 결과는 근거로 쓰지 않는다 (A §8.2, §1.1 "공식 자료 검색 결과에 문서 ID, 출처 URL, 기준일이 첨부됨").
4. IF 쓸 수 있는 검색 결과가 0건이면, THEN THE Mentoring_Package SHALL `NO_EVIDENCE`를 남기고, 근거 없는 기업별 필수 조건이나 직무 설명을 만들지 않는다 (A §8.3).
5. THE Mentoring_Package SHALL 팀 작성 상담 방법론 문서(`document_type = career_mentoring_methodology`)를 작성 방식 근거로만 쓰고, NCS 직무 필수 능력의 출처로 표시하지 않는다 (A §8.3).
6. THE Mentoring_Package SHALL 검색 결과 `chunkText`를 태그로 감싸 데이터로만 모델에 넘기고, 그 안의 지시문을 실행하지 않는다 (A UT-16, 제품 원칙 8).
7. THE Mentoring_Package SHALL `retrievalScore`를 사실 신뢰도나 합격률로 표시하지 않는다 (A §8.2).
8. WHERE KB를 쓸 수 없으면(환경변수 없음, 호출 실패), THE Mentoring_Package SHALL 분석을 실패시키지 않고 Reference_Lookup의 NCS 정형 데이터만으로 결과를 만들며, 결과에 `NO_EVIDENCE` 또는 `SOURCE_UNAVAILABLE` 경고를 남긴다 (A §10.3 "KB 미연결: CSV 기반 로컬 검색").

### Requirement 8: 적합도 결과 저장과 조회

**User Story:** As a 사용자, I want 분석 결과를 나중에 다시 열어 그때 기준으로 보기를, so that 공고가 바뀌거나 마감돼도 내가 본 근거를 다시 확인한다.

출처: A §4.5 `JobFitResult`, §6.3, db §2.1 `ANALYSIS#`, §12.1 "관심 공고 상세"

#### Acceptance Criteria

1. WHEN 분석이 끝나면, THE Task_Runner SHALL `ANALYSIS#{analysisId}`에 `assessmentMode`, `profileId`, `profileVersion`, `jobPostingId`, `snapshotId`, `ncsCode` 또는 `ncsCandidates`, `fitScore`, `potentialUpperBound`, `eligibilityStatus`, 조건별 판정, `ruleVersion`, Requirement_Link 목록, Gap_Result, `sources`, `warnings`, `scorePolicyVersion`을 저장한다 (db §2.1, A §4.5).
2. THE Mentoring_API SHALL `GET /analyses/{analysisId}` 응답을 A §6.3 예시의 필드 이름(`strengths`, `partialEvidence`, `unverifiedSkills`, `confirmedGaps`, `sources`, `warnings`)으로 돌려준다. 강점과 부분 증거에는 `evidenceId`를, 미확인 항목에는 확인 질문을 붙인다 (A §6.3).
3. THE Mentoring_API SHALL 분석 응답에 이력서 원문 전체를 넣지 않는다. Evidence 인용문은 그 사용자의 응답에만 넣는다 (A §12.2 `allowRawResume: false`의 원칙, 첫 스펙 Requirement 2 기준 6).
4. WHERE 분석이 `REQUIRES_USER_REVIEW`이면, THE Mentoring_API SHALL 사유 코드(`POSTING_NOT_READY`, `NCS_AMBIGUOUS` 등)와 사용자가 할 일을 함께 돌려준다 (A §6 "공통 정책" 상태 값).

### Requirement 9: 첨삭 요청과 입력

**User Story:** As a 사용자, I want 자기소개서 문항과 내 답변을 넣고 공고에 맞춘 첨삭을 받기를, so that 무엇을 고쳐야 하는지 문장 단위로 안다.

출처: A F-03 입력·처리 1~4단계·9단계·"실패 및 예외", §6.4, 첫 스펙 Requirement 9 기준 9 (Story_Item 조회 함수)

#### Acceptance Criteria

1. WHEN 사용자가 `POST /reviews`에 `documentId` 또는 `inputText`, `documentType`, 선택 `analysisId`·`jobPostingId`·`workspaceId`·`profileId`·`questionText`·`maxCharacters`·`storyIds`를 보내면, THE Mentoring_API SHALL `documentId`와 `inputText`가 둘 다 없거나 텍스트가 비어 있으면 400 `INVALID_INPUT`과 빠진 입력 이름(`missingInputs`)을 돌려준다 (A F-03 입력, "자소서 빈 텍스트 또는 대상 문항 없음").
2. THE Task_Runner SHALL 첨삭 대상 원문을 `documentId`면 그 Document_Version의 Normalized_Text에서, `inputText`면 요청 본문에서 읽는다. `inputText`를 저장하는 위치는 "이 스펙의 미결정" M-12에서 정한다 (A F-03 처리 1단계).
3. WHERE `analysisId`나 `jobPostingId`가 있으면, THE Task_Runner SHALL 그 분석이 고정한 Posting_Snapshot(또는 `LATEST`의 스냅샷)의 요건만 공고 기준으로 쓰고 `sourceJobSnapshotId`에 남긴다. 공고가 없으면 NCS 기준 일반 첨삭으로 하고 결과에 "공고 맞춤 첨삭이 아님"을 표시한다 (A F-03 "공고 미제공").
4. WHERE `storyIds`가 있으면, THE Task_Runner SHALL 첫 스펙의 Story_Item 조회 함수로 그 사용자의 경험 블록만 읽고, 사용자가 확인한 필드(`confirmedFields`) 값만 사실로 쓴다. 다른 사용자의 경험 블록 ID면 404로 처리한다 (A F-03 처리 4단계, 첫 스펙 Requirement 9 기준 8·9).
5. THE Mentoring_Package SHALL 글자 수를 코드로 계산해 글자 수(공백 포함·제외)와 UTF-8 바이트 수를 함께 돌려주고, `maxCharacters`를 넘으면 경고를 남긴다. 모델에게 글자 수를 세게 하지 않는다 (A F-03 처리 9단계).
6. THE Task_Runner SHALL 문항 의도를 지원동기, 직무경험, 협업, 갈등, 문제해결, 성장, 기타 중 하나로 분류해 결과에 남긴다 (A F-03 처리 3단계, 패키지 `agent/prompts/03_COVER_LETTER_STAR.md` 절차 1).

### Requirement 10: 첨삭 생성과 사실 검사

**User Story:** As a 사용자, I want 첨삭이 내가 하지 않은 경험이나 없는 수치를 넣지 않기를, so that 그대로 제출해도 거짓이 섞이지 않는다.

출처: A F-03 처리 5~8단계·"수정 결과 단위"·"실패 및 예외", §1.1 "첨삭이 … 허위 경험·수치를 추가하지 않음", F-07, UT-14, 패키지 `03_COVER_LETTER_STAR.md` 제약, 제품 원칙 5

#### Acceptance Criteria

1. THE Task_Runner SHALL 첨삭을 고정 JSON 스키마로 받는다. 항목마다 `sourceSpan{startChar, endChar}`, `issueType`, `reason`, `improvementAction`, `revisedExample`(없으면 `null`), `needsUserConfirmation`, `questions`, `usedStoryIds`를 두고, 전체에 `overallFeedback`, `strengths`, `factCheckStatus`를 둔다. 검사 실패는 한 번 다시 묻고 그래도 실패하면 `FAILED`, `AI_OUTPUT_INVALID`다 (A F-03 "수정 결과 단위", §4.5 `ReviewResult`).
2. FOR ALL 저장되는 첨삭 항목, `sourceSpan`으로 자른 원문이 비어 있지 않아야 하고 원문 범위 안에 있어야 한다. 맞지 않는 항목은 저장하지 않고, 남은 항목이 없으면 `REQUIRES_USER_REVIEW`로 둔다 (A F-03 "원문 스팬 매핑 불일치 → … 무조건 저장 금지").
3. THE Task_Runner SHALL `revisedExample`에 들어 있는 숫자, 기간, 자격, 직위, 수상, 회사·프로젝트 이름, 성과가 첨삭 원문, 사용자가 확인한 Story_Item 필드, Fact_Status가 `VERIFIED`인 Career_Profile 항목 중 하나에 있는지 코드로 대조한다 (A F-03 처리 7단계).
4. IF `revisedExample`에 근거 없는 사실이 들어 있으면, THEN THE Task_Runner SHALL 그 `revisedExample`을 `null`로 바꾸고 `needsUserConfirmation = true`와 그 사실을 묻는 확인 질문을 넣는다. 결과 `factCheckStatus`는 `NEEDS_CONFIRMATION`이다 (A F-03 처리 8단계, UT-14).
5. THE Task_Runner SHALL STAR 중 Task·Action·Result가 원문과 경험 블록에 없으면 그 부분을 지어낸 예시 문장 대신 최대 3개의 확인 질문으로 돌려준다 (패키지 `03_COVER_LETTER_STAR.md` 절차 4, A F-01B "DRAFT 상태로 STAR 성과 생성 금지").
6. THE Task_Runner SHALL 첨삭 원문과 공고 요건을 태그로 감싸 데이터로만 넘기고, 원문에 있는 지시문을 실행하지 않는다 (제품 원칙 8).
7. THE Task_Runner SHALL 원문에 학교, 나이, 성별, 출신지, 가족 관계 같은 직무와 관계없는 개인정보가 있으면 `issueType = BLIND_RISK` 항목으로 알린다. 이 정보를 평가 기준으로 쓰지 않는다. 지역인재 전형 같은 법정 자격은 공고 판정(Requirement 3)에서만 다룬다 (A F-03 "비공개·차별 가능 개인정보", "블라인드 공채").
8. THE Task_Runner SHALL 모델 입력 전에 이름·연락처·주민등록번호·주소 형태의 문자열을 가린다 (첫 스펙 Requirement 6 기준 2).

### Requirement 11: 첨삭 결과 저장

**User Story:** As a 사용자, I want 첨삭이 내 문서를 바로 바꾸지 않고 제안으로 남기를, so that 내가 고를 것만 반영한다.

출처: A F-03 처리 10~11단계, §6.4 "사용자 수락은 별도 문서 버전 저장 API(팀 워크스페이스 담당 소유)", §12.4, db §0 원칙 7, §2.1 `REVIEW#`, api §1 (`/api/v1/me/workspaces/{wsId}` PATCH 문서 버전)

#### Acceptance Criteria

1. WHEN 첨삭이 끝나면, THE Task_Runner SHALL 첨삭 본문(항목 목록)을 개인 문서 버킷 `users/{hashedUserId}/` 아래에 저장하고, `REVIEW#{reviewId}`에는 `resultKey`, `documentId`, `documentVersion`, `issueCount`, `factCheckStatus`, `sourceJobSnapshotId`, `usedStoryIds`, `promptVersion`만 둔다 (db §2.1, §0 원칙 7).
2. THE Mentoring_Package SHALL 첨삭 결과를 제안으로만 저장하고 Document_Version이나 워크스페이스 문서 버전을 바꾸지 않는다. 사용자가 수락한 최종본 저장은 BACKEND의 워크스페이스 API가 맡는다 (A F-03 처리 10단계, §12.4).
3. THE Mentoring_API SHALL `GET /reviews/{reviewId}`에서 S3의 첨삭 본문을 읽어 돌려주고, 첨삭 본문이나 원문 인용을 로그에 남기지 않는다 (첫 스펙 Requirement 12 기준 2).

### Requirement 12: 학습 경로 요청과 주차 계획

**User Story:** As a 사용자, I want 내 확인된 격차와 일주일에 쓸 수 있는 시간에 맞춘 학습 계획을 받기를, so that 무리 없는 순서로 준비한다.

출처: A F-05 입력·처리 1~3·6~7단계·"일정 추천 규칙"·완료 기준, §6.5, §4.5 `LearningPathResult`, 패키지 `agent/prompts/07_LEARNING_RECOMMENDATION.md`

#### Acceptance Criteria

1. WHEN 사용자가 `POST /learning-paths`에 `analysisId`, `weeklyStudyHours`, `preferredFormat`, 선택 `regionCode`·`targetDate`·`startDate`·`ncsCode`를 보내면, THE Mentoring_API SHALL `weeklyStudyHours`가 1~40 정수인지, `preferredFormat`이 `ONLINE`·`OFFLINE`·`HYBRID` 중 하나인지, `targetDate`가 As_Of 이후인지 검사하고 어긋나면 400 `INVALID_INPUT`을 돌려준다 (A F-05 입력, §6.5).
2. IF 분석의 NCS 코드가 하나로 정해지지 않았고 요청의 `ncsCode`가 분석의 `ncsCandidates`에 없으면, THEN THE Mentoring_API SHALL 400 `INVALID_INPUT`과 후보 목록을 돌려준다 (Requirement 2 기준 7).
3. THE Task_Runner SHALL 분석의 Gap_Result에서 확인된 격차는 학습 과제로, 미확인 항목은 학습 전에 먼저 할 확인 과제로 나눈다. 미확인 항목만 있는 경우에도 학습 과제를 지어내지 않는다 (A F-05 처리 1단계, F-04).
4. THE Mentoring_Package SHALL 주 수, 주별 시간, 총 시간을 코드로 계산한다. 주별 `estimatedHours`는 `weeklyStudyHours`를 넘지 않고, 총 시간은 `weeklyStudyHours × 주 수`를 넘지 않는다. `targetDate`가 없으면 기본 주 수를 설정 파일에서 읽는다 (A F-05 처리 6단계, 완료 기준 "사용자 주간 학습시간과 로드맵 총 학습시간 일관성 검증").
5. THE Task_Runner SHALL 주별 목표·실습·산출물 문장을 LLM_Port로 만들되, 학습 대상은 코드가 고른 능력단위와 Reference_Lookup의 학습 목표로 한정한다. 모델이 목록에 없는 능력단위나 자격을 넣으면 그 항목을 버린다 (A F-05 처리 2·7단계, tech.md "LLM은 도구가 준 사실만 설명").
6. THE Mentoring_Package SHALL 능력단위의 `training_hours`를 참고 정보로만 보여 주고, 개인의 실제 학습 기간이나 자격 취득 기간으로 표시하지 않는다. 추정 기간에는 "추정" 표시를 붙인다 (A F-05 "훈련시간 ≠ 실제 학습 기간", 첫 스펙 Requirement 10 기준 8).
7. IF 분석에 확인된 격차와 미확인 항목이 모두 없으면, THEN THE Task_Runner SHALL 빈 로드맵 대신 강점 심화 과제만 담은 결과와 그 사유를 돌려준다.

### Requirement 13: 자격·교육과정·시험일정 출처 검증

**User Story:** As a 사용자, I want 추천된 자격과 교육과정이 실제로 있고 날짜가 확인된 것만 보기를, so that 없는 시험이나 끝난 과정 때문에 계획을 잘못 세우지 않는다.

출처: A F-05 처리 3~4·8~10단계·"일정 추천 규칙"·완료 기준, §9 `OfficialDataPort`·"공통 API 어댑터", §6.5, AGENTS.md "노션 허브 자료" (외부 API 타임아웃 5초·재시도 1회), "데이터 소스" (국가자격 시험일정 하루 1,000건), UT-11·UT-12·UT-13

#### Acceptance Criteria

1. THE Mentoring_Package SHALL 자격 후보를 Reference_Lookup의 NCS–자격 연계에서만 만들고 `(능력단위, 자격, 구분)`으로 중복을 뺀다. 자격 정보(`QUAL#{qualCode}`)가 없는 후보는 넣지 않는다 (A F-05 처리 3~4단계, UT-13).
2. THE Mentoring_Package SHALL NCS–자격 연계를 그 기업의 필수 자격으로 표시하지 않는다 (A F-05 "자격증이 공식 NCS와 연결됐다고 해당 기업의 필수 자격은 아님").
3. THE Mentoring_Package SHALL 훈련과정과 시험일정을 Official_Data_Port 뒤에서만 읽는다. 외부 호출은 타임아웃 5초, 재시도 1회로 하고, 인증키는 Secrets Manager에서 서버 쪽에서 읽으며, 키가 들어간 URL을 로그에 남기지 않는다 (A §9, AGENTS.md "노션 허브 자료").
4. IF 시험일정을 확인하지 못하면, THEN THE Mentoring_Package SHALL 그 자격의 `schedule`을 `null`, `verificationStatus`를 `SCHEDULE_UNVERIFIED`로 두고 날짜·회차·접수 마감을 만들지 않는다. 공식 안내 링크만 붙인다 (A §6.5, F-05 "시험일정 미확인 시 날짜·회차·마감 생성 금지", UT-11).
5. WHERE 시험일정이 확인됐고 분석에 공고 마감일이 있으면, THE Mentoring_Package SHALL 시험일만이 아니라 합격 발표일과 공고 마감일을 비교해 결과가 마감 뒤에 나오면 경고를 붙인다. "지원 가능"으로 판단하지 않는다 (A F-05 "시험일 < 채용 마감일만으로 '지원 가능'이라고 판단하지 않음").
6. IF 조건에 맞는 교육과정이 0건이면, THEN THE Mentoring_Package SHALL 일반 실습 계획만 주고 `NO_LIVE_COURSES`를 남긴다. 모집 상태를 확인하지 못한 과정은 "모집 중"으로 표시하지 않는다 (A F-05, §9 "최신 교육정보 미검증이면 '모집 중'으로 확정 안내하지 않음", UT-12).
7. IF 연결된 외부 소스 하나가 실패하면, THEN THE Task_Runner SHALL 학습 경로 전체를 실패시키지 않고 상태를 `PARTIAL_SUCCESS`로, 실패한 소스를 `warnings`에 둔다. 소스가 아직 연결되지 않은 경우(Official_Data_Port 미설정)는 실패가 아니라 `sourceVerificationStatus`에 미연결로 표시한다 (A F-05 완료 기준 "API 장애 시 … PARTIAL_SUCCESS"). MVP에서 어떤 소스를 연결할지는 M-9에서 정한다.
8. FOR ALL 결과에 들어간 자격·교육과정 항목, `officialUrl`, `checkedAt`, `verificationStatus`가 있어야 한다. 셋 중 하나라도 없는 항목은 결과에서 뺀다 (A F-05 완료 기준).

### Requirement 14: 학습 경로 저장

**User Story:** As a 사용자, I want 만든 학습 경로를 다시 열어 보기를, so that 주차별로 따라간다.

출처: A F-05 처리 11단계, §4.5 `LearningPathResult`, db §2.1 `PATH#`

#### Acceptance Criteria

1. WHEN 학습 경로가 끝나면, THE Task_Runner SHALL `PATH#{pathId}`에 `analysisId`, `ncsCode`, 입력 조건, `weeks[{goals, activities, deliverable, estimatedHours, officialSources}]`, `verificationTasks`, `certificates[]`, `courses[]`, `sourceVerificationStatus`, `warnings`, `version`을 저장한다 (db §2.1, A §4.5).
2. THE Mentoring_Package SHALL 학습 경로 버전을 수정하지 않는다. 진행 체크와 수정 기록 저장은 A §6.1에 경로가 없어 "이 스펙의 미결정" M-11에서 정한다 (A F-05 처리 11단계).

### Requirement 15: 외부 서비스 없는 테스트

**User Story:** As a A 개발자, I want 이 스펙의 모든 기능을 AWS와 외부 API 없이 테스트하기를, so that 백엔드 연결(BE-1~BE-8) 전에도 완료 여부를 확인한다.

출처: A §10.3·§13, 첫 스펙 Requirement 11, D-37, 계약 `contracts/fixtures/valid/` (`PostingForAnalysis.json`, `JobRequirementView.json`)

#### Acceptance Criteria

1. THE Mentoring_Package SHALL Posting_Snapshot 읽기, Basic_Profile 읽기, Eligibility_Fn, KB 검색, Official_Data_Port를 각각 인터페이스 뒤에 두고, 테스트용 메모리 구현을 함께 둔다. 테스트용 Eligibility_Fn은 db §3.2 규칙을 따르는 가짜 구현이고 `backend/`를 import하지 않는다.
2. THE Mentoring_Package SHALL 다음 A §13 시나리오를 자동 테스트로 갖는다: UT-05(필수 자격 미충족), UT-06(우대 없는 공고 재정규화), UT-07(요건 0개), UT-08(반복 계산 동일), UT-09(잘못된 NCS 코드), UT-10(다른 직무 KB 문서 제외), UT-11(시험일정 실패), UT-12(교육과정 없음), UT-13(자격 연계 중복), UT-14(원문에 없는 수치 첨삭), UT-16(RAG 문서 속 지시문), UT-19(공고 변경·마감), INT-02(프로필 → 적합도 → 첨삭 → 학습).
3. THE Mentoring_Package SHALL 점수 계산에 속성 기반 테스트를 둔다: 임의의 Requirement_Link 목록에 대해 Requirement 5 기준 4(하한 ≤ 상한, 0~100)와 기준 1(반복 동일)이 성립해야 한다.
4. THE Mentoring_Package SHALL 통합 데모 직무 데이터 분석(NCS 20010105 빅데이터분석)의 가상 공고와 가상 이력서로 INT-02를 끝까지 실행하는 테스트를 갖는다. 공고는 실제 존재하는 공고가 아니고 `sourceType = DEMO`다 (D-37, A §4.4 "계약 예시이며 실제 존재하는 채용공고가 아님").

### Requirement 16: 로그와 지표

**User Story:** As a 운영 담당, I want 적합도·첨삭·학습 경로 실패를 개인정보 없이 추적하기를, so that 시연 중 원인을 찾는다.

출처: A F-08 "CloudWatch 커스텀 메트릭", 첫 스펙 Requirement 12

#### Acceptance Criteria

1. THE Mentoring_Package SHALL 첫 스펙 Requirement 12의 로그 규칙을 그대로 따르고, 첨삭 원문·수정 예시·Knowledge_Citation `chunkText`도 로그에 남기지 않는다.
2. THE Mentoring_Package SHALL `AnalysisLatency`, `LLMSchemaFailure`, `EvidenceValidationFailure`에 더해 `FactCheckRejected`(첨삭 사실 검사로 뺀 예시 수), `KbNoEvidence`, `OfficialSourceFailure` 지표를 CloudWatch EMF 형식 로그로 남긴다 (A F-08, db §2.7).

## 백엔드(BACKEND) 담당 작업

첫 스펙의 BE-1~BE-7에 더해 이 스펙에 필요한 것이다. 현황은 2026-11-20 `main`(`97d69c8`) 기준으로 코드에서 확인했다. A는 이 파일들을 고치지 않고 백엔드 담당에게 요청한다.

### 바꿔야 하는 것

| ID | 할 일 | 바꿀 파일 | 지금 상태 | 관련 |
| --- | --- | --- | --- | --- |
| BE-4 (보강) | 첫 스펙 BE-4 목록에 `TABLE_REFERENCE`(`team07-reference`)와 `KB_ID`를 넣는다. `KB_ID`는 저장소에 적지 않고 `infra/config.sh`의 KB 이름(`team07-career-mentor-kb`)으로 실행할 때 조회해 넣는다. `TABLE_CATALOG`는 이미 있어 그대로 쓴다 | `infra/setup-api.sh` (`ENV_VARS`) | `TABLE_CATALOG`, `MODEL_ID`, `TABLE_CAREER_MENTOR`, `CAREER_DOCS_BUCKET`은 있다. `TABLE_REFERENCE`, `KB_ID`는 없다 | Requirement 2 기준 5, Requirement 7 기준 1 |
| BE-8 | A 의존성을 만들 때 `eligibility.evaluate_eligibility`를 넣는다. B의 `build_aws_deps(eligibility=…)`와 같은 방식 | `backend/mentoring_api.py` (BE-1에서 새로 만드는 파일) | B는 `backend/opportunities_api.py`에서 넣고 있다. A 입구는 아직 없다 | Requirement 3 기준 2, D-11, D-41 |
| BE-9 | M-9에서 외부 소스를 연결하기로 하면, 고용24·공공데이터포털 인증키를 Secrets Manager `team07/…` 이름으로 등록한다 | AWS 콘솔·CLI (저장소 변경 없음) | 키는 노션 표에만 있다. 실행 역할에 `team07/*` 읽기 권한은 있다 | Requirement 13 기준 3, M-9 |

### 이미 있어서 바꿀 필요 없는 것

| 항목 | 위치 | 관련 |
| --- | --- | --- |
| 작업 종류 `JOB_FIT`, `REVIEW`, `LEARNING_PATH` | db §2.5 | Requirement 1 기준 1 |
| 결과 키 `ANALYSIS#`, `REVIEW#`, `PATH#`와 워크스페이스 GSI1 | db §2.1, api §6.0 | Requirement 1 기준 4, Requirement 8·11·14 |
| 공고 스냅샷 `SNAP#`·`LATEST`, `eligibilityRules[]` | db §3·§3.2 (B가 채움) | Requirement 2·3 |
| 기본 프로필 `PROFILE#BASIC` (학력·전공·경력) | db §2.1, `backend/me_api.py` | Requirement 3 기준 1 |
| 사용자가 수락한 첨삭 최종본 저장 (워크스페이스 문서 버전) | `PATCH /api/v1/me/workspaces/{wsId}` | Requirement 11 기준 2 |
| 실행 역할: catalog·reference 읽기, KB `Retrieve`, Secrets Manager `team07/*` 읽기, Bedrock 호출 | `infra/iam/lambda-role-policy.json` | Requirement 2·7·13 |
| Lambda 시간 제한 300초 | `infra/setup-api.sh` | Requirement 1 (비동기 작업) |

### 실행 전에 사용자 확인이 필요한 AWS 작업

- `team07-reference`에 NCS CSV 실제 쓰기 (첫 스펙 Requirement 10 기준 5). 이 스펙의 NCS 모드, 격차, 학습 경로가 운영에서 이 데이터를 읽는다. 2026-11-20 미리 보기 결과는 206건(직무 프로필 11, 능력단위 135, 직업기초능력 34, 자격 5, 자격 연계 21)이다.
- BE-9 비밀정보 등록과 BE-4·BE-8 반영 뒤 배포.

## 이 스펙의 미결정

첫 스펙의 M-1~M-7에 이어 번호를 붙인다. 결정 전까지 해당 기준은 인터페이스 뒤에 둔다.

| ID | 항목 | 선택지 | 관련 |
| --- | --- | --- | --- |
| M-8 | 점수의 "관련 경험 근거"(0.1) 분류에 무엇을 넣을지 | 사용자가 확인한 Story_Item 중 요건과 연결된 것 / Career_Profile `experiences` / MVP에서는 비워 두고 재정규화 | Requirement 5 기준 2·3. A F-02는 가중치만 있고 항목의 원천이 없다. 공고 `requirements[].kind`에는 경험 분류가 없다 (D-10) |
| M-9 | 고용24 훈련과정·국가자격 시험일정을 MVP에서 실제로 연결할지 | 둘 다 연결 / 시험일정만 / MVP는 미연결(`SCHEDULE_UNVERIFIED`·`NO_LIVE_COURSES` + 공식 안내 링크) | Requirement 13, BE-9. 시험일정 키는 발급됨(하루 1,000건). 훈련과정 승인 상태는 노션 표에서 확인 필요 |
| M-10 | 부산 청년지원 프로그램 안내 (A F-05 처리 10단계) | B 정책 지갑 화면 링크만 / `team07-catalog` `POLICY#`를 A가 읽어 교육 관련 정책만 붙임 | 정책 데이터와 정책 지갑은 B 소유 (B-08). A가 같은 기능을 다시 만들지 않는다 |
| M-11 | 학습 진행 체크·수정 기록 저장 경로 | `PATCH /learning-paths/{id}`로 새 버전 / MVP에서 뺌 | Requirement 14 기준 2. A §6.1에 경로가 없다 |
| M-12 | 첨삭 `inputText` 원문 저장 위치 | `POST /documents/text`와 같은 Document로 저장(첫 스펙 경로 재사용, 역량 추출은 하지 않음) / 첨삭 결과와 함께 `users/{hashedUserId}/reviews/` 아래에만 저장 | Requirement 9 기준 2. 원문은 S3에만 둔다 (db §0 원칙 7) |
