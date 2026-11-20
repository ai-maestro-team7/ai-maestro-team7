# Requirements Document

## Introduction

mentoring-profile-storybank는 A 파트(`docs/개발계획서1.md`)의 첫 후속 스펙이다. 사용자가 올린 이력서·경력 문서에서 텍스트를 뽑고, 원문 근거가 붙은 역량 프로필을 만들고, 경험을 Story Bank(경험 블록)로 정리하는 기능을 다룬다. A 코드가 처음 들어가는 `ai/mentoring/`의 패키지 구성과 입구도 이 스펙에서 정한다. 이후 스펙(mentoring-fit-review-learning, mentoring-agent-quality)은 이 스펙이 만든 역량 프로필과 경험 블록을 읽어서 시작한다.

근거와 전제:
- 문서 표기: A = `docs/개발계획서1.md`, 제안서 = `docs/프로젝트_제안서.md`, api = `docs/api.md`(v1.0), db = `docs/db-schema.md`(v1.3), 기반 = `.kiro/specs/common-foundation/`, 계약 = `contracts/src/team07_contracts/`, 패키지 = 지식 패키지 `team7-career-mentor-knowledge-package-2026-11-20.zip`.
- 결정 기록(기반 requirements.md "결정 기록", 기반 design.md 추가 항목)에서 CONFIRMED인 결정은 그대로 따른다: 인증 Cognito JWT(D-07), API 규약(D-01~D-05), DB 4테이블(D-13), 단일 Lambda `team07-api`와 파트 패키지(D-17), Lambda 비동기 자기 호출(D-19), Python 3.13(D-15), 데모 직무 데이터 분석(D-37).
- PROPOSED·OPEN 결정에 걸리는 기준은 해당 결정 ID를 붙이고, 결정이 바뀌면 그 기준만 고친다. 이 스펙에서 새로 생긴 미결정은 마지막 "이 스펙의 미결정" 표에 둔다.
- A §7.1의 테이블 키(`DOC#documentId`, `STORY#storyId#LATEST`, `IDEMPOTENCY#`)는 db v1.3이 대체했다. 이 스펙은 db v1.3 키를 따른다.
- A §10의 SQS + DLQ는 SQS 권한이 없어 Lambda 비동기 자기 호출로 대체한다 (D-19). 작업 함수의 입력·출력은 SQS로 바꿔도 같게 둔다.
- 이 스펙에 필요한 AWS 권한은 지금 실행 역할(`infra/iam/lambda-role-policy.json`)에 있다: `team07-*` 테이블 읽기·쓰기, `team07-career-docs-<계정ID>` 객체 읽기·쓰기, Textract 텍스트 탐지, Bedrock 모델 호출, Lambda 자기 호출. 없는 권한은 EventBridge와 CloudWatch 지표 전송이고, 이 스펙은 둘을 쓰지 않는다 (Requirement 12, 미결정 M-4).

범위에서 제외 (다른 스펙이 담당):
- 직무 적합도·지원자격(F-02), 첨삭(F-03), 역량 격차(F-04), 학습 경로(F-05): mentoring-fit-review-learning
- 통합 Agent와 Action Group(F-06), 품질 평가셋 실행(F-07), 운영 알람(F-08): mentoring-agent-quality. 단, 이 스펙의 함수는 나중에 Agent 도구가 같은 함수를 부를 수 있게 만든다 (Requirement 1)
- Bedrock Knowledge Base 생성·동기화 (S3 Vectors 권한 대기, team-guide §3)
- 워크스페이스 생성·지원 상태 (BACKEND, D-36), 기본 프로필 `PROFILE#BASIC` (BACKEND, D-08)
- AWS 자원 생성, 권한 변경, 배포 (AGENTS.md "환경·보안": 사용자에게 먼저 확인)

## Glossary

- **Mentoring_Package**: `ai/mentoring/` 아래 A 코드 전체. 백엔드 Lambda `team07-api`에 패키지로 묶여 배포된다 (D-17)
- **Mentoring_API**: `/api/v1/mentoring/*` REST 요청을 처리하는 A의 입구
- **Task_Runner**: 오래 걸리는 처리(텍스트 추출, 역량 추출, 경험 질문 생성)를 Lambda 비동기 자기 호출로 실행하는 A의 입구 (D-19)
- **User_Id**: 백엔드가 `backend/common.py`의 `get_user_id()`로 읽어 A 입구에 넘기는 사용자 ID (Cognito `sub`, api §3)
- **Document**: 사용자가 올리거나 직접 입력한 이력서·자기소개서·경력기술서·포트폴리오. `documentType`은 `RESUME`, `COVER_LETTER`, `CAREER_HISTORY`, `PORTFOLIO` 중 하나 (A F-01)
- **Document_Version**: Document의 한 버전. db §2.1의 `DOC#{docId}#V#{n}` 항목과 최신 포인터 `DOC_LATEST#{docId}`
- **Extraction_Status**: Document_Version의 처리 단계. `UPLOADED`, `EXTRACTING`, `EXTRACTED`, `ANALYZING`, `REQUIRES_USER_REVIEW`, `COMPLETED`, `FAILED` (A F-01 "상태 전이")
- **Normalized_Text**: 추출한 원문을 정규화한 텍스트. Evidence의 `startChar`·`endChar`는 이 텍스트 기준 인덱스다 (A §4.3)
- **Career_Profile**: 원문 근거가 붙은 역량 프로필 (A §4.3). 버전마다 `PROFILE#{profileId}#V#{n}`, 최신 포인터 `PROFILE#LATEST` (db §2.1)
- **Evidence**: 역량의 근거가 되는 원문 인용. `evidenceId`, `sourceDocumentId`, `page`, `startChar`, `endChar`, `quotedText` (A §4.3)
- **Evidence_Level**: `EVIDENCED`, `PARTIAL`, `SELF_REPORTED`, `NOT_FOUND`, `USER_CONFIRMED_GAP` (A §4.2)
- **Fact_Status**: `VERIFIED`, `NEEDS_CONFIRMATION`, `SUGGESTION` (A §4.2, 패키지 `agent/CAREER_MENTOR_AGENT_PROMPT.md` "정보 상태")
- **Story_Item**: Situation·Task·Action·Result·Learning으로 정리한 경험 블록 (A F-01B). 버전마다 `STORY#{storyId}#V#{n}`, 최신 포인터 `STORY_LATEST#{storyId}` (db §2.1)
- **LLM_Port**: Bedrock 모델 호출을 감싼 인터페이스. 운영에서는 Bedrock, 테스트에서는 MockLLM을 쓴다 (A §10.3)
- **MockLLM**: 정해진 JSON fixture를 돌려주는 LLM_Port 구현 (A §10.3)
- **Reference_Loader**: 패키지 `structured/` CSV를 `team07-reference` 테이블(db §4)에 넣는 도구
- **Reference_Lookup**: NCS 직무·능력단위·자격 연계를 조회하는 인터페이스. 테이블이 없거나 연결되지 않으면 CSV에서 읽는다 (A §10.3)
- **Career_Profile_Summary**: A가 만들어 C의 `start_interview(profile=…)`에 넘기는 역량 요약 계약 (`contracts` `career_summary.py`, D-12)
- **Error_Envelope**: 공통 오류 응답 `{"error": {code, message, requestId, retryable, details?}}` (api §5, D-03)

