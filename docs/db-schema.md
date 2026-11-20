# DB 스키마 (v1.4.1)

7팀 · 부산 청년 취업 맞춤형 멘토링 Agent
작성: 백엔드/DB 담당 · 기준: A(멘토링) 개발 명세서 v2.0, B(부산 기회 추천) DB·API 스키마 v0.1, C(AI 모의면접) 개발명세서
상태: **A·B·C 피드백 반영, 파트 간 충돌 정리 완료 (2026-11-20)** · 공통 API 규칙은 `docs/api.md`

| 버전 | 내용 |
|---|---|
| v1.0 | 초안 |
| v1.1 | 면접 담당 요청, 멘토링 담당 피드백 반영 (Workspace, GSI에 userId, `*_LATEST#`, 문서 버전, TASK, 삭제 규칙, 평가 로그) |
| v1.2 | B 피드백 반영: 공고·정책·기업은 `team07-catalog`(B 설계), B 사용자 데이터는 `career-mentor`의 `OPP#`, 공통 프로필은 `PROFILE#BASIC`로. 알림 ID 형식, 저장 공고 ↔ 워크스페이스 연결 규칙 추가 |
| v1.6 | B: 공고 이름 색인 `POSTNAMES` / `POSTING#{jobPostingId}` 추가. 검색어·회사 이름 검색에 쓴다 (`ai/busan-opportunity/DECISIONS.md` B-D08) |
| v1.7 | `team07-catalog`: 공고 `regionalTalent`에 `conditions[]{kind, sido, sigungu, label}`(공고문에서 읽은 지역 조건) 추가. 지역 조건 색인 `INDEX#REGIONAL` / `POSTING#{id}` 추가 (`ai/busan-opportunity/DECISIONS.md` B-D09) |
| v1.5 | 기본 정보 화면: `PROFILE#BASIC`에 `schoolName`(대학 이름, 전문대 이상, 50자)·`certificates[]`(가진 자격증, 10개, 50자) 추가. `universityRegion`은 최종 학교 소재지로 쓴다 (대학원이면 학부 대학, 고졸이면 고등학교). 지역인재 판정과 자격 요건 비교에 쓴다 |
| v1.4.1 | 모의면접 세션 필드 반영: 답변 기록 `followUpCheck`(#152), 캡처 `reason`·`session.baseline` 형식(#115) |
| v1.4 | 채팅 Agent (D-38~D-40, `docs/개발계획서4.md` §8): `SESSION#`·`CHAT#{sessionId}#{messageId}` 필드 확정, `PROFILE#BASIC`에 `desiredSalaryMin`·`desiredCareerType` 추가. 면접 `documentId`는 `DOC_LATEST#`에 `extractedTextKey`가 없으면 `DOC#{id}#V#{n}`의 `textKey`를 읽는다 |
| v1.3.1 | C 명세 변경 반영 (`transcriptKey`, `eyesOpen`, `baseline=None`) |
| v1.3 | 파트 간 충돌 정리: `eligibilityRules[]` 구조와 공통 판정 함수, 고용24·NCS 직무 코드 병행 + 매핑(`MAP#WORK24#`), 요건 종류 `REQUIRED_SKILL`/`PREFERRED_SKILL`, 옛 테이블 4개 삭제, `team07-reference` 생성 |

---

## 0. 설계 원칙

1. **데이터의 주인으로 테이블을 나눈다.** 사용자 개인 데이터 / 공고·정책·기업(B가 쓰고 모두 읽음) / 공식 기준 데이터 / 캐시.
2. **사용자 데이터는 전부 `team07-career-mentor`의 `PK = USER#{userId}`.** 회원 탈퇴 때 이 PK만 지우면 모든 파트 데이터가 같이 지워진다. userId는 인증 정보에서만 읽는다 (§6).
3. **파트별 SK 접두사:** 공통·A·C는 엔티티 이름(`WORKSPACE#`, `DOC_LATEST#`, `INTERVIEW#` …), B는 `OPP#`.
4. **GSI로 읽어도 소유자를 다시 확인한다.** GSI 키에도 userId를 넣고, 읽은 뒤 `ownerUserId`를 인증 사용자와 비교한다.
5. **결과는 수정하지 않고 버전으로 쌓는다.** 버전 `X#{id}#V#0001`, 목록용 최신 포인터는 별도 접두사 `X_LATEST#{id}`.
6. **버전과 최신 포인터는 한 트랜잭션으로 쓴다.** `TransactWriteItems` + `latestVersion = :expected` 조건. 실패하면 409 `PRECONDITION_NOT_MET`.
7. **원문은 S3, DB에는 키와 메타만.** (400KB 한도)
8. **TTL은 임시 데이터에만.** 사용자 문서·분석 결과·공고 스냅샷은 자동 삭제하지 않는다. TTL 속성 이름은 `expiresAt` 하나로 통일.
9. **Scan 금지.** GetItem·Query·GSI·S3 Vectors로 끝나게 키를 잡는다.

## 1. 테이블 한눈에

| 테이블 | 쓰는 쪽 / 읽는 쪽 | 담는 것 |
|---|---|---|
| `team07-career-mentor` | 공통·A·B·C | 사용자의 모든 데이터: 공통 프로필, 워크스페이스, 문서, 역량 프로필, 경험 블록, 분석·첨삭·로드맵, 대화, 모의면접, B 사용자 상태(`OPP#`), 작업 상태 |
| `team07-catalog` | B가 씀 / 모두 읽음 | 공고 스냅샷·최신, 부산 대안 후보, 청년정책, 기업 (§3) |
| `team07-reference` | A | NCS 직무·능력단위·자격 연계 (ZIP CSV) |
| `team07-cache` | A | 외부 API 응답 캐시 (훈련과정·시험일정 등). 청년정책은 B가 catalog에 매일 넣으므로 캐시하지 않는다 |

공통 속성: `entityType`, `schemaVersion`, `ownerUserId`(사용자 데이터), `createdAt`, `updatedAt` (ISO 8601 +09:00).

---

## 2. `team07-career-mentor`

키: `PK`, `SK` · GSI1: `GSI1PK`, `GSI1SK` · TTL: `expiresAt`

### 2.1 공통·A·C 엔티티

| 엔티티 | SK | GSI1PK / GSI1SK | 주요 필드 |
|---|---|---|---|
| **공통 프로필** (모두 읽음) | `PROFILE#BASIC` | — | `birthYear`, `residenceSido`, `residenceSigungu`, `residenceSince`, `universityRegion`(최종 학교 소재지), `schoolName`, `certificates[]`, `graduationStatus`, `employmentStatus`, `monthlyIncome`, `householdIncomeLevel`, `desiredJobs[]`, `desiredRegion`, **`educationLevel`(`HIGH_SCHOOL`/`ASSOCIATE`/`BACHELOR`/`MASTER`/`DOCTOR`), `major`, `priorities[]`** (B 요청), `careerYears`, **`desiredSalaryMin`(정수, 만 원/년), `desiredCareerType`(`NEW`/`EXPERIENCED`/`ANY`)** (채팅 조건 저장 D-40), `talentPoolConsent`(예약, 기본 false), `isDemo`(데모 계정). `desiredJobs[] = [{work24Code, ncsCode, name}]` 최대 3개 |
| **워크스페이스** | `WORKSPACE#{wsId}` | `USER#{u}#WSLIST` / `{status}#{updatedAt}` | `workspaceId`, `jobPostingId`, `snapshotId`, `targetNcsCode`, `status`, `selectedDocuments{RESUME, COVER_LETTER: {documentId, version}}`, `latestAnalysisId`, `latestReviewId`, `latestLearningPathId`, `latestInterviewId` |
| 문서 (최신·목록용) | `DOC_LATEST#{docId}` | — | `documentId`, `documentType`, `title`, `latestVersion`, 최신 버전의 `s3Key`·`extractedTextKey`·`extractionStatus` 사본. 업로드 완료 전(`PENDING`)에만 `expiresAt`(발급 후 24시간) |
| 문서 버전 | `DOC#{docId}#V#0001` | — | `version`, `parentVersion`, `s3Key`, `extractedTextKey`, `extractionStatus`, `sourceDocumentId`, `relatedStoryIds[]`, `checksum`, `sizeBytes`. 업로드 완료 전(`PENDING`)에만 `expiresAt`(발급 후 24시간), 완료하면 뺀다 |
| 역량 프로필 (최신) | `PROFILE#LATEST` | — | `latestProfileId`, `latestVersion` |
| 역량 프로필 버전 | `PROFILE#{profileId}#V#0001` | — | `skills[]`, `evidence[]`, `projects[]`, `certificates[]`, `needsConfirmation[]`, `sourceDocumentIds[]`, `modelId`, `promptVersion` |
| 경험 블록 (최신·목록용) | `STORY_LATEST#{storyId}` | — | `storyId`, `title`, `status`, `latestVersion` |
| 경험 블록 버전 | `STORY#{storyId}#V#0001` | — | `situation`, `task`, `actions[]`, `result`, `learning`, `confirmedFields[]`, `status` |
| 직무 적합도 분석 | `ANALYSIS#{analysisId}` | `USER#{u}#WS#{wsId}` / `ANALYSIS#{createdAt}#{analysisId}` | `profileId`, `profileVersion`, `jobPostingId`, `snapshotId`, `fitScore`, `potentialUpperBound`, `eligibilityStatus`, `strengths[]`, `gaps`, `scorePolicyVersion`, `sources[]` |
| 첨삭 | `REVIEW#{reviewId}` | `USER#{u}#WS#{wsId}` / `REVIEW#{createdAt}#{reviewId}` | `documentId`, `documentVersion`, `resultKey`(S3), `issueCount`, `factCheckStatus`, `promptVersion` |
| 학습 경로 | `PATH#{pathId}` | `USER#{u}#WS#{wsId}` / `PATH#{createdAt}#{pathId}` | `analysisId`, `weeks[]`, `certificates[]`, `courses[]`, `sourceVerificationStatus`, `version` |
| 모의면접 | `INTERVIEW#{ivId}` | `USER#{u}#WS#{wsId}` / `INTERVIEW#{createdAt}#{ivId}` | §2.4 |
| 비동기 작업 | `TASK#{taskId}` | `TASK#{status}` / `{updatedAt}#{u}#{taskId}` | §2.5 |
| 대화 세션 | `SESSION#{sessionId}` | — | `sessionId`(`chat-…`), `workspaceId`, `title`, `pendingMessageId`, `pendingSince`, `messageCount`, `lastMessageAt`, `pinned`(대화 목록 위에 고정, 기본 false) (채팅 Agent, `docs/개발계획서4.md` §8) |
| 대화 메시지 | `CHAT#{sessionId}#{messageId}` | — | `messageId`(`{yyyyMMddTHHmmssSSS}-{16진 6자}`, 시간순 정렬), `role`, `content`, `status`(`PENDING`·`PROCESSING`·`COMPLETED`·`FAILED`·`CANCELLED`), `followUps[]`, `cards[]`, `actions[]`, `toolCalls[{name, ok, durationMs}]`, `attachments[{documentId}]`, `modelId`, `promptVersion`. 도구 인자·결과 원문은 두지 않는다 |
| 평가 로그 (선택) | `EVAL#{analysisId}#{evaluationId}` | — | §2.7. MVP는 CloudWatch 로그만 |
| 멱등 키 | `IDEM#{key}` | — | `requestHash`, `resultId`, `expiresAt`(24시간) |
| 계정 상태 | `ACCOUNT` | — | `status`(`ACTIVE`/`DELETING`) (§2.6) |

### 2.2 B 엔티티 (`OPP#`)

| 엔티티 | SK | GSI1PK / GSI1SK | 주요 필드 | TTL |
|---|---|---|---|---|
| B 설정 | `OPP#PREFS` | — | `sort`, `leaveReason`, `leaveReasonAskedAt`, `notifications{email, weekly}`, `receivingPolicies[]`, `demoAsOf` | 없음 |
| 저장·목표 공고 | `OPP#SAVED#{jobPostingId}` | 비부산 공고만: `WATCH#{jobMajor}` / `USER#{u}` (P1) | `kind`(INTEREST, TARGET), `workspaceId`, `snapshotId`, `isBusan`, `jobMajor`, `fromAlternativeOf`, `savedAt`, `scheduleNames[]` | 없음 |
| 정책 알림 신청 | `OPP#ALERT#{policyId}` | — | `scheduledAt`, `scheduleName`, `checks` | 없음 |
| 알림함 | `OPP#NOTI#{notificationId}` | — | `type`(POLICY_OPEN, POLICY_CLOSING, TARGET_DEADLINE, NEW_BUSAN_SIMILAR, WEEKLY_REPORT), `title`, `body`, `link`, `read`, `channel` | 90일 |
| 즉시 알림 횟수 | `OPP#CAP#{yyyy-Www}` | — | `immediateCount` | 2주 |
| 설명 문장 캐시 | `OPP#EXPL#{jobPostingId}` | — | `sentences[]`, `factsHash` | 24시간 |

- **`notificationId = {yyyyMMddTHHmmss}-{해시 8자}`** (예: `20261121T101200-a1b2c3d4`). B 초안의 `{createdAt}#{해시}`는 `/notifications/{notificationId}/read` 주소에 들어가는데, 주소의 `#`는 그 뒤를 서버로 보내지 않아 요청이 깨진다. 시각이 앞에 있어 `OPP#NOTI#` 정렬(최신순)은 그대로다.
- 멱등 처리는 공통 `IDEM#` 조건부 쓰기 (B 초안 그대로).
- GSI1은 아이템마다 값이 하나라 겹치지 않는다. `OPP#SAVED#`는 `WATCH#`만 쓰고, 워크스페이스와의 연결은 아래처럼 `WORKSPACE#` 아이템이 GSI1을 갖는다. **GSI2는 필요 없다.**

### 2.3 저장 공고 ↔ 워크스페이스 (B 질문에 대한 답)

- **잇는다.** 공고를 저장하면(INTEREST든 TARGET이든) 그 공고의 워크스페이스가 생긴다. A 명세의 "저장한 공고마다 분석·자소서·면접·학습을 한곳에서" 흐름.
- **만드는 곳: 공통 백엔드 함수** `ensure_workspace(userId, jobPostingId, snapshotId)`. B의 `POST /saved`가 이 함수를 부르고, `OPP#SAVED#`와 `WORKSPACE#`를 **한 트랜잭션**으로 쓴다. 이미 있으면 기존 워크스페이스를 돌려준다(`attribute_not_exists` 조건).
- **지원 상태는 `WORKSPACE#.status` 한 곳에만 둔다.** 값은 B의 상태 그대로: `INTEREST` · `PLANNED` · `PREPARING` · `APPLIED` · `RESULT` (+ 지원을 접으면 `CLOSED`). `OPP#SAVED#`에는 상태를 두지 않아 두 곳 값이 어긋날 일이 없다. B의 `GET /saved`는 `OPP#SAVED#` Query 후 워크스페이스를 BatchGet.
- **저장을 풀면** (`DELETE /saved/{id}`) `OPP#SAVED#`와 마감 일정만 지우고 `WORKSPACE#`는 남긴다. 다시 저장하면 같은 워크스페이스에 이어 붙는다.
- `workspaceId = ws-{jobPostingId}` (공고 없이 NCS 직무로 만들면 `ws-ncs-{ncsCode}`). 사용자 PK 안에서만 유일하면 되므로 GetItem 한 번으로 "이 공고의 내 워크스페이스"를 찾는다.

### 2.4 모의면접 (C와 합의)

| SK | 내용 |
|---|---|
| `INTERVIEW#{ivId}` | `session`(면접 함수가 준 그대로) + 백엔드 관리 값: `status`, `stage`, `expectedAnswerId`, `submittedAnswerIds[]`, `transcribeJobs{answerId: {jobName, audioKey, transcriptKey, timeLimitReached}}`, `nextQuestion`, `lastAnswer`, `jobRole`(= session.job), `workspaceId` |
| `INTERVIEW#{ivId}#FRAME#{answerId}#{capturedAt}` | `type`(CALIBRATION/ANSWER), `accepted`, `valid`, `reason`(분석 제외 사유, `valid=false`일 때: `INVALID_IMAGE`/`NO_FACE`/`MULTIPLE_FACES`/`LOW_CONFIDENCE`/`FACE_OCCLUDED`/`TOO_DARK`/`BLURRY`/`ANALYSIS_FAILED`. 감점 아님), `gaze`, `head`, `eyesOpen{value, confidence}` (눈 감음 판단은 점수 계산 단계). **이미지는 저장하지 않음**. 보정 캡처는 answerId 자리에 `CALIBRATION` |
| `INTERVIEW#{ivId}#REPORT` | `report`. 다시 열면 이 값을 그대로 반환 |
| `INTERVIEW#{ivId}#Q#{questionId}` (선택) | 조회용 요약만 |

- `ivId` = 면접 명세의 `sessionId` (UUID, 백엔드 생성). 중복 제출은 조건부 쓰기 → 409. 제출 뒤 캡처는 `accepted=false`
- `compute_baseline`은 리포트 직전 `CALIBRATION` 캡처로 → `session.baseline = {gaze{yaw, pitch}, head{yaw, pitch}}`(유효 캡처의 중앙값). 유효 3장 미만이면 `None`(태도 미측정)이고 백엔드는 대체값을 넣지 않는다
- `session`의 답변 기록에는 `followUpCheck`(꼬리질문 판단 결과 `ABSTRACT`/`INCONSISTENT`/`SUFFICIENT`/`JUDGE_FAILED`, #152)가 있다. 판단이 실패해도 면접은 꼬리질문 없이 이어지고 `JUDGE_FAILED`로 남는다. 백엔드는 `session`을 그대로 저장하므로 따로 다루지 않는다. 이 필드가 생긴 뒤 이전 면접 패키지로 되돌리면 진행 중 세션을 못 읽을 수 있다
- Transcribe 결과는 백엔드가 정한 `uploads/interview/{ivId}/transcripts/{answerId}.json`에 저장(`start_transcription`의 `output_bucket`·`output_key`). 답변 원문이 들어 있어 녹음과 함께 바로 삭제
- `start_interview` 입력: `resumeText` 또는 `documentId` → `DOC_LATEST#`의 `extractedTextKey`(없으면 `DOC#{id}#V#{n}`의 `textKey`, #151). 저장된 역량 프로필은 `PROFILE#LATEST`가 가리키는 버전을 A의 `to_career_profile_summary()`로 변환해 넘긴다. 변환 결과가 없거나 계약 검사를 통과하지 못하면 `profile=None`이다.
- 녹음은 변환 끝나면 바로 삭제, `uploads/` 7일 자동 삭제는 안전장치
- 구현 `backend/interview_api.py` · 테스트 `backend/test_interview.py`

### 2.5 비동기 작업 `TASK#{taskId}`

| 필드 | 값 |
|---|---|
| `status` | `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED` |
| `taskType` | `DOCUMENT_EXTRACT`, `PROFILE_EXTRACT`, `JOB_FIT`, `REVIEW`, `LEARNING_PATH`, `EXTERNAL_POSTING_ANALYSIS`(B, P1) |
| `resourceId`, `resultId` | 대상 ID, 완료 시 결과 ID (폴링 응답에 그대로) |
| `retryCount`, `errorCode`, `retryable` | 실패 구분 |
| `startedAt`, `completedAt`, `updatedAt` | 시각 |

- 상태 전이는 조건부 쓰기(`status = :expected`)로만
- 뒤에서 처리: SQS 권한 전까지 Lambda 비동기 자기 호출

### 2.6 회원 탈퇴·삭제

1. `ACCOUNT.status = DELETING` → 모든 쓰기(작업 Lambda, B 배치 포함)는 이 값을 확인하고 저장
2. Query `PK = USER#{u}` 페이지네이션 → `BatchWriteItem` 25개씩, `UnprocessedItems`는 지수 백오프 재시도. **`OPP#` 아이템도 같은 PK라 함께 지워진다**
3. S3: `career-docs/users/{hashedUserId}/`, `career-docs/pending/users/{hashedUserId}/`(업로드 완료 전 원본), `uploads/interview/{ivId}/`. 개인 문서 저장과 회원 탈퇴 삭제는 모두 `backend/common.py`의 `hash_user_id()`를 사용한다. 인증된 Cognito `sub`의 UTF-8 바이트를 SHA-256으로 해시한 소문자 64자리 16진수이며, 접두사를 안정적으로 다시 계산할 수 있도록 키나 솔트를 사용하지 않는다. 해시는 인증이나 접근 제어를 대신하지 않는다.
4. B의 EventBridge 일정(`scheduleNames[]`, `OPP#ALERT#.scheduleName`)은 아이템을 지우기 전에 읽어서 삭제 (B 함수 호출)
5. 마지막에 `ACCOUNT` 삭제. 단계별 건수만 로그로

### 2.7 AI 품질 평가 로그

MVP는 CloudWatch 구조화 로그(EMF). 필드 `evaluationId`, `requestId`, `analysisId`, `feature`, `modelVersion`, `promptVersion`, `schemaValid`, `groundingStatus`, `latencyMs`, `errorCode`, `createdAt`. 화면에서 이력을 봐야 하면 `EVAL#` 엔티티 추가. 원문·인증키는 남기지 않는다.

### 2.8 자주 쓰는 조회

| 하고 싶은 것 | 방법 |
|---|---|
| 추천·판정용 프로필 | GetItem `PROFILE#BASIC` (+ B는 `OPP#PREFS`) |
| 내 워크스페이스 목록 (상태별·최근순) | GSI1 `USER#{u}#WSLIST`, `begins_with(GSI1SK, "PREPARING#")` |
| 특정 공고의 내 워크스페이스 | GetItem `WORKSPACE#ws-{jobPostingId}` |
| 워크스페이스의 분석·첨삭·로드맵·면접 | GSI1 `USER#{u}#WS#{wsId}` → `ownerUserId` 재확인 |
| 내 문서 / 경험 블록 목록 (최신만) | Query `begins_with(SK, "DOC_LATEST#")` / `"STORY_LATEST#"` |
| 문서 이전 버전 | Query `begins_with(SK, "DOC#{docId}#V#")` |
| 내 저장 공고 | Query `begins_with(SK, "OPP#SAVED#")` → 워크스페이스 BatchGet |
| 내 알림함 (최신순) | Query `begins_with(SK, "OPP#NOTI#")`, `ScanIndexForward=false` |
| 비슷한 공고를 저장한 사용자 (B, P1) | GSI1 `WATCH#{jobMajor}` |
| 작업 상태 | GetItem `TASK#{taskId}` |

---

## 3. `team07-catalog`: 공고·정책·기업 (B 설계, B 배치만 씀)

키: `PK`, `SK` · GSI1: `GSI1PK`, `GSI1SK` · **Streams: NEW_IMAGE** (B-12 새 부산 공고 매칭, P1) · TTL 없음

| 엔티티 | PK | SK | GSI1PK / GSI1SK | 주요 필드 |
|---|---|---|---|---|
| 공고 스냅샷 | `POSTING#{jobPostingId}` | `SNAP#{snapshotId}` | — | **팀 필드:** `title`, `organization`, `companyId`, `jobDescription`, `requirements[]{requirementId, name, kind(REQUIRED_SKILL/PREFERRED_SKILL), weight, sourceQuote}`, `eligibilityRules[]{ruleId, type, value, sourceQuote}`(§3.2), `closesAt`, `officialUrl`, `sourceType`, `checkedAt`. **B 필드:** `source`, `company{name, bizNo, hqSido}`, `orgType`, `workRegion{sido, sigungu, label}`, `job{code(고용24), middle, major, name, ncsCodes[]}`, `employmentType`, `careerType`, `educationMin`, `salary{disclosed, min, max, unit}`, `rolling`, `remoteWork`, `selectionSteps`, `documents`, `badges[]`, `regionalTalent{status, basis, conditions[]{kind(NON_CAPITAL/SCHOOL/RESIDENCE/SCHOOL_OR_RESIDENCE/UNKNOWN), sido, sigungu, label}}`, `extractStatus`, `extractedBy`, `contentHash` |
| 공고 최신 | `POSTING#{jobPostingId}` | `LATEST` | `POSTING#{시도코드}` / `closesAt` | `snapshotId`, `title`, `organization`, `isExpired`, `isSample`, 목록용: `isBusan`, `isCapitalArea`, `workRegion`, `job`, `salary`, `remoteWork`, `badges[]` |
| 공고 이름 색인 | `POSTNAMES` | `POSTING#{jobPostingId}` | — | `jobPostingId`, `organization`, `title`, `jobName`, `closesAt`. 진행 중 공고만 둔다. `LATEST`를 쓸 때 같이 쓰고 마감 처리하면 지운다 (B-D08) |
| 부산 대안 후보 | `POSTING#{jobPostingId}` | `ALTS` | — | `candidates[{jobPostingId, similarity}]` (최대 10), `computedAt` |
| 청년정책 | `POLICY#{policyId}` | `META` | `POLICY#{시도코드}` / `applyEnd` | `title`, `summary`, `amountMax`, `ageMin`, `ageMax`, `residenceRule`, `incomeRule`, `applyStart`, `applyEnd`, `url`, `source`, `kind`, `regions[]`, `category`, `stage`, `eligibility{…}`, `benefit{…}`, `application{…}`, `lastCycle`, `exclusiveWith[]`, `checklist[]`, `verified`, `verifiedBy`, `verifiedAt`, `youthcenterId` |
| 지역 조건 색인 | `INDEX#REGIONAL` | `POSTING#{jobPostingId}` | — | `jobPostingId`, `closesAt`. 공고문에 지역 조건이 있는 진행 중 공고만. 수집·보강이 `LATEST`를 쓸 때 넣고, 조건이 없어지거나 마감되면 지운다 |
| 기업 | `COMPANY#{companyId}` | `META` | `COMPANY#{시도코드}` / `name` | `name`, `bizNo`, `industry`, `size`, `highlights[]`, `source`, `asOf` |

규칙 (B 초안)

- **스냅샷:** 내용(`contentHash`)이 바뀔 때만 새 `SNAP#`을 쓰고 `LATEST`를 바꾼다. 마감돼도 지우지 않고 `LATEST.isExpired = true`. A는 분석에 `snapshotId`를 저장하고, 나중에 `SNAP#{snapshotId}`로 그 시점 공고를 읽는다 → **A의 스냅샷 요청 해결**
- 목록 화면은 `LATEST`만, 스냅샷은 상세에서만 읽는다
- 상시 채용 `closesAt`, 상시 정책 `applyEnd` = `9999-12-31` (정렬 키가 없으면 GSI에서 빠짐). 공고엔 `rolling=true`도
- 전국 정책 `POLICY#00`, 구 단위 정책은 시·도 키(`POLICY#26`)에 두고 `regions[]`로 거른다
- 요건 추출 전에는 `requirements` 비어 있고 `extractStatus=PENDING`. 추출하면 같은 스냅샷에 채운다 (원문이 같으므로)

조회 (B 초안)

| 하고 싶은 것 | 방법 |
|---|---|
| 공고 여러 개 목록 | 후보 ID는 S3 Vectors → BatchGetItem `LATEST` |
| 검색어·회사 이름으로 공고 찾기 | Query `PK = POSTNAMES` → 맞는 ID를 BatchGetItem `LATEST`. 벡터 후보에 더한다 (B-D08) |
| 공고 상세 | GetItem `LATEST` → GetItem `SNAP#{snapshotId}` |
| 부산 공고 마감 임박순 | GSI1 `POSTING#26`, `GSI1SK >= 오늘` |
| 부산 대안 후보 | GetItem `ALTS` |
| 지역 혜택 필터 후보 | Query `PK = INDEX#REGIONAL` (`closesAt >= 오늘`) → BatchGetItem `LATEST` |
| 지역 정책 | GSI1 `POLICY#26` / `POLICY#11` / `POLICY#00` |
| 직무 코드별·기업별·유사 공고 | S3 Vectors 메타데이터 필터 (`jobMajor`, `sido`, `isBusan`, `active`, `deadline`) |

### 3.1 A의 JobRequirement 요청 ↔ catalog

| A 요청 | catalog | 상태 |
|---|---|---|
| jobPostingId, snapshotId | `POSTING#` / `SNAP#` | ✅ |
| companyId, organization | `companyId`(스냅샷에 추가), `organization` | ✅ |
| jobTitle, jobDescription | `title`, `jobDescription` | ✅ |
| requirements[] + sourceQuote, preferredQualifications[] | `requirements[]{kind=REQUIRED_SKILL/PREFERRED_SKILL, sourceQuote}` | ✅ 우대는 `kind=PREFERRED_SKILL`로 거름 |
| eligibilityRules[] | `eligibilityRules[]` (§3.2) | ✅ 판정은 공통 함수 |
| closesAt, officialUrl, checkedAt | 같은 이름 | ✅ |
| workLocations[] | `workRegion` (1개) | ⚠️ 근무지 여러 개는 MVP 미지원. 필요하면 `workRegions[]` 추가 (B) |
| 기업별 공고 목록 | B가 GSI byOrg를 빼고 S3 Vectors 필터로 대체 | 🔶 S3 Vectors 질의는 유사도 순이라 "기업 공고 전부"는 어려움. 필요해지면 GSI 추가 검토 |

### 3.2 지원 자격 조건 `eligibilityRules[]`와 판정

B가 스냅샷에 조건을 저장하고, **A·B 모두 `backend/eligibility.py`의 `evaluate_eligibility(profile, rules)`로만 판정**한다. 같은 공고에 두 파트가 다른 판정을 내지 않게 하려는 것.

| `type` | `value` 예 | 프로필 필드 | 결과 |
|---|---|---|---|
| `EDUCATION` | `"BACHELOR"` (`NONE`이면 무관) | `educationLevel` | 이상이면 MET |
| `CAREER` | `{"type": "NEW"}`, `{"type": "EXPERIENCED", "minYears": 3}` | `careerYears` | 신입·무관은 MET |
| `CERTIFICATE` | `"ADsP"` | 역량 프로필 `certificates[]`, 사용자 확인 `confirmedMissingCertificates[]` | 보유 MET, **없다고 확인했을 때만** NOT_MET, 나머지 UNKNOWN |
| `MAJOR` | `["통계", "컴퓨터공학"]` | `major` | 포함 MET |
| 그 밖 (지역인재 등) | — | — | UNKNOWN (직접 확인) |

전체 결과: NOT_MET 하나라도 → `INELIGIBLE`, 아니고 UNKNOWN이 있거나 조건이 아직 없으면 → `NEEDS_VERIFICATION`, 모두 MET → `ELIGIBLE`. 판정 결과는 저장하지 않고 요청 때 계산한다 (프로필이 바뀌면 결과도 바뀌므로). A는 분석 결과(`ANALYSIS#`)에 그때의 판정과 `ruleVersion`을 함께 저장한다.

## 4. `team07-reference`: NCS·자격 (A 사용)

| 엔티티 | PK | SK | GSI1PK / GSI1SK |
|---|---|---|---|
| NCS 직무 프로필 (11) | `NCS#{ncsCode}` | `PROFILE` | `JOBNAME#{직무명}` / `NCS#{ncsCode}` |
| 주간 공식 능력단위·요소 스냅샷 | `NCS#{ncsCode}` | `OFFICIAL#UNITS` | — |
| 능력단위 (135) | `NCS#{ncsCode}` | `UNIT#{unitCode}` | — |
| 자격 연계 (37) | `UNIT#{unitCode}` | `QUAL#{qualCode}#{unitType}` | `QUAL#{qualCode}` / `UNIT#{unitCode}` |
| 자격 정보 | `QUAL#{qualCode}` | `META` | — |
| 직업기초능력 (34) | `BASIC` | `SKILL#{id}` | — |
| 직무 코드 매핑 | `MAP#WORK24#{직종코드}` | `NCS#{ncsCode}` | `MAP#NCS#{ncsCode}` / `WORK24#{직종코드}` |

- 직무 코드 매핑은 B가 고용24 직무정보 API로 채운다. 고용24 직종 → NCS는 PK Query, NCS → 고용24는 GSI1. 한 직종에 NCS 후보가 여럿일 수 있다 (A 명세 §8.3 후보 반환).
- 자격 연계는 키가 `(능력단위, 자격, 구분)`이라 중복이 들어갈 수 없다 (A 명세 §2.2 중복 제거).

## 5. `team07-cache`

`cache_key` + TTL `expires_at`. A가 훈련과정·시험일정·직업정보 응답에 쓴다. API 키가 들어간 URL은 키로 쓰지 않는다.

자격시험 일정은 등록된 `QUAL#… / META`의 종목코드별로 `EXAM#{qualificationCode}#{year}`에 저장한다. `items`는 해당 종목·연도에 공식 발표된 일정이며 빈 목록은 조회 시점 기준 미발표를 뜻한다. 사용 시 `expires_at`을 확인한다.

## 멘토링 수집 운영

- 매일 06:00 KST에 한국산업인력공단 `getQualExamSchdList`에서 올해와 내년 시험 일정을 수집한다. 캐시 유효기간은 24시간이다.
- 매주 화요일 07:00 KST에 [NCS 공식 자료실](https://www.ncs.go.kr/th06/bbs_lib_list.do?libDstinCd=01&searchKeyword=DB)의 최신 대분류별 정보망 DB를 확인한다. 각 직무 스냅샷에 버전 포함 능력단위코드, 명칭, 요소명, 자료 기준월, 출처, SHA-256을 저장한다. 수집 실패 시 이전 자료를 유지한다.
- 개발계획서1 §9의 권장 주기를 따른다. 실행 시각은 오전 정책 배치와 분리한 운영 설정이다. 기존 팀 키로 NCS 기준정보 API가 403을 반환해 공단 공식 배포 파일을 사용한다.
- Lambda 코드 배포 후 서울 리전에서 `python3 infra/setup_mentoring_collection.py`를 실행한다. 두 일정은 기존 Scheduler 역할로 `team07-api`를 호출한다.

## 6. 공통 ID 규칙

| ID | 형식 | 만드는 곳 |
|---|---|---|
| `userId` | Cognito `sub` (사용자 풀 `team07-users`, 아이디·비밀번호 로그인) | 공통 인증 |
| `jobPostingId` | `wk24-{구인인증번호}`, `alio-{공시번호}`, `ext-{해시}`(P1). `ptn-`, `sch-` 예약 | B |
| `snapshotId` | `{수집일 YYYYMMDD}-{contentHash 8자}` | B |
| `policyId` | `ythc-{정책번호}`, `seed-{이름}`, `event-{번호}`(P1) | B |
| `companyId` | `biz-{사업자번호}`, 없으면 `name-{정규화 이름 해시}` | B |
| `notificationId` | `{yyyyMMddTHHmmss}-{해시 8자}` | B |
| `workspaceId` | `ws-{jobPostingId}`, `ws-ncs-{ncsCode}` | 공통 백엔드 |
| `sessionId`(= ivId) | UUID | 공통 백엔드 |
| 그 밖의 ID | `{접두사}-{uuid4 앞 12자}` (`doc-`, `analysis-`, `review-`, `path-`, `story-`, `task-`) | 생성하는 API |

ID 안에는 `#`를 쓰지 않는다. 키 구분자이고, 주소에 들어가면 요청이 깨진다. 서버는 `#`가 든 ID를 받으면 400.

## 7. S3·S3 Vectors

| 저장소 | 용도 | 경로·설정 |
|---|---|---|
| `team07-career-docs-<계정ID>` | 개인 문서 원본·추출본·첨삭 결과 | `users/{hashedUserId}/documents/{docId}/v{n}/…`, `users/{hashedUserId}/reviews/{reviewId}.json`. 업로드 완료 전 원본은 `pending/users/…`에 두고 완료 때 `users/…`로 옮긴다. `pending/`은 1일 자동 삭제 |
| `team07-kb-source-<계정ID>` | KB 원천 (13쌍) | `docs/` |
| `team07-uploads-<계정ID>` | 면접 녹음(변환 후 삭제), 질문 음성. 7일 자동 삭제 | `uploads/interview/{ivId}/{answers,transcripts,questions}/…` |
| `team07-opp-data-<계정ID>` | B: 공공 API 원본, 정규화본, 시드, 데모 스냅샷, 수집 기록 | `raw/{출처}/{날짜}/`, `normalized/{날짜}/`, `seed/`, `snapshots/demo-2026-11-21/`, `runs/{날짜}.json` |
| S3 Vectors `team07-opp-vectors` | B: 공고 임베딩 검색 | 인덱스 `postings-v1` (1024차원, 코사인). 키 `jobPostingId`. 필터 메타데이터 `isBusan`, `sido`, `jobMajor`, `active`, `deadline`(YYYYMMDD 숫자), 필터 불가 `title` |

## 8. 생성 현황과 정리

| 자원 | 상태 |
|---|---|
| `team07-career-mentor`, `team07-catalog`(Streams), `team07-reference`, `team07-cache` | ✅ 생성됨 (테이블은 이 4개가 전부) |
| 버킷 4개, S3 Vectors `team07-opp-vectors` / `postings-v1` | ✅ 생성됨 |
| `team07-reference` 데이터 | ⬜ A의 ZIP CSV 적재, B의 직무 코드 매핑 적재 |
| `team07-users`, `team07-chat`, `team07-jobs`, `team07-interviews` | 🗑 삭제함 (비어 있었음, `career-mentor`로 합침) |