## Requirements

### Requirement 1: A 패키지 구성과 입구

**User Story:** As a 공통 백엔드 담당, I want A 코드가 다른 파트와 같은 방식으로 패키징되고 정해진 입구로만 불리기를, so that `team07-api` 하나에 A 기능을 붙이고 A 담당과 따로 배포 구조를 맞출 필요가 없다.

출처: D-17, 기반 design.md "Integration_Seam_Doc" A 행·"파트 폴더 규칙", 기반 Requirement 12, B §1.1·§5.9 (REST와 Agent가 같은 함수), A §0-6

#### Acceptance Criteria

1. THE Mentoring_Package SHALL Python 패키지 이름을 하이픈 없는 `mentoring` 하나로 두고, 의존성은 `ai/mentoring/requirements.txt` 하나에, 테스트는 `ai/mentoring/tests/` 아래에 둔다 (D-17, 기반 "파트 폴더 규칙").
2. THE Mentoring_Package SHALL 백엔드가 부르는 입구를 두 개만 공개한다: REST 요청을 받는 Mentoring_API와 비동기 작업을 받는 Task_Runner. 두 입구는 요청 변환, User_Id 전달, 응답·오류 변환만 하고 비즈니스 규칙을 직접 구현하지 않는다 (기반 Requirement 12 기준 6).
3. THE Mentoring_Package SHALL 입구 뒤의 비즈니스 함수가 User_Id를 첫 인자로 받고 HTTP 이벤트 형식에 의존하지 않게 한다. 이후 mentoring-agent-quality의 Agent 도구가 같은 함수를 부를 수 있어야 한다 (A §0-6, F-06 "Agent 장애 시 각 기능의 고정 REST API는 독립 동작").
4. THE Mentoring_Package SHALL `backend/`의 어떤 모듈도 import하지 않는다. 공통 계약과 오류 코드는 `team07_contracts`에서 가져온다 (기반 Requirement 12, D-18).
5. THE Mentoring_Package SHALL 테이블 이름, 버킷 이름, 모델 ID, 업로드 한도, 텍스트 길이 한도를 환경변수나 설정 파일에서만 읽는다. 필수 값이 없으면 그 이름을 담은 오류로 멈추고, 코드 안의 기본 자원 이름이나 모델 ID로 대체하지 않는다. A의 환경변수 이름과 설정 파일 위치는 기반 design.md §7 Resource_Naming_Convention의 Part별 설정 표(R13.2)에 "미정"으로 남아 있어 이 스펙의 design에서 채운다 (AGENTS.md "코딩 규칙").
6. THE Mentoring_Package SHALL A 오류를 `code`, `message`, `retryable`, 선택 `details`를 가진 예외 하나로 던진다. 입구는 이 예외를 Error_Envelope로 바꾸고, A 별칭 코드(`VALIDATION_ERROR`, `MODEL_UNAVAILABLE`, `SOURCE_UNAVAILABLE`)는 대표 코드(`INVALID_INPUT`, `AWS_SERVICE_ERROR`)로 바꿔 응답한다. 사용자에게 보이는 `message`는 한국어다 (api §5, D-04, 계약 `errors.py`).
7. THE Mentoring_Package SHALL BACKEND 소유 파일(`backend/`, `infra/`, `docs/db-schema.md`)을 이 스펙에서 고치지 않는다. 필요한 변경은 "백엔드(BACKEND) 담당 작업" BE-1~BE-7로 백엔드 담당에게 요청하고 기반 Contract_Change_Procedure를 따른다. 그 전까지 `/api/v1/mentoring/*`는 지금처럼 501 `NOT_IMPLEMENTED`로 남고, A 코드는 Requirement 11의 로컬 테스트로 확인한다 (api §1, 기반 Requirement 2).

### Requirement 2: 사용자 식별과 데이터 격리

**User Story:** As a 사용자, I want 내 이력서와 분석 결과를 다른 사람이 볼 수 없기를, so that 개인 문서를 안심하고 올릴 수 있다.

출처: api §3·§5, db §0 원칙 2·4, A §1.1 "사용자 A가 사용자 B 자료를 조회할 수 없고", F-08 "보안 필수", UT-15

#### Acceptance Criteria

1. THE Mentoring_API SHALL User_Id를 백엔드가 넘긴 값에서만 얻고, 요청 본문·쿼리·헤더에 있는 `userId`나 `ownerUserId`는 무시한다 (api §3).
2. THE Mentoring_Package SHALL 사용자 데이터를 모두 `team07-career-mentor`의 `PK = USER#{User_Id}` 아래에 저장하고, 각 항목에 `ownerUserId`를 함께 둔다 (db §0 원칙 2).
3. WHEN 요청한 `documentId`, `profileId`, `storyId`가 없거나 다른 사용자의 것이면, THE Mentoring_API SHALL 존재 여부를 드러내지 않도록 같은 404 응답을 돌려준다. 코드는 문서면 `DOCUMENT_NOT_FOUND`, 그 밖은 `NOT_FOUND`다 (api §5 "남의 리소스는 404", 계약 `errors.py`).
4. THE Mentoring_Package SHALL S3 객체 키를 서버에서만 만들고 `users/{hashedUserId}/` 아래에 둔다. 요청으로 받은 S3 키는 쓰지 않는다 (A F-08 "서버가 생성한 key만 사용", db §7).
5. THE Mentoring_Package SHALL Scan을 쓰지 않고 GetItem·Query로만 사용자 데이터를 읽는다 (db §0 원칙 9).
6. FOR ALL 이 스펙의 REST 경로, 사용자 A의 리소스 ID로 사용자 B가 요청하면 응답 본문에 사용자 A의 원문, 인용, 파일 이름이 들어 있지 않아야 한다 (A UT-15).

### Requirement 3: 문서 업로드 URL 발급

**User Story:** As a 사용자, I want 이력서 PDF를 화면에서 바로 올리기를, so that 파일 크기 때문에 API가 막히지 않는다.

출처: A F-01 처리 1~2단계·§6.1·§6.2, api §2 (`Idempotency-Key`), AGENTS.md "노션 허브 자료" (Lambda 요청 6MB 한도, presigned URL 업로드), db §2.1·§7

#### Acceptance Criteria

1. WHEN 사용자가 `POST /api/v1/mentoring/documents/upload-url`에 `fileName`, `contentType`, `sizeBytes`, `documentType`, 선택 `workspaceId`를 보내면, THE Mentoring_API SHALL 값을 검사한 뒤 Document와 첫 Document_Version을 만들고 201로 `documentId`, `uploadUrl`, `expiresInSeconds`, `status`를 돌려준다 (A §6.2).
2. THE Mentoring_API SHALL 허용 형식(PDF)과 크기 한도를 설정 값으로 검사한다. 크기 한도를 넘으면 413 `FILE_TOO_LARGE`, 형식이나 `documentType`이 허용 값이 아니면 400 `INVALID_INPUT`을 돌려준다. A F-01의 10MB·20페이지는 설정 기본값의 예시이고 코드에 숫자로 넣지 않는다 (A F-01 "입력").
3. THE Mentoring_API SHALL 업로드 URL을 짧은 유효 시간의 S3 PUT presigned URL로 발급하고, 요청한 `contentType`과 크기 조건을 URL 서명에 넣는다 (A F-01 처리 2단계).
4. THE Mentoring_Package SHALL `DOC_LATEST#{docId}`와 `DOC#{docId}#V#0001`을 한 트랜잭션으로 쓰고, 첫 Extraction_Status를 `UPLOADED` 전 단계인 대기 상태로 표시한다. 대기 상태의 이름은 design에서 Extraction_Status 목록과 함께 정한다 (db §0 원칙 6, A F-01 처리 2단계 "PENDING 저장").
5. WHEN 같은 사용자가 같은 `Idempotency-Key`와 같은 본문으로 다시 요청하면, THE Mentoring_API SHALL 새 Document를 만들지 않고 처음 결과의 `documentId`를 돌려준다. 같은 키에 다른 본문이 오면 409 `PRECONDITION_NOT_MET`을 돌려준다 (api §2, A F-01 "중복 요청", D-31).
6. THE Mentoring_Package SHALL presigned URL을 로그, 오류 `details`, DynamoDB 항목에 남기지 않는다 (A §6.2, tech.md "보안·개인정보").

### Requirement 4: 업로드 완료와 텍스트 직접 입력

**User Story:** As a 사용자, I want 파일을 올린 뒤나 텍스트를 붙여넣은 뒤 바로 분석이 시작되기를, so that 화면에서 진행 상태만 기다리면 된다.

출처: A F-01 처리 3~4단계·§6.1·§10.1·§10.2, api §4, D-05, D-19, 계약 `async_status.py` (A 확장 `REQUIRES_USER_REVIEW`, `PARTIAL_SUCCESS`)

#### Acceptance Criteria

1. WHEN 사용자가 `POST /api/v1/mentoring/documents/{documentId}/complete`를 보내면, THE Mentoring_API SHALL S3 HeadObject로 객체 존재, 크기, 형식이 발급 때 값과 맞는지 확인한 뒤 Extraction_Status를 `UPLOADED`로 바꾸고 202로 `documentId`, `taskId`, `status`를 돌려준다 (A F-01 처리 3단계, §6.1).
2. IF 객체가 없거나 크기·형식이 발급 때 값과 다르면, THEN THE Mentoring_API SHALL 400 `INVALID_INPUT`을 돌려주고 작업을 만들지 않는다 (A §6.2 "ETag만 신뢰하지 말고").
3. WHEN 이미 완료 처리된 Document_Version에 complete가 다시 오면, THE Mentoring_API SHALL 새 작업을 만들지 않고 처음 결과를 돌려준다 (A F-01 처리 3단계 "중복 complete는 멱등").
4. WHEN 사용자가 `POST /api/v1/mentoring/documents/text`로 `text`와 `documentType`을 보내면, THE Mentoring_API SHALL 텍스트 길이를 설정 한도(A F-01 예시 1,000~30,000자)로 검사하고, 텍스트를 S3에 저장한 뒤 `EXTRACTING` 단계를 건너뛰어 `EXTRACTED`로 두고 202를 돌려준다. 한도를 벗어나면 400 `INVALID_INPUT`이다 (A F-01 "상태 전이": 텍스트 직접 입력은 EXTRACTING 생략).
5. THE Mentoring_Package SHALL 작업마다 `TASK#{taskId}` 항목을 만들고 상태를 공통 4개(`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`)와 A 확장(`REQUIRES_USER_REVIEW`, `PARTIAL_SUCCESS`)으로만 둔다. 상태 전이는 `status = :expected` 조건부 쓰기로만 한다 (db §2.5, api §4, D-05).
6. THE Task_Runner SHALL 작업 메시지에 리소스 ID와 버전만 담고, 이력서·자기소개서 원문, 추출 텍스트, 키를 담지 않는다. 작업을 처리할 때 User_Id로 소유권을 다시 확인한다 (A §10.1).
7. WHEN 같은 작업이 두 번 실행되면, THE Task_Runner SHALL 결과를 한 번만 저장한다 (A §10.2 "at-least-once", UT-17).
8. WHEN 사용자가 `GET /api/v1/mentoring/documents/{documentId}`를 보내면, THE Mentoring_API SHALL 최신 Document_Version의 `documentType`, `version`, Extraction_Status, 페이지 수, 추출 텍스트 길이, 실패 시 오류 코드를 돌려준다. 원문 파일 URL과 추출 텍스트 본문은 이 응답에 넣지 않는다 (A §6.1 "문서 추출 상태/텍스트 메타"). 추출 텍스트를 사용자에게 보여주는 방법은 "이 스펙의 미결정" M-2에서 정한다.

### Requirement 5: 텍스트 추출

**User Story:** As a 사용자, I want 디지털 PDF와 스캔 PDF 모두에서 이력서 내용을 읽어 주기를, so that 문서 형태 때문에 분석을 못 받는 일이 없다.

출처: A F-01 처리 5~6단계·"필수 입력 누락/에러", §3.1 "Textract 한국어", §10.2 Textract, UT-20, tech.md "착수 전 확인" (Textract 한국어)

#### Acceptance Criteria

1. WHEN Task_Runner가 업로드된 PDF의 추출 작업을 받으면, THE Task_Runner SHALL 먼저 PDF 텍스트 레이어를 추출하고, 텍스트가 부족하거나 깨졌다고 판정될 때만 Textract로 OCR을 한다 (A F-01 처리 5단계, §3.1).
2. THE Task_Runner SHALL 텍스트 품질을 공백·문자 비율, 페이지별 길이, 인코딩 오류 비율로 판정하고, 판정 기준값은 설정 파일에서 읽는다 (A F-01 처리 6단계).
3. WHERE 문서가 여러 페이지이거나 스캔 PDF이면, THE Task_Runner SHALL Textract 비동기 탐지(Start → Get)와 `NextToken`으로 모든 페이지를 읽는다 (A §10.2).
4. THE Task_Runner SHALL 추출 결과를 Normalized_Text로 만들어 개인 문서 버킷의 해당 Document_Version 경로에 저장하고, DynamoDB에는 `extractedTextKey`, 페이지 수, 페이지별 시작 위치만 저장한다 (db §0 원칙 7, §2.1).
5. IF PDF가 손상됐거나 암호화돼 읽을 수 없으면, THEN THE Task_Runner SHALL Extraction_Status를 `FAILED`, 오류 코드를 `DOCUMENT_UNREADABLE`(422)로 두고 작업 상태를 `FAILED`, `retryable=false`로 둔다 (A F-01 "필수 입력 누락/에러").
6. IF 추출한 텍스트가 설정 최소량보다 적으면, THEN THE Task_Runner SHALL Extraction_Status와 작업 상태를 `REQUIRES_USER_REVIEW`로 두고, 사용자가 텍스트를 직접 입력하도록 안내하는 사유 코드를 남긴다 (A F-01 "텍스트 추출량 부족").
7. IF Textract가 시간 안에 끝나지 않거나 일시 오류를 내면, THEN THE Task_Runner SHALL 작업을 `FAILED`, `retryable=true`, 오류 코드 `AWS_SERVICE_ERROR`로 두고 직접 입력 경로를 안내한다 (A F-01 "Textract 타임아웃").
8. THE Mentoring_Package SHALL 텍스트 레이어 PDF와 스캔 PDF 각각에 대한 테스트를 외부 서비스 없이 실행되는 가짜 Textract로 갖는다 (A UT-20).

### Requirement 6: 원문 근거가 붙은 역량 추출

**User Story:** As a 사용자, I want 내 이력서에서 뽑은 역량마다 어느 문장이 근거인지 보이기를, so that AI가 지어낸 역량이 아닌지 확인할 수 있다.

출처: A F-01 처리 7~10단계, §4.2·§4.3 "증거 인용 검증 규칙", F-07 계층별 검증 1~3·7, §1.1, UT-01·UT-02·UT-04, tech.md "LLM·데이터 처리 규칙", 패키지 `agent/prompts/01_STORY_BANK_COMPETENCY.md`·`methodology/`

#### Acceptance Criteria

1. WHEN 텍스트 추출이 끝나면, THE Task_Runner SHALL Extraction_Status를 `ANALYZING`으로 바꾸고 LLM_Port에 역량 추출을 요청한다 (A F-01 처리 8단계).
2. THE Task_Runner SHALL 모델 입력 전에 이름, 연락처, 주민등록번호, 주소 형태의 문자열을 가리고, 원문은 개인 문서 버킷에만 둔다 (A F-01 처리 7단계).
3. THE Task_Runner SHALL 이력서 텍스트를 태그로 감싸 데이터로만 넘기고, 텍스트 안의 지시문을 실행하지 않는다 (tech.md "외부 텍스트는 태그로 감싸", 제품 원칙 8).
4. THE Task_Runner SHALL 모델 출력을 고정 JSON 스키마로 받고 Pydantic으로 검사한다. 검사에 실패하면 한 번 다시 요청하고, 다시 실패하면 작업을 `FAILED`, 오류 코드 `AI_OUTPUT_INVALID`, `retryable=true`로 둔다. 실패를 조용히 통과시키지 않는다 (tech.md "LLM 출력은 고정 JSON 스키마", F-07 7).
5. FOR ALL 저장되는 Evidence, `quotedText`는 해당 Normalized_Text에 그대로 들어 있어야 하고 `startChar`·`endChar`로 자른 문자열과 같아야 한다. `quotedText`가 원문에 없으면 그 Evidence를 저장하지 않는다. 문자열은 있지만 위치가 다르면 위치를 원문에서 다시 찾아 맞추고, 못 찾으면 위치를 버리고 연결된 역량을 `NEEDS_CONFIRMATION`으로 둔다 (A §4.3 "증거 인용 검증 규칙", F-07 품질 게이트 "Evidence quote 정합성 100%").
6. IF 모델 출력에 원문에 없는 경력, 회사·프로젝트 이름, 기간, 수치, 자격이 들어 있으면, THEN THE Task_Runner SHALL 수정 요청을 한 번 보내고, 그래도 남으면 그 항목을 저장하지 않고 작업 상태를 `REQUIRES_USER_REVIEW`, 사유 코드를 `EVIDENCE_MISMATCH`로 둔다 (A F-01 처리 10단계, UT-04).
7. THE Task_Runner SHALL 서류에 없는 역량을 `NOT_FOUND`로만 표시하고 "부족"으로 확정하지 않는다. 경력·성과가 없는 이력서는 빈 목록으로 저장하고 가상 경험을 만들지 않는다 (A §4.2 "NOT_FOUND ≠ 실력 없음", F-01 "경력·성과 없는 이력서", UT-02).
8. THE Task_Runner SHALL 모델이 고른 Fact_Status 중 `VERIFIED`를 그대로 저장하지 않는다. 사용자가 확인하기 전의 역량은 `NEEDS_CONFIRMATION` 또는 `SUGGESTION`이고, `VERIFIED`는 Requirement 7의 사용자 확인으로만 생긴다 (A §4.2 "VERIFIED(사용자가 증빙 내용을 확인)", F-01 처리 11단계).
9. THE Task_Runner SHALL 결과에 `modelId`, `promptVersion`, `schemaVersion`을 남기고, 모델 ID는 환경변수에서 읽는다 (tech.md "결과에는 modelId, promptVersion", AGENTS.md "노션 허브 자료").
10. WHERE 역량을 NCS 능력단위와 연결하면, THE Task_Runner SHALL Reference_Lookup에 있는 능력단위 코드만 `ncsUnitCode`에 넣고, 없는 코드는 넣지 않는다 (A §2.1 "정형 계산용", tech.md "NCS 코드는 정형 데이터로 정확히 조회").

### Requirement 7: 역량 프로필 저장, 조회, 사용자 확인

**User Story:** As a 사용자, I want AI가 뽑은 역량을 내가 고치고 확정하기를, so that 이후 적합도와 첨삭이 내가 인정한 사실만 쓴다.

출처: A F-01 처리 11~12단계·"완료 기준", §4.1·§4.3, §6.1 (`GET /profiles/me`, `POST /profiles/{profileId}/confirm`), db §0 원칙 5·6, §2.1, api §6.5

#### Acceptance Criteria

1. WHEN 역량 추출 검증이 끝나면, THE Task_Runner SHALL Career_Profile 새 버전 `PROFILE#{profileId}#V#{n}`과 `PROFILE#LATEST`를 한 트랜잭션으로 쓰고, `latestVersion = :expected` 조건이 맞지 않으면 쓰지 않는다 (db §0 원칙 5·6).
2. THE Mentoring_Package SHALL Career_Profile 버전을 수정하거나 지우지 않고 새 버전으로만 쌓는다. 각 버전에는 `sourceDocumentIds`, `skills`, `evidence`, `projects`, `experiences`, `certificates`, `needsConfirmation`, `modelId`, `promptVersion`, `schemaVersion`을 둔다 (A §4.3, db §2.1).
3. WHEN 사용자가 `GET /api/v1/mentoring/profiles/me`를 보내면, THE Mentoring_API SHALL `PROFILE#LATEST`가 가리키는 최신 Career_Profile 버전을 돌려준다. 프로필이 없으면 404 `NOT_FOUND`다. 이 경로는 역량 프로필이고 기본 프로필(`/api/v1/me/profile`)과 다르다 (api §1·§6.5).
4. WHEN 사용자가 `POST /api/v1/mentoring/profiles/{profileId}/confirm`으로 역량별 확인·수정·삭제를 보내면, THE Mentoring_API SHALL 이전 버전을 그대로 두고 다음 번호의 새 버전을 만들어 201로 돌려준다. 사용자가 확인한 역량만 `VERIFIED`가 된다 (A F-01 처리 11단계 "Verified revision v2 생성(기존 v1 보존)").
5. IF confirm 요청의 기준 버전이 최신 버전이 아니면, THEN THE Mentoring_API SHALL 409 `PRECONDITION_NOT_MET`을 돌려주고 새 버전을 만들지 않는다 (db §0 원칙 6).
6. WHEN 사용자가 확인 과정에서 근거가 없는 역량을 새로 적으면, THE Mentoring_API SHALL 그 역량을 Evidence 없이 `SELF_REPORTED`로 저장하고 원문 인용을 만들지 않는다 (A §4.2 `SELF_REPORTED`).
7. WHEN 사용자가 어떤 역량을 가지고 있지 않다고 확인하면, THE Mentoring_API SHALL 그 역량을 `USER_CONFIRMED_GAP`으로 저장한다 (A §4.2, UT-03).

### Requirement 8: 면접용 역량 요약 변환

**User Story:** As a 모의면접 담당(C), I want A의 역량 프로필을 정해진 요약 형식으로 받기를, so that 이력서 원문 없이도 질문 소재를 얻는다.

출처: 계약 `career_summary.py`, D-12, D-40(PROPOSED), 기반 design.md "Career_Profile_Summary (`career_summary.py`, R9, D-12·D-40)" 절의 원천 대응표, A §12.2 (`allowRawResume: false`, "AI가 생성한 잘못된 평가를 CareerProfile의 확인된 보유 역량으로 자동 반영하지 않음")

#### Acceptance Criteria

1. THE Mentoring_Package SHALL Career_Profile 버전 하나를 받아 `team07_contracts`의 `CareerProfileSummary`를 돌려주는 변환 함수를 공개한다. 백엔드(`backend/interview_api.py`)가 면접 시작 때 이 함수를 부를 수 있어야 한다. 백엔드 쪽 연결은 BE-5다 (기반 design.md "변환 함수는 A 소유").
2. THE Mentoring_Package SHALL 요약의 `skills`에 Fact_Status가 `VERIFIED`인 역량의 이름만 넣고, `needsConfirmation`에는 확인이 필요한 역량을 넣는다. `needsConfirmation`의 항목은 부족이 확정된 역량이 아니다 (기반 design.md 원천 대응표, A §4.2).
3. THE Mentoring_Package SHALL 요약에 이력서 원문, Evidence 인용문, 연락처를 넣지 않는다 (A §12.2 `allowRawResume: false`).
4. THE Mentoring_Package SHALL 목록 개수와 항목 길이를 `CAREER_SUMMARY_LIMITS`(D-40 PROPOSED: `projects` 10개·200자, `skills` 30개·50자, `needsConfirmation` 10개·200자)로 맞추고, 결과가 계약 검사를 통과하지 못하면 요약을 돌려주지 않는다. 한도를 넘는 항목을 고르는 규칙은 "이 스펙의 미결정" M-5에서 정한다.
5. THE Mentoring_Package SHALL C의 면접 평가 결과를 Career_Profile에 반영하는 함수를 두지 않는다 (A §12.2, 계약 `career_summary.py` "C의 면접 결과를 A로 되돌리는 필드·함수도 없다").

### Requirement 9: 경험 블록 초안과 확인 질문

**User Story:** As a 경험을 정리하지 못한 사용자, I want 짧게 적은 경험을 AI가 질문으로 구체화해 주기를, so that 자기소개서에 쓸 수 있는 경험 블록이 생긴다.

출처: A F-01B, §6.1 (`POST /stories`, `GET /stories`, `PATCH /stories/{storyId}`), 제안서 4.1 "경험 발굴 AI 코칭"·4.10 "경험 라이브러리", 패키지 `agent/prompts/01_STORY_BANK_COMPETENCY.md`·`methodology/02_Story_Bank_STAR_가이드.md`, db §2.1

#### Acceptance Criteria

1. WHEN 사용자가 `POST /api/v1/mentoring/stories`로 `rawExperience`와 선택 `targetRole`, `sourceDocumentId`, `existingStoryId`를 보내면, THE Mentoring_API SHALL 사용자 원문을 첫 Story_Item 버전에 `DRAFT` 상태로 저장하고 202로 `storyId`, `status`를 돌려준다 (A F-01B 처리 1단계, §6.1).
2. THE Task_Runner SHALL 원문에서 Situation·Task·Action·Result·Learning에 해당하는 사실을 나누고, 빠진 항목에 대한 확인 질문을 최대 3개 만들어 같은 Story_Item의 새 버전에 저장한다 (A F-01B 처리 2~3단계, 패키지 `01_STORY_BANK_COMPETENCY.md` 절차 1~4).
3. THE Task_Runner SHALL 원문에 없는 Task, Action, Result, 성과 수치, KPI를 만들지 않는다. `DRAFT` 상태의 내용으로 완성된 STAR 성과를 만들지 않는다 (A F-01B "DRAFT 상태의 내용으로 완성된 STAR 성과나 KPI 생성 금지").
4. THE Task_Runner SHALL 경험의 주체가 사용자 본인인지, 팀 성과와 개인 기여가 구분되는지 확인하고, 수치의 측정 기준이나 기간이 분명하지 않으면 그 필드를 `NEEDS_CONFIRMATION`으로 둔다 (A F-01B 처리 2단계, 패키지 `01` 제약).
5. WHEN 사용자가 `PATCH /api/v1/mentoring/stories/{storyId}`로 질문 답변이나 필드 확인을 보내면, THE Mentoring_API SHALL 이전 버전을 두고 새 버전을 만들며, 사용자가 확인한 필드 이름만 `confirmedFields`에 넣는다 (A F-01B 처리 4~5단계).
6. THE Mentoring_Package SHALL 역량 후보마다 근거가 된 사용자 행동 문장을 연결하고, 근거가 있는 수만큼만 역량 후보를 둔다 (패키지 `01` 출력·제약 "반드시 역량을 3개 만들 필요는 없다").
7. WHEN 사용자가 `GET /api/v1/mentoring/stories`를 보내면, THE Mentoring_API SHALL 그 사용자의 `STORY_LATEST#` 항목만 Query로 읽어 최신 버전 목록을 돌려준다 (db §2.8 "내 문서 / 경험 블록 목록").
8. THE Mentoring_Package SHALL 다른 사용자의 경험 블록을 질문 생성, 예시, 역량 후보에 쓰지 않는다 (A F-01B 처리 4단계).
9. THE Mentoring_Package SHALL 이후 첨삭 기능이 쓸 수 있도록 Story_Item 조회 함수가 `storyId`, 최신 버전, `confirmedFields`, 확인된 필드 값만 돌려주게 한다 (A F-01B 처리 6단계 "직무/자소서 문항과 연결할 경험 ID만 반환하여 F-03에서 재사용").

### Requirement 10: NCS 기준 데이터 적재와 조회

**User Story:** As a A 개발자, I want 패키지의 NCS 직무·능력단위·자격 연계를 정확한 키로 조회하기를, so that 역량을 직무에 연결할 때 모델이 코드를 지어내지 않는다.

출처: A §0-3·§2·§2.1·§2.2·§10.3, db §4, AGENTS.md "노션 허브 자료" (`selected_qualification_links.csv`의 중복 행 12개), 패키지 `structured/`·`LICENSE_AND_LIMITATIONS.md`

#### Acceptance Criteria

1. THE Reference_Loader SHALL 패키지 `structured/`의 UTF-8 정규화 CSV(`selected_job_profiles`, `selected_competency_units`, `selected_qualification_links`, `selected_ncs_classification`, `ncs_basic_skills`)만 읽고, CP949가 섞인 `raw/` 파일은 읽지 않는다 (A §2.2).
2. THE Reference_Loader SHALL db §4의 키 구조(`NCS#{ncsCode}` / `PROFILE`·`UNIT#{unitCode}`, `UNIT#{unitCode}` / `QUAL#{qualCode}#{unitType}` 등)로 항목을 만든다.
3. THE Reference_Loader SHALL 자격 연계를 `(competency_unit_code, qualification_code, unit_type)`로 중복 제거하고, 훈련시간이 다른 중복 레코드의 값을 더하지 않는다 (A §2.2).
4. WHEN Reference_Loader를 같은 입력으로 두 번 실행하면, THE Reference_Loader SHALL 두 번째 실행 뒤에도 항목 수와 값이 같게 둔다 (멱등).
5. THE Reference_Loader SHALL 실제 테이블에 쓰기 전에 항목 수를 미리 보여 주는 모드를 갖고, 실제 쓰기는 실행하는 사람이 명시적으로 선택할 때만 한다. 실제 쓰기는 AWS 자원 데이터 변경이므로 사용자 확인 뒤에 실행한다 (AGENTS.md "AWS 자원을 만들거나 바꾸는 작업은 사용자에게 먼저 확인").
6. THE Reference_Lookup SHALL NCS 코드, 직무명, 능력단위 코드로 정확히 조회하고, 의미 검색을 하지 않는다 (tech.md "NCS 코드·자격 연계·점수 규칙은 정형 데이터로 정확히 조회").
7. WHERE `team07-reference` 테이블을 쓸 수 없거나 비어 있으면, THE Reference_Lookup SHALL 같은 CSV에서 읽는 로컬 구현으로 같은 결과를 돌려준다 (A §10.3 "KB 미연결: CSV 기반 로컬 검색").
8. THE Reference_Lookup SHALL NCS–자격 연계의 `필수/선택`을 채용공고의 필수·우대 조건으로 표현하지 않고, `training_hours`를 개인의 자격 취득 기간으로 표현하지 않는다 (A §2.2).

### Requirement 11: 외부 서비스 없는 개발과 테스트

**User Story:** As a A 개발자, I want AWS 권한이나 Bedrock 없이도 A 기능 전체를 로컬에서 돌려 보기를, so that 권한을 기다리지 않고 해커톤 첫날 수직 슬라이스를 만든다.

출처: A §10.3·§13·§14 Day 1, 기반 Requirement 1 기준 5·9 (Local_Check: 자격 증명 없음, 외부 네트워크 차단), structure.md "코딩 규칙" (mock·fixture), 계약 `contracts/fixtures/`

#### Acceptance Criteria

1. THE Mentoring_Package SHALL DynamoDB, S3, Textract, Bedrock을 각각 인터페이스 뒤에 두고, 테스트용 메모리 구현과 MockLLM을 함께 둔다 (A §10.3).
2. WHEN Local_Check가 A 테스트를 실행하면, THE Mentoring_Package SHALL AWS 자격 증명과 외부 네트워크 없이 모든 테스트를 통과한다 (기반 Requirement 1 기준 5·9).
3. THE Mentoring_Package SHALL 테스트 데이터를 모두 가상 데이터로 만들고, 실제 개인 이력서·연락처·실명을 넣지 않는다. 공고·프로필이 필요하면 `contracts/fixtures/valid/`를 쓴다 (기반 Requirement 11, A "보안: 모든 예시에는 실제 개인정보 미포함").
4. THE Mentoring_Package SHALL 다음 A §13 시나리오를 자동 테스트로 갖는다: UT-01(근거 있는 역량), UT-02(미기재 역량 `NOT_FOUND`), UT-03(사용자 확인 격차), UT-04(근거 없는 경력 생성 거부), UT-15(다른 사용자 조회 차단), UT-17(중복 작업 결과 1건), UT-20(텍스트 PDF와 스캔 PDF), INT-01(업로드 → 추출 → 프로필).
5. THE Mentoring_Package SHALL 통합 데모 직무 데이터 분석(NCS 20010105 빅데이터분석)의 가상 이력서 하나로 INT-01을 끝까지 실행하는 테스트를 갖는다 (D-37).
6. THE Mentoring_Package SHALL 같은 입력과 같은 MockLLM 출력에 대해 같은 Career_Profile 내용을 만든다. 생성 시각과 ID는 비교에서 뺀다 (A F-07 "점수 계산 결정성"의 원칙을 저장 결과에 적용).

### Requirement 12: 로그와 지표

**User Story:** As a 운영 담당, I want 추출·검증 실패를 개인정보 없이 추적하기를, so that 시연 중 장애 원인을 찾을 수 있다.

출처: A F-08 "구조화 로그"·"CloudWatch 커스텀 메트릭", tech.md "보안·개인정보" (로그 항목), AGENTS.md "환경·보안", db §2.7 (MVP는 CloudWatch 구조화 로그 EMF)

#### Acceptance Criteria

1. THE Mentoring_Package SHALL 로그에 `requestId`, 해시한 사용자 ID, `taskId`, 기능 이름, 단계, 상태, 처리 시간, `modelId`, `promptVersion`, 검증 결과, 오류 코드, 재시도 횟수만 남긴다 (A F-08).
2. THE Mentoring_Package SHALL 로그와 오류 `details`에 이력서·자기소개서 원문, 추출 텍스트, Evidence 인용문, 경험 원문, presigned URL, 파일 이름을 남기지 않는다 (A F-08, tech.md "보안·개인정보").
3. THE Mentoring_Package SHALL `DocumentParseFailure`, `EvidenceValidationFailure`, `LLMSchemaFailure`, `AnalysisLatency` 지표를 CloudWatch EMF 형식의 로그로 남긴다. 별도 지표 전송 권한이 필요한 API는 쓰지 않는다 (A F-08, db §2.7, tech.md "착수 전 확인": CloudWatch 지표 전송 권한 없음).

## 백엔드(BACKEND) 담당 작업

A 기능이 실제로 돌려면 BACKEND 소유 파일이 바뀌어야 한다. 이 스펙은 이 파일들을 고치지 않고, 백엔드 담당에게 요청한다 (기반 Requirement 2 Contract_Change_Procedure, AGENTS.md "새 Lambda·권한은 백엔드 담당에게"). 현황은 2026-11-20 `main`(`a556a31`, PR #27·#29·#31 포함) 기준으로 코드에서 확인했다.

### 바꿔야 하는 것

| ID | 할 일 | 바꿀 파일 | 지금 상태 | 관련 |
| --- | --- | --- | --- | --- |
| BE-1 | `/api/v1/mentoring/*` 요청을 `mentoring` 패키지의 REST 입구로 보낸다. User_Id는 `get_user_id()`로 읽어 넘긴다 | `backend/app.py` | 이 경로는 501 `NOT_IMPLEMENTED`를 돌려준다 | Requirement 1 기준 2·7, Requirement 2 기준 1 |
| BE-2 | 비동기 작업 이벤트를 파트별로 나눠 A 작업은 `mentoring`의 Task_Runner로 보낸다 | `backend/app.py` | `"task"` 이벤트를 모두 `interview_api.run_task`로 보낸다 | Requirement 4 기준 5~7, D-19 |
| BE-3 | `ai/mentoring/`을 `mentoring` 패키지로 묶고 `ai/mentoring/requirements.txt`를 설치 목록에 넣는다 | `infra/package.sh` | `backend/*.py`, `ai/interview/`(→ `interview`), `ai/busan-opportunity/src/opportunity/`(→ `opportunity`), `contracts/`(→ `team07_contracts`)를 묶는다 (PR #29). A는 없다 | Requirement 1 기준 1, D-17 |
| BE-4 | A 전용 환경변수를 Lambda 설정에 넣는다: `team07-reference` 테이블 이름, 업로드·텍스트 한도 등. 이름은 이 스펙의 design에서 정해 전달한다 | `infra/setup-api.sh` (`ENV_VARS`) | `TABLE_CAREER_MENTOR`, `CAREER_DOCS_BUCKET`, `MODEL_ID`, `EMBEDDING_MODEL_ID`는 있다 (PR #29). A는 `MODEL_ID`를 그대로 쓴다. 참조 테이블 이름과 한도 값은 없다 | Requirement 1 기준 5, Requirement 6 기준 9 |
| BE-5 | 면접 시작 때 역량 프로필을 그대로 넘기지 말고 A의 요약 변환 함수 결과를 넘긴다. 변환 결과가 없거나 계약 검사에 실패하면 `profile=None` | `backend/interview_api.py` (`load_latest_profile()`) | 역량 프로필 버전의 `skills`·`projects`·`needsConfirmation`을 그대로 넘긴다. A 형식이면 `skills`가 객체 목록이라 `CareerProfileSummary`와 맞지 않는다 | Requirement 8 기준 1, 기반 design.md "Career_Profile_Summary" 절 |
| BE-6 | 개인 문서 경로의 `hashedUserId`를 만드는 방식을 정한다. 회원 탈퇴 삭제(db §2.6 3단계)가 같은 값으로 `users/{hashedUserId}/`를 지워야 하므로 A와 백엔드가 같은 함수를 써야 한다 | `backend/common.py` 또는 `contracts/` (위치는 결정 필요) | 해시 함수가 없다 | Requirement 2 기준 4, 미결정 M-1 |
| BE-7 | 경험 질문 생성을 202 비동기로 두면 `TASK#.taskType`에 그 값을 추가한다 | `docs/db-schema.md` §2.5 | `taskType`에 `DOCUMENT_EXTRACT`, `PROFILE_EXTRACT` 등은 있고 경험 블록용 값은 없다 | Requirement 9 기준 1, 미결정 M-7 |

### 이미 있어서 바꿀 필요 없는 것

| 항목 | 위치 | 관련 |
| --- | --- | --- |
| 사용자 식별 `get_user_id()` (Cognito `sub`) | `backend/common.py` | Requirement 2 기준 1 |
| 테이블 `team07-career-mentor`·`team07-reference` | 생성됨 (db §8) | Requirement 2·7·9·10 |
| 개인 문서 버킷 `team07-career-docs-<계정ID>`와 브라우저 PUT용 CORS | `infra/setup-data.sh` | Requirement 3 기준 3 |
| 공통 계약 `team07_contracts` 배포 묶음 (PR #29) | `infra/package.sh` | Requirement 1 기준 4, Requirement 8 |
| 실행 역할 권한: `team07-*` 테이블 읽기·쓰기, career-docs 객체 읽기·쓰기, Textract 텍스트 탐지, Bedrock 모델 호출, Lambda 자기 호출 | `infra/iam/lambda-role-policy.json` | Requirement 3~7 |
| Lambda 시간 제한 300초 | `infra/setup-api.sh` | Requirement 5 (Textract 비동기 대기) |
| 워크스페이스 연결: 결과에 `GSI1PK = USER#{userId}#WS#{workspaceId}`를 넣으면 워크스페이스 상세에 나온다 | api §6.0, `backend/workspace.py` | Requirement 3 기준 1 (`workspaceId`) |

### 실행 전에 사용자 확인이 필요한 AWS 작업

- `team07-reference` 테이블에 NCS CSV를 실제로 쓰는 일 (Requirement 10 기준 5). 코드는 A가 만들고, 실행은 확인을 받은 뒤 한다.
- BE-3·BE-4 반영 뒤 배포 (`infra/deploy.sh`, `infra/setup-api.sh`). 배포 담당은 한 명으로 고정한다 (AGENTS.md "노션 허브 자료").

## 이 스펙의 미결정

결정 기록(COMMON 소유)에 올릴지는 design 단계에서 함께 정한다. 결정 전까지 해당 기준은 인터페이스 뒤에 둔다.

| ID | 항목 | 선택지 | 관련 |
| --- | --- | --- | --- |
| M-1 | `hashedUserId` 만드는 방식 | 비밀 키를 쓰는 HMAC / 단순 해시 / 백엔드 공통 함수 | Requirement 2 기준 4, db §7, BE-6. C(`uploads/interview/{ivId}/`)는 해시를 쓰지 않아 공통 함수가 없다 |
| M-2 | 추출 텍스트를 사용자가 확인·수정하는 경로 | `POST /documents/text`에 `sourceDocumentId`를 받아 새 버전 / 새 경로 추가 | Requirement 4 기준 8, A F-01 처리 6단계 ("확인·수정 화면 제공"). A §6.1에 경로가 없다 |
| M-3 | 문서·경험 블록 개별 삭제 | A §6.1에 삭제 경로 없음 / 새 경로 추가 | A F-01B 처리 7단계. 회원 탈퇴 삭제는 BACKEND(db §2.6) |
| M-4 | `career.profile.completed` 이벤트 | 이벤트 버스 권한 전까지 발행하지 않고 `TASK#` 완료로 대신 / 다른 수단 | A F-01 처리 12단계. EventBridge 권한 없음 (tech.md "착수 전 확인") |
| M-5 | 요약 한도를 넘는 항목을 고르는 규칙 | 최근 버전 순 / 근거 강도 순 / 사용자 지정 순 | Requirement 8 기준 4, D-40 |
| M-6 | 패키지 CSV를 저장소에 넣을지 | `structured/` CSV를 `ai/mentoring/` 아래에 넣기 / 실행할 때 경로를 받기 | Requirement 10. 라이선스 열은 "이용허락범위 제한 없음"이지만 패키지 `LICENSE_AND_LIMITATIONS.md` 확인 필요. 저장소는 공개 |
| M-7 | 경험 질문 생성을 202 비동기로 둘지 | A §6.1대로 202 / 응답 시간이 짧으면 동기 200 | Requirement 9 기준 1, BE-7 (202면 `taskType` 추가 필요) |
