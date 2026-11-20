# Requirements Document

## Introduction

공통 기반(common-foundation)은 A(역량 분석·첨삭·학습 경로), B(부산 기회 추천), C(AI 모의면접), 공통 백엔드, 프론트엔드가 서로를 기다리지 않고 병렬로 개발할 수 있게 하는 최소한의 공통 약속이다. 저장소 기본 파일, 폴더 소유 규칙, API 공통 규약, 파트 경계를 넘는 데이터 계약과 예시 데이터, 사용자 식별 경계, Backend와 Ai 코드의 연결 경계, 자원 이름 규칙, 결정 기록만 다룬다.

근거와 전제:
- B §9와 C §9는 해커톤 0~2시간에 계약을 합의하고 API 명세와 가짜 응답을 프론트·백엔드에 넘기도록 계획한다. 공통 기반은 이 시간 안에 끝낼 수 있는 크기로 유지한다.
- 최상위 폴더는 PR #1·#2로 정했고, 백엔드·인프라·공통 문서는 PR #9~#14로 들어왔다 (이전 뼈대 `4aa11cc`를 정리해 다시 넣음, D-25).
- 결정 상태 (2026-11-20): 확정 담당이 정한 항목은 `CONFIRMED`이고 이 스펙의 기준은 그 결정을 따른다. 결정 내용과 구현은 "결정 기록" 표, `docs/api.md`(공통 API 규칙), `docs/db-schema.md`(v1.3), `backend/`·`infra/`(PR #9~#14, 배포됨)가 기준이다. 결정이 없는 항목(D-27 MVP 우선순위 등. D-23은 Bedrock Agents로 정했다가 D-38(Strands)로 바뀜, D-24는 Next.js로 나중에 확정)만 `OPEN`으로 남기고, 그 항목은 인터페이스 뒤에 두거나 담당이 정할 때까지 임의로 정하지 않는다.
- 아래 각 Requirement의 기준 중 결정과 이름·형식이 다른 곳은 Requirement 첫머리의 "결정 반영" 문단이 우선한다.
- 문서 표기: A = `docs/개발계획서1.md`, B = `docs/개발계획서2.md`, C = `docs/개발계획서3.md`, 제안서 = `docs/프로젝트_제안서.md`.

범위에서 제외 (다른 스펙이 담당):
- 각 파트의 기능 구현 (A F-01~F-08, B B-01~B-17, C 면접 함수)과 파트 내부 모델·테이블 설계
- AWS 자원 생성·배포·권한 변경 (AGENTS.md "환경·보안": 사용자에게 먼저 확인), IaC 도구 선택
- 통합 Agent 프레임워크 선택 (A F-06 소유), 프론트엔드 프레임워크 선택, KB 적재, 외부 API 수집
- CI 구성 (CONTRIBUTING "자동 검사와 테스트": CI는 있으면 확인하는 선택 사항)

후속 스펙과의 경계: backend-platform(`backend/`), mentoring-profile-storybank·mentoring-fit-review-learning·mentoring-agent-quality(`ai/mentoring/`), busan-opportunity-data·busan-opportunity-recommend·busan-opportunity-notify(`ai/busan-opportunity/`), interview-functions(`ai/interview/`), frontend-app(`frontend/`), integration-e2e. 공통 기반은 이 스펙들이 쓰는 폴더의 내부 구조를 정하지 않는다.

## Glossary

- **Foundation**: 이 스펙이 만드는 공통 기반 산출물 전체
- **Part**: 소유 단위. A(`ai/mentoring/`), B(`ai/busan-opportunity/`), C(`ai/interview/`), BACKEND(`backend/`), FRONTEND(`frontend/`), COMMON(공통 파일) 중 하나 (structure.md "파트와 소유 범위")
- **Repository_Baseline**: 루트 README, 루트 `.gitignore`, Python 버전 선언, 파트별 의존성·테스트 배치 규칙
- **Local_Check**: 개발자가 로컬에서 한 명령으로 실행하는 확인 절차. 파트별 테스트, Contract_Package 검사, Secret_Scanner, Import_Rule_Checker를 실행한다
- **Ownership_Map**: 최상위 폴더와 공통 파일마다 소유 Part를 적은 표
- **Contract_Change_Procedure**: COMMON 소유 파일이나 다른 Part 소유 파일을 바꿀 때 따르는 절차
- **API_Convention_Doc**: 모든 Part의 REST API가 따르는 공통 규약 문서 (단일 기준)
- **Contract_Package**: 파트 경계를 넘는 데이터 계약을 기계로 검사할 수 있는 스키마로 담은 묶음. 각 계약의 직렬화·검사·변환 함수를 포함한다
- **Error_Envelope**: 공통 오류 응답 형식
- **Error_Code_Catalog**: 공통 오류 코드, HTTP 상태, 기본 retryable 값, 출처 Part를 적은 목록
- **Async_Task_Status**: 202 응답 뒤 상태 조회에 쓰는 공통 상태 형식
- **Status_Extension**: 특정 Part가 Async_Task_Status에 추가로 선언한 상태 값이나 필드 (예: A의 `REQUIRES_USER_REVIEW`, C의 `stage`)
- **Identity_Resolver**: REST 핸들러와 Agent 도구 입구가 사용자 ID를 얻는 유일한 함수
- **Identity_Mode**: Identity_Resolver가 사용자 ID를 읽는 방식 (Cognito JWT, 개발용 사용자 헤더 등). 방식 선택은 Decision_Log 항목이다
- **Common_Profile**: 공통 백엔드가 소유하고 다른 Part가 읽는 공통 프로필 계약 (B §10.3)
- **Posting_For_Analysis**: B가 만들고 A·C가 읽기 전용으로 쓰는 공고 계약 (B §10.2, A §4.4·§12.3)
- **Job_Requirement_View**: A §4.4 JobRequirement 형식으로 바꾼 Posting_For_Analysis
- **Interview_Job_Context**: C의 `start_interview`에 넘기는 직무 정보 (C §5.2 `job`, B §10.1)
- **Career_Profile_Summary**: A가 만들고 C가 받는 역량 요약 계약 (A §12.2, C §5.2 `profile`)
- **Fixture_Set**: Contract_Package의 각 계약에 대한 예시 데이터 묶음. 모든 데이터는 가상이다
- **Secret_Scanner**: 커밋 대상 파일에서 AWS 계정 ID 형태(앞뒤가 숫자가 아닌 연속 12자리 숫자)와 AWS 액세스 키 ID 형태(`AKIA` 또는 `ASIA` 뒤에 영문 대문자나 숫자 16자가 이어지는 20자 문자열)의 문자열을 찾는 검사. `<계정ID>`처럼 꺾쇠괄호로 감싼 자리표시자는 제외한다. Fixture_Set 파일에서는 이메일 주소, 전화번호, 주민등록번호 형태도 함께 찾는다 (Requirement 11·13)
- **Import_Rule_Checker**: Part 사이의 import 방향 규칙을 검사하는 도구
- **Integration_Seam_Doc**: Backend가 Ai 아래 각 Part 코드를 부르는 입구와 패키징 방식을 적은 문서
- **Resource_Naming_Convention**: 리전, 자원 이름 접두사, 태그, 환경변수 이름, 자원 소유 Part를 정한 문서
- **Decision_Log**: 미확정 항목을 선택지·제안 기본값·출처·담당·상태와 함께 적은 단일 문서. 둘 이상의 Part에 영향을 주는 항목과, 한 Part에만 속하지만 steering이 미확정으로 둔 항목을 모두 담는다
- **Decision_Status**: Decision_Log 항목의 상태. `OPEN`(선택지만 있음), `PROPOSED`(제안 기본값 있음, 팀 확인 전), `CONFIRMED`(팀 확인), `SUPERSEDED`(다른 항목으로 대체) 중 하나
- **Seam**: 미확정 결정을 감추는 인터페이스. 결정이 바뀌어도 Seam을 쓰는 코드는 바뀌지 않는다

## Requirements

### Requirement 1: 저장소 기본 구성

**User Story:** As a 팀 개발자 또는 AI 코딩 에이전트, I want 저장소의 폴더 역할과 실행 방법을 한곳에서 확인하기를, so that 다른 파트를 기다리지 않고 바로 작업을 시작할 수 있다.

출처: structure.md "저장소 구성"·"코딩 규칙", CONTRIBUTING "자동 검사와 테스트", tech.md "보안·개인정보"

#### Acceptance Criteria

1. THE Repository_Baseline SHALL 루트 README에 최상위 폴더 `ai/mentoring/`, `ai/busan-opportunity/`, `ai/interview/`, `backend/`, `frontend/`, `docs/`, `.kiro/`와 Foundation이 추가하는 모든 공통 폴더를 한 행에 하나씩 나열하고, 각 행에 소유 Part 하나와 근거 명세 문서(A·B·C·제안서·steering·CONTRIBUTING 중 해당 문서와 절)를 적는다. README에 나열된 폴더 집합은 저장소의 실제 최상위 폴더 집합(`.git/` 제외)과 같아야 한다.
2. THE Repository_Baseline SHALL 루트 `.gitignore`로 다음 범주를 Git 추적에서 제외한다: 환경변수 파일(`.env`, `.env.*`), 자격 증명 파일(AWS 자격 증명·키 파일), Python 가상환경 폴더, 빌드 산출물, 테스트·도구 캐시(pytest 캐시, Python 바이트코드 캐시 포함), 운영체제 생성 파일(macOS `.DS_Store` 포함). 범주마다 예시 경로 하나 이상을 `git check-ignore`로 확인했을 때 제외되어야 하고, Contract_Package와 Fixture_Set 파일은 제외되지 않아야 한다.
3. THE Repository_Baseline SHALL Python 버전을 저장소의 정확히 한 위치에 선언하고, 그 선언 옆에 Decision_Log 항목 ID를 붙인다. 이 Decision_Log 항목은 두 선택지(Python 3.12, B 명세 출처; Python 3.13, 이전 뼈대 `4aa11cc` 출처)를 출처와 함께 적고, 팀 확인 전에는 Decision_Status를 `OPEN` 또는 `PROPOSED`로 둔다. 다른 파일에는 이와 다른 Python 버전 선언이 없어야 한다.
4. THE Repository_Baseline SHALL 루트 README에 Part 폴더 배치 규칙을 적는다. 규칙 내용: 코드를 가진 각 Part 폴더(A, B, C, BACKEND, FRONTEND)는 자기 폴더 안에 의존성 파일 하나와 테스트 폴더 하나를 가진다. 한 Part의 테스트는 다른 Part의 의존성 파일을 설치하지 않고 실행된다. Part 폴더의 내부 구조는 해당 Part의 후속 스펙이 정한다.
5. WHEN 개발자가 저장소 루트에서 Local_Check 전체 실행 명령을 실행하면, THE Local_Check SHALL AWS 자격 증명 환경변수와 자격 증명 파일이 없고 외부 네트워크가 차단된 상태에서 Part 5개(A, B, C, BACKEND, FRONTEND)의 테스트, Contract_Package 검사, Secret_Scanner, Import_Rule_Checker를 모두 실행한다. 이어서 Part와 검사마다 "성공", "실패", "테스트 없음" 중 하나를 한 줄씩 출력한다.
6. IF 어떤 Part의 테스트 폴더가 없거나 테스트 폴더 안에 테스트 파일이 0개이면, THEN THE Local_Check SHALL 해당 Part를 "테스트 없음"으로 보고하고 이를 실패로 세지 않는다. 전체 성공 여부는 나머지 Part의 테스트, Contract_Package 검사, Secret_Scanner, Import_Rule_Checker의 결과로만 판정한다.
7. THE Repository_Baseline SHALL 루트 README에 저장소 루트에서 실행하는 Local_Check 전체 실행 명령 하나와 Part 5개 각각의 실행 명령을 적는다. 각 명령은 README에 적힌 그대로 복사해 실행했을 때 criterion 5의 결과 형식으로 출력해야 한다.
8. IF Part 테스트, Contract_Package 검사, Secret_Scanner, Import_Rule_Checker 중 하나 이상이 실패하면, THEN THE Local_Check SHALL 남은 Part와 검사를 끝까지 실행한다. 그 뒤 실패한 Part 또는 검사의 이름과 실패한 테스트 이름을 출력하고, 0이 아닌 종료 코드로 끝낸다. 모든 항목이 "성공" 또는 "테스트 없음"이면 종료 코드는 0이다.
9. IF Local_Check 실행 중 어떤 테스트가 AWS 서비스나 외부 네트워크에 접속을 시도하면, THEN THE Local_Check SHALL 그 테스트를 실패로 처리하고 해당 Part를 "실패"로 보고한다. 출력에는 테스트 이름과 외부 접속 시도가 원인이라는 표시를 포함하며, 접속 결과를 기다리느라 실행을 멈추지 않는다.

### Requirement 2: 폴더 소유와 공통 파일 변경 절차

**User Story:** As a 병렬로 작업하는 개발자, I want 누가 어떤 파일을 고칠 수 있는지 분명히 알기를, so that 서로의 변경이 충돌하거나 다시 작업하는 일을 줄일 수 있다.

출처: structure.md "파트와 소유 범위"·"Spec·작업 진행 원칙"·"협업 규칙", AGENTS.md "파트"·"협업", CONTRIBUTING "코드 리뷰"

#### Acceptance Criteria

1. THE Ownership_Map SHALL 다음 경로마다 소유 Part를 정확히 하나씩 지정한다. 대상은 `.git/`을 뺀 모든 최상위 폴더, `ai/` 아래 3개 Part 폴더(`ai/mentoring/`, `ai/busan-opportunity/`, `ai/interview/`), 그리고 공통 파일(루트 README, 루트 `.gitignore`, Contract_Package, Fixture_Set, API_Convention_Doc, Integration_Seam_Doc, Resource_Naming_Convention, Decision_Log, Ownership_Map, Contract_Change_Procedure, `.kiro/steering/`, `AGENTS.md`, `docs/`)이다. 각 항목에는 저장소 루트 기준 경로 1개와 소유 Part 1개(A, B, C, BACKEND, FRONTEND, COMMON 중 하나)를 적는다.
2. THE Ownership_Map SHALL 각 Part는 자신이 소유한 경로만 직접 수정한다는 규칙을 적는다. COMMON 소유 경로나 다른 Part 소유 경로를 수정할 때는 Contract_Change_Procedure를 따른다는 규칙도 함께 적는다.
3. THE Ownership_Map SHALL 후속 스펙 10개(backend-platform, mentoring-profile-storybank, mentoring-fit-review-learning, mentoring-agent-quality, busan-opportunity-data, busan-opportunity-recommend, busan-opportunity-notify, interview-functions, frontend-app, integration-e2e)마다 주로 쓰는 폴더 1개와 그 폴더의 소유 Part를 적는다. 그 폴더의 내부 구조는 Ownership_Map에 적지 않고 해당 후속 스펙에 맡긴다.
4. WHEN PR이 COMMON 소유 경로나 다른 Part 소유 경로를 수정하고 그 수정이 계약(Contract_Package의 계약, API_Convention_Doc의 규약, Integration_Seam_Doc의 연결 경계, Resource_Naming_Convention의 이름 규칙)을 바꾸면, THE Contract_Change_Procedure SHALL 바뀐 계약을 정의한 문서의 수정을 같은 PR에 포함하도록 요구한다. 그 문서를 수정한 커밋은 계약을 쓰는 코드를 수정한 커밋보다 앞에 있어야 한다.
5. THE Contract_Change_Procedure SHALL CONTRIBUTING의 이슈·브랜치·커밋·PR 규칙을 그대로 따르도록 요구한다. 또한 공통 계약 변경 PR 본문의 "참고 사항"에 영향을 받는 Part 목록(1개 이상)과 관련 Decision_Log 항목 ID를 적도록 요구하고, 관련 항목이 없으면 "없음"이라고 적도록 요구한다.
6. WHEN PR이 COMMON 소유 경로나 다른 Part 소유 경로를 수정하면, THE Contract_Change_Procedure SHALL 두 가지를 요구한다. 첫째, PR에서 영향을 받는 각 Part의 담당자에게 리뷰를 요청한다. 둘째, 머지 전에 PR 링크와 영향을 받는 Part를 팀 채널에 알린다. 리뷰 승인(`Approve`)은 머지 조건으로 두지 않는다 (CONTRIBUTING "코드 리뷰": 작성자가 검증했다면 승인 없이 머지할 수 있다).
7. IF 한 경로가 Ownership_Map의 폴더 항목과 그보다 더 구체적인 파일·폴더 항목에 함께 해당하면, THEN THE Ownership_Map SHALL 더 구체적인 항목의 소유 Part를 그 경로에 적용한다는 규칙을 적는다.
8. IF PR이 수정하거나 추가하는 경로의 소유 Part가 Ownership_Map에 없으면, THEN THE Contract_Change_Procedure SHALL 그 PR을 COMMON 소유 경로 변경과 같은 절차로 처리하도록 요구한다. 또한 같은 PR에서 그 경로의 소유 Part 항목을 Ownership_Map에 추가하도록 요구한다.

### Requirement 3: API 공통 규약

**User Story:** As a 프론트엔드·백엔드·파트 개발자, I want 모든 파트의 API가 같은 규약을 따르기를, so that 화면과 백엔드가 응답 처리를 한곳에 모으고 파트별 차이로 다시 고치지 않아도 된다.

출처: A §6 "공통 정책"·§6.6, B §5.1, C §5.1, tech.md "API (규약 미확정, 두 안이 공존)"

#### Acceptance Criteria

1. THE API_Convention_Doc SHALL 경로 접두사, JSON 키 표기, 본문 인코딩(JSON UTF-8, `Content-Type: application/json`), 날짜·시각 형식, 금액 표기, Error_Envelope, 비동기 처리 방식, `Idempotency-Key` 헤더, 데이터 기준일 필드를 하나의 문서 안에서 항목마다 별도 절로 정의하고, 절마다 근거 명세 절을 적는다 (tech.md API 공통 항목, A §6).
2. THE API_Convention_Doc SHALL 경로 접두사를 `/api/v1/mentoring`, `/api/v1/opportunities`, `/api/v1/interview`로 적고 (A §6, B §5.1, C §5.1), Decision_Log 항목 ID `D-01`과 그 항목의 현재 Decision_Status를 함께 표시한다.
3. THE API_Convention_Doc SHALL JSON 키를 카멜 표기로, Python 함수와 인자 이름을 snake_case로 적고 (B §5.1, C "백엔드와의 약속"), Decision_Log 항목 ID `D-02`와 그 항목의 현재 Decision_Status를 함께 표시한다.
4. THE API_Convention_Doc SHALL 날짜를 `YYYY-MM-DD`(예: `2026-11-21`)로, 시각을 초 단위까지 적고 `+09:00` 오프셋을 붙인 ISO 8601(예: `2026-11-21T04:52:00+09:00`)로 정의하고 (B §5.1, B 예시 응답 `dataAsOf`, tech.md API 공통 항목), A 예시의 `Z` 표기(A §4.4 `checkedAt`)가 이 형식과 다르다는 점을 Decision_Log 항목 `D-29`로 올려 그 항목 ID와 Decision_Status를 표시한다.
5. THE API_Convention_Doc SHALL 금액을 소수점 없는 정수 값과 단위 필드의 조합으로 정의하고, 단위 필드 값은 `MANWON_YEAR`, `MANWON_MONTH`, `MANWON`, `WON` 네 개로 한정하며 (B §5.1·§5.6), 이 규칙이 이전 api.md의 원 단위 정수 표기와 다르므로 Decision_Log 항목 ID `D-30`과 Decision_Status를 함께 표시한다 (tech.md "기술 미확정" 3).
6. THE API_Convention_Doc SHALL 30초를 넘을 수 있는 작업을 HTTP 202로 접수하는 방식으로 정의한다. 202 응답 본문에는 리소스 ID와 `status` 값 `PENDING`이 들어가고 (A §6), 상태 조회 엔드포인트는 Async_Task_Status 형식(Requirement 5)으로 결과를 돌려준다 (tech.md API 공통 항목, C §2.3). 리소스 ID 필드 이름은 각 Part 절에 적고 (예: A `reviewId`·`learningPathId`, B `jobId`), 접수 뒤의 처리 방식은 Decision_Log 항목 `D-19`로 남겨 이 문서에서 정하지 않는다.
7. THE API_Convention_Doc SHALL 생성·저장 POST 요청이 `Idempotency-Key` 헤더를 받는 규칙을 정의한다 (A §6, B §5.1). 같은 사용자가 같은 키와 같은 본문으로 다시 보낸 요청은 두 번째 저장 없이 첫 요청과 같은 리소스 ID와 결과를 돌려받는다고 적는다 (A §6 "동일 사용자+body hash+키", A F-01 "중복 요청", B T-16). 헤더가 필수인지 선택인지와 키 보존 기간은 각 Part 절에 적는다 (A §6 "지원 권장", B §6.4 OppIdempotency TTL 1시간).
8. THE API_Convention_Doc SHALL Error_Envelope의 `message`와 화면에 보여주는 오류 안내 문구를 한국어로 정의하고, `code`는 Error_Code_Catalog에 있는 영문 대문자 코드를 그대로 쓴다고 정의한다 (tech.md API 공통 항목, A §6.6, B §5.1).
9. WHERE 어떤 Part가 공통 규약에 없는 필드나 값(예: A `REQUIRES_USER_REVIEW`, B `stale`, C `stage`)을 써야 하면, THE API_Convention_Doc SHALL 해당 확장을 그 Part 절에 추가 필드나 추가 값으로만 적는다. 확장마다 소유 Part와 근거 명세 절을 함께 적고, 공통 절에 정의된 필드의 이름·형식·의미는 바꾸거나 다시 정의하지 않는다.
10. THE API_Convention_Doc SHALL 파트별 점수 이름과 범위(A `fitScore`·`potentialUpperBound` 0~100, B `matchScore` 0~1·`rankScore`, C 면접 종합 점수 0~100, B-16 준비도 1~9칸)와 파트별 지원자격 상태 값(A `ELIGIBLE/INELIGIBLE/NEEDS_VERIFICATION`, B 공고 `MET/NOT_MET/UNKNOWN`, B 정책 `ELIGIBLE/NOT_ELIGIBLE/CHECK_NEEDED`)을 소유 Part와 함께 나열한다. 범위가 명세에 없는 점수(예: `rankScore`)는 "명세에 없음"으로 적고, Decision_Log 항목 ID `D-11`과 Decision_Status를 함께 표시한다 (tech.md "점수", "기술 미확정" 6).
11. IF Contract_Package에서 파트 경계를 넘는 계약의 스키마에 중첩 객체를 포함해 이름이 정확히 `score`인 필드가 있으면, THEN THE Contract_Package SHALL 계약 이름과 해당 필드 경로를 담은 검사 오류를 낸다. 점수 필드는 소유 Part가 드러나는 이름(예: `fitScore`, `matchScore`)만 통과한다.
12. THE API_Convention_Doc SHALL 데이터 기준일 필드를 Part 명세 이름 그대로 나열하고 (A `checkedAt`·`sourceCheckedAt`, B `dataAsOf`), 각 필드를 "응답에 담긴 외부·수집 데이터를 마지막으로 확인한 날짜 또는 시각"으로 정의한다. 응답 생성 시각과는 따로 표시한다고 적고 (A §4.5 "응답 기준일과 공식 자료 기준일을 분리 표시"), Decision_Log 항목 ID `D-06`과 Decision_Status를 함께 표시한다.
13. THE API_Convention_Doc SHALL 같은 사용자가 같은 `Idempotency-Key`로 본문이 다른 POST 요청을 보낼 때의 처리를 확정하지 않는다. 이 경우를 선택지와 출처(A §7.1 Idempotency `requestHash`)가 있는 Decision_Log 항목 `D-31`로 올리고, 그 항목 ID와 Decision_Status를 7번 규칙 옆에 표시한다.

### Requirement 4: 공통 오류 응답

**User Story:** As a 프론트엔드 개발자, I want 모든 파트의 오류가 같은 형식으로 오기를, so that 다시 시도 버튼과 안내 문구를 한 번만 구현할 수 있다.

출처: A §6.6, B §5.8, C §5.1 "오류 형식"·"백엔드와의 약속", tech.md "API" 오류 행

#### Acceptance Criteria

1. THE Contract_Package SHALL Error_Envelope를 최상위 `error` 객체 하나로 정의하고, `error` 아래에 필수 필드 `code`(Error_Code_Catalog에 있는 문자열), `message`(빈 문자열이 아닌 문자열), `requestId`(빈 문자열이 아닌 문자열), `retryable`(boolean)과 선택 필드 `details`(객체)를 둔다 (B §5.1, C §5.1, `details`는 A §6.6).
2. THE Contract_Package SHALL Error_Code_Catalog에 A §6.6, B §5.8, C §5.1 표에 있는 오류 코드를 하나도 빠짐없이 담는다. 코드마다 HTTP 상태 하나, 기본 `retryable` 값, 그 코드를 쓰는 출처 Part 목록을 적는다.
3. IF 출처 문서가 한 코드에 HTTP 상태를 둘 이상 허용하거나 (A §6.6 `RESOURCE_NOT_OWNED` 403/404, `MODEL_UNAVAILABLE`·`SOURCE_UNAVAILABLE` 502/503), 기본 `retryable` 값을 적지 않았거나 (A §6.6 표에는 retryable 열이 없음), 같은 코드에 Part마다 다른 값을 적었으면, THEN THE Error_Code_Catalog SHALL 그 칸에 Decision_Log 항목 ID `D-32`를 붙이고, 해당 Decision_Log 항목은 Decision_Status가 `CONFIRMED`가 될 때까지 출처 값을 제안 기본값으로 둔 `PROPOSED` 상태를 유지한다.
4. IF 같은 상황에 Part마다 다른 코드가 있으면 (예: A `VALIDATION_ERROR`와 B·C `INVALID_INPUT`, A `MODEL_UNAVAILABLE`과 B·C `AWS_SERVICE_ERROR`), THEN THE Error_Code_Catalog SHALL 두 코드를 모두 유효한 코드로 남기고, 서로 별칭 관계로 적고, 어느 코드를 대표로 쓸지 정하는 Decision_Log 항목 ID `D-04`를 붙인다.
5. WHEN 유효한 Error_Envelope 객체를 JSON으로 직렬화한 뒤 다시 읽으면, THE Contract_Package SHALL 원래 객체와 필드 이름, 값, `details` 포함 여부가 모두 같은 객체를 돌려준다 (왕복 속성).
6. IF Error_Envelope 데이터에 필수 필드가 없거나, 필드 타입이 기준 1과 다르거나, `code`가 Error_Code_Catalog에 없거나, `error` 객체 안이나 최상위에 정의되지 않은 필드가 있으면, THEN THE Contract_Package SHALL 객체를 만들지 않고, 문제가 된 필드 이름을 모두 담은 검사 오류를 낸다.
7. IF Error_Envelope 데이터에서 `requestId`가 `error` 객체 밖 최상위에 있으면 (A §6.6 예시, tech.md "API" 오류 행), THEN THE Contract_Package SHALL 기준 6에 따라 검사 오류를 내고, Error_Code_Catalog 문서는 `requestId` 위치를 정하는 Decision_Log 항목 ID `D-03`을 붙인다.
8. WHEN 호출자가 C의 `InterviewError(code, message, retryable)`와 빈 문자열이 아닌 `requestId`를 넘기면, THE Contract_Package SHALL `InterviewError`와 같은 `code`, `message`, `retryable`, 넘겨받은 `requestId`를 갖고 `details`는 없는 Error_Envelope를 돌려준다 (C "백엔드와의 약속", structure.md).
9. IF 호출자가 넘긴 `InterviewError`의 `code`가 Error_Code_Catalog에 없거나 `requestId`가 비어 있으면, THEN THE Contract_Package SHALL Error_Envelope를 돌려주지 않고, 문제가 된 필드 이름(`code` 또는 `requestId`)을 담은 검사 오류를 낸다.

### Requirement 5: 비동기 작업 상태

**User Story:** As a 프론트엔드·백엔드 개발자, I want 오래 걸리는 작업의 상태를 같은 형식으로 조회하기를, so that 파트마다 다른 폴링 로직을 만들지 않아도 된다.

출처: A §6 "공통 정책"·F-01 "상태 전이", B §5.1, C §5.1·§5.4, tech.md "API" 오래 걸리는 작업 행

#### Acceptance Criteria

1. THE Contract_Package SHALL Async_Task_Status의 공통 상태 값을 대문자 문자열 `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` 네 개로 정의한다 (B §5.1, C §5.1 "상태 값").
2. THE Contract_Package SHALL `COMPLETED`와 `FAILED`를 공통 종료 상태로, `PENDING`과 `PROCESSING`을 공통 비종료 상태로 표시한다 (C §5.4: `COMPLETED`·`FAILED`면 조회 중단, A F-01: 결과 완료 전 조회는 `PENDING/PROCESSING`).
3. WHERE 어떤 Part가 상태 값 형태의 Status_Extension을 선언하면, THE Contract_Package SHALL 추가 값마다 선언한 Part와 종료 상태 여부(참 또는 거짓)를 함께 기록하고, 공통 상태 값 네 개와 이름이 같은 추가 값은 받지 않는다 (A `REQUIRES_USER_REVIEW`·`PARTIAL_SUCCESS`, A F-01 "이후 `REQUIRES_USER_REVIEW`로 종료", A §6 "상태에 따른 UI").
4. IF Async_Task_Status의 `status` 값이 `FAILED`이면, THEN THE Contract_Package SHALL Error_Envelope의 `error` 객체를 필수 필드로 요구하고, `error`가 없거나 Error_Envelope 형식 검사에 실패하면 `error` 필드 이름을 담은 검사 오류를 낸다.
5. IF Async_Task_Status 데이터에 `status` 필드나 Part가 선언한 작업 식별 ID 필드가 없거나, `status` 값이 공통 상태 값과 그 데이터를 만든 Part의 Status_Extension 상태 값 어느 쪽과도 대소문자까지 정확히 일치하지 않거나(예: 이전 뼈대의 `pending`·`done`, 다른 Part가 선언한 확장 값), 필드 형태 Status_Extension의 값이 허용 값 목록에 없으면, THEN THE Contract_Package SHALL 해당 필드 이름과 값을 담은 검사 오류를 내고 그 데이터를 유효한 Async_Task_Status로 받지 않는다.
6. THE Contract_Package SHALL 모든 유효한 Async_Task_Status 객체(Fixture_Set의 Async_Task_Status 예시를 모두 포함)를 JSON으로 직렬화한 뒤 다시 읽은 결과가 원래 객체와 필드 이름, 필드 값, 값이 null인 필드(C §5.4 예시의 `"report": null`)까지 같도록 한다 (왕복 속성).
7. THE Contract_Package SHALL 모든 Async_Task_Status 객체에 `status` 필드와 작업 식별 ID 필드 1개를 필수로 요구하고, 이 ID 필드 이름을 Part별로 기록한다 (A `taskId` 또는 리소스 ID: A §6 "공통 정책", B `jobId`: B §5.1, C `sessionId`: C §5.1·§5.4).
8. WHERE 어떤 Part가 필드 형태의 Status_Extension을 선언하면, THE Contract_Package SHALL 그 필드의 허용 값 목록을 기록하고, 작업의 종료 여부는 `status` 값만으로 정한다. 예: C `stage`의 허용 값은 `QUESTION_GENERATING`, `NEXT_QUESTION_READY`, `TRANSCRIBING`, `JUDGING`, `REPORT_GENERATING`, `REPORT_READY` 6개이다 (C §5.1). `stage`가 `REPORT_READY`여도 `status`가 `COMPLETED`가 아니면 작업은 종료되지 않은 상태다.

### Requirement 6: 사용자 식별 경계

**User Story:** As a 보안을 책임지는 백엔드 개발자, I want 모든 입구가 사용자 ID를 같은 함수로만 얻기를, so that 인증 방식이 정해지기 전에도 다른 사용자 데이터를 조회하는 경로가 생기지 않는다.

출처: A §6 "공통 정책"·F-06 "검증 정책"·§5 F-08 "보안 필수", B §5.1·§5.9·T-20, C §5.1 "인증", tech.md "기술 미확정" 1·"보안·개인정보"

결정 반영 (D-07·D-35 CONFIRMED): Identity_Resolver는 `backend/common.py`의 `get_user_id()`다. Identity_Mode 기본값은 Cognito JWT(사용자 풀 `team07-users`, 아이디·비밀번호 로그인 `POST /api/v1/auth/login`)이고 출처는 API Gateway JWT authorizer가 검증한 `sub`다. 개발용 사용자 헤더는 `X-User-Id`, 설정 값은 `ALLOW_DEV_USER_HEADER=1`이며 로컬 테스트에서만 켠다. 배포 Lambda에는 이 값을 두지 않는다(`infra/setup-auth.sh`가 지움). 기준 7·11의 "설정이 없으면 오류"는 "설정이 없으면 Cognito JWT 모드"로 읽는다.

#### Acceptance Criteria

1. THE Identity_Resolver SHALL REST 핸들러와 Agent 도구 입구가 사용자 ID를 얻는 유일한 함수가 되도록 하나의 공개 인터페이스를 제공한다. 이 인터페이스는 입구 종류(REST 또는 Agent 도구)와 해당 입구 데이터를 인자로 받는다.
2. WHEN REST 요청이 들어오면, THE Identity_Resolver SHALL 현재 Identity_Mode가 정한 출처 하나에서만 사용자 ID를 읽어 바꾸지 않고 그대로 돌려준다. Cognito JWT 방식이라면 출처는 `sub` claim이다 (A §6, B §5.1). Identity_Mode가 정하지 않은 출처는 무시한다. 예를 들어 Cognito JWT 방식에서는 개발용 사용자 헤더가 있어도 읽지 않는다.
3. WHEN Agent 도구 호출이 들어오면, THE Identity_Resolver SHALL 백엔드가 넣은 세션 속성(B §5.9 `sessionAttributes.userId`)에서만 사용자 ID를 읽어 바꾸지 않고 그대로 돌려준다.
4. FOR ALL 요청 본문, 쿼리 문자열, 경로 파라미터, 모델 파라미터에 담긴 `userId` 값, THE Identity_Resolver SHALL 그 값이 인증 컨텍스트나 세션 속성의 값과 달라도 무시하고, 인증 컨텍스트나 세션 속성의 값만 돌려준다 (B T-20, A §6). C의 면접 `sessionId`도 사용자 ID로 쓰지 않는다 (C §4 "인증 수단이 아님").
5. IF 입구의 출처(REST는 Identity_Mode가 정한 출처, Agent 도구는 `sessionAttributes.userId`)에 사용자 ID가 없거나, 값이 문자열이 아니거나, 앞뒤 공백을 뺀 길이가 1~128자를 벗어나면, THEN THE Identity_Resolver SHALL Error_Code_Catalog의 `UNAUTHORIZED`(HTTP 401) 오류를 낸다 (A §6.6). 이때 다른 입력에 담긴 `userId` 값을 대신 쓰지 않는다. 128자 상한은 36자 UUID인 Cognito `sub`보다 넉넉하게 잡은 값이다.
6. WHERE Identity_Mode가 개발용 사용자 헤더 방식으로 설정되면, THE Identity_Resolver SHALL API_Convention_Doc에 적힌 개발용 헤더 이름 하나(Decision_Log `D-35`)에서만 사용자 ID를 읽는다 (B §5.1).
7. IF 개발용 사용자 헤더 방식이 지정되었고 Resource_Naming_Convention에 정한 배포 환경 설정 값(Decision_Log `D-35`)이 공개 배포를 나타내면, THEN THE Identity_Resolver SHALL 초기화 단계에서 첫 요청을 처리하기 전에 설정 검사 오류를 내고, 어떤 요청에도 사용자 ID를 돌려주지 않는다 (B §5.1 "공개 배포 전에 제거", tech.md "보안·개인정보").
8. THE Identity_Resolver SHALL 로그용으로 사용자 ID의 해시 값을 돌려주는 함수를 제공하고, 이 함수는 다음 조건을 만족한다 (tech.md "보안·개인정보", A F-08 구조화 로그 `userIdHash`):
   - 같은 사용자 ID에는 항상 같은 값을 돌려준다.
   - Fixture_Set의 서로 다른 사용자 ID에는 서로 다른 값을 돌려준다.
   - 돌려준 값에 원래 사용자 ID 문자열이 들어 있지 않다.
9. THE Identity_Resolver SHALL Identity_Mode가 바뀌어도 같은 공개 인터페이스(같은 인자와 반환 형식)를 유지하고, Identity_Mode 선택은 Decision_Log D-07 항목으로 남긴다 (tech.md "기술 미확정" 1).
10. THE Identity_Resolver SHALL 호출 인자로 받은 입구 데이터와 Identity_Mode 설정만으로 결과를 정한다. AWS 서비스, 네트워크, 파일을 호출하지 않으며, 같은 입력과 같은 설정에는 같은 결과를 돌려준다. 따라서 AWS 자격 증명이 없는 로컬 환경에서도 Local_Check로 검사할 수 있다.
11. IF Identity_Mode 설정이 없거나 Decision_Log D-07에 적힌 선택지에 없는 값이면, THEN THE Identity_Resolver SHALL 초기화 단계에서 첫 요청을 처리하기 전에 설정 값 이름을 담은 설정 검사 오류를 내고, 어떤 요청에도 사용자 ID를 돌려주지 않는다.
12. THE Identity_Resolver SHALL 자신이 내는 오류(`UNAUTHORIZED`, 설정 검사 오류)의 `message`와 `details`에 원래 사용자 ID 값을 넣지 않는다 (tech.md "보안·개인정보", AGENTS.md "환경·보안").

### Requirement 7: 공통 프로필 계약

**User Story:** As a B 파트 개발자와 공통 백엔드 개발자, I want 추천과 정책 판정에 필요한 프로필 필드를 미리 합의하기를, so that 온보딩 화면과 추천 로직을 따로 개발해도 필드가 맞는다.

출처: B §10.1·§10.3·§4.2 B-08, 제안서 5.2·8.4, product.md "제품 원칙" 7, tech.md "기술 미확정" 7

#### Acceptance Criteria

결정 반영 (D-08·D-33 CONFIRMED): Common_Profile은 `team07-career-mentor`의 `PROFILE#BASIC`이고 API는 `GET`/`PUT /api/v1/me/profile`(`backend/me_api.py`)이다. B 피드백 v0.1이 이 필드 이름을 따른다.

1. THE Contract_Package SHALL Common_Profile 필드를 `birthYear`, `residenceSido`, `residenceSigungu`, `residenceSince`, `universityRegion`, `graduationStatus`, `educationLevel`, `major`, `careerYears`, `employmentStatus`, `monthlyIncome`, `householdIncomeLevel`, `desiredJobs`, `desiredRegion`, `priorities`, `talentPoolConsent`로 정의한다. 저장은 부분 수정을 허용하므로 모든 필드가 선택이다. 기능에 필요한 최소 필드는 소비 Part가 검사하고 없으면 오류를 낸다 (B `PROFILE_INCOMPLETE` + `missingFields`).
2. THE Contract_Package SHALL `desiredJobs`를 0개 이상 3개 이하의 객체 목록으로 검사한다. 객체 필드는 `name`(1~50자, 필수), `work24Code`(고용24 직종 코드, 선택), `ncsCode`(NCS 코드, 선택)이고, 코드는 영문·숫자·밑줄 1~20자다 (고용24·NCS 병행, `docs/api.md` §6.2).
3. THE Contract_Package SHALL `residenceSido`·`universityRegion`을 2자리 숫자 문자열(시·도 코드), `residenceSigungu`를 5자리 숫자 문자열(시·군·구 코드), `residenceSince`를 `YYYY-MM`, `desiredRegion`을 `ALL` 또는 시·도 코드로 검사한다.
4. THE Contract_Package SHALL 생년을 1950~2015 사이의 정수 연도(`birthYear`)로만 받고, 문자열과 월·일이 들어간 날짜 형식 값은 검사 오류로 거부한다 (B §4.2 B-08 "생년만 받으므로", B §10.3 예 `2003`).
5. IF Common_Profile 데이터에 1번에 정의되지 않은 필드가 있으면, THEN THE Contract_Package SHALL 정의되지 않은 필드 이름을 모두 담은 검사 오류를 내고, 해당 필드를 뺀 부분 객체를 돌려주지 않고 데이터 전체를 거부한다 (실명·연락처·주민번호 수집 금지, product.md 원칙 7).
6. FOR ALL 유효한 Common_Profile 객체, THE Contract_Package SHALL JSON으로 직렬화한 뒤 다시 읽은 결과가 원래 객체와 같도록 한다. 같다는 것은 필드 집합과 모든 필드 값이 같다는 뜻이며, 원래 객체에 없던 선택 필드는 다시 읽은 결과에도 없어야 하고 `null`로 채워지면 안 된다 (왕복 속성).
7. THE Contract_Package SHALL Common_Profile 계약 정의에 소유 Part를 BACKEND로, A·B·C를 읽기 전용 소비자로 적는다 (B §1 담당 구분, §10.1).
8. IF Common_Profile 데이터에 필수 필드가 없거나, 필드 값이 2~4번 규칙 또는 9번 허용 값 목록을 어기면, THEN THE Contract_Package SHALL 문제가 된 필드 이름과 위반 규칙을 필드마다 담은 검사 오류를 내고 데이터 전체를 거부한다. 필드가 없는 것은 오류로 보지 않는다 (기준 1). `null`을 보내면 그 필드를 지운다.
9. THE Contract_Package SHALL 열거형 필드의 허용 값을 다음으로 둔다 (D-33): `educationLevel` `HIGH_SCHOOL`·`ASSOCIATE`·`BACHELOR`·`MASTER`·`DOCTOR`, `graduationStatus` `ENROLLED`·`GRADUATING`·`GRADUATED`, `employmentStatus` `UNEMPLOYED`·`EMPLOYED`·`PART_TIME`·`STUDENT`, `householdIncomeLevel` `under_100`·`under_150`·`over_150`·`unknown`, `priorities` `SALARY`·`GROWTH`·`STABILITY`·`WORK_LIFE`·`HOUSING`·`LOCATION`.
10. WHEN Common_Profile 데이터에 `priorities`가 있을 때, THE Contract_Package SHALL `priorities`를 9번 허용 값으로 이루어진 3개 이하의 목록으로 검사한다.

### Requirement 8: 공고 계약 (B → A·C)

**User Story:** As a A 파트와 C 파트 개발자, I want B가 만드는 공고 데이터를 정해진 형식으로 받기를, so that B의 수집이 끝나기 전에도 예시 공고로 적합도·첨삭·면접 기능을 만들 수 있다.

출처: B §3.2·§3.5·§6.1·§10.1·§10.2, A §4.1·§4.4·§7.3·§12.3, C §5.2, tech.md "기술 미확정" 5

결정 반영 (D-09·D-10·D-34 CONFIRMED, B 피드백 v0.1): 공고 계약은 `team07-catalog`의 `POSTING#{jobPostingId}` / `SNAP#{snapshotId}`·`LATEST` 형식(`docs/db-schema.md` §3)이 기준이다. 내용이 바뀔 때만 새 스냅샷을 쓰고 마감돼도 지우지 않는다. B §10.2의 옛 이름은 다음처럼 바뀌었고, 아래 기준의 옛 이름은 이 대응으로 읽는다: `postingId`→`jobPostingId`, `deadline`→`closesAt`, `sourceUrl`→`officialUrl`, `collectedAt`→`checkedAt`, `company.name`→`organization`, `active=false`→`isExpired=true`, `requirements{required, preferred}`→`requirements[]{requirementId, name, kind(REQUIRED_SKILL/PREFERRED_SKILL), weight(기본 1.0), sourceQuote, extractedBy}`, `evidence`→`sourceQuote`, 공고 버전 식별자 = `snapshotId`(`{수집일 YYYYMMDD}-{contentHash 8자}`). 지원 자격 조건은 스냅샷의 `eligibilityRules[]`, 판정은 `backend/eligibility.py`의 `evaluate_eligibility()` 하나로 한다 (D-11).

#### Acceptance Criteria

1. THE Contract_Package SHALL Posting_For_Analysis를 B §10.2 표의 필드(`postingId`, `company.name`, `job.name`, `requirements.required`, `requirements.preferred`, `careerType`, `educationMin`, `requirements.certificates`, `jobDescription`, `sourceUrl`, `collectedAt`, `updatedAt`)와 `workRegion`(`sido`, `sigungu`, `label`, `unknown`, B §3.2·§6.1), `deadline`, `sourceType`, 공고 마감 여부 값으로 정의한다. 이 중 `careerType`, `educationMin`, `requirements.certificates`, `jobDescription`, `deadline`은 공고에 정보가 없을 때 비워 둘 수 있는 선택 필드이고 (B §3.2 "채용시까지"는 `rolling=true`, B §4.2 B-04 "정보가 없으면 UNKNOWN"), 나머지는 필수 필드다. `requirements.required`와 `requirements.preferred`는 0개 이상의 항목을 담는 목록이다. 마감 여부 값의 필드 이름은 Decision_Log 항목 `D-34`로 남긴다.
2. THE Contract_Package SHALL Posting_For_Analysis의 요건 항목(`requirements.required`, `requirements.preferred`, `requirements.certificates`의 각 항목)마다 1자 이상의 원문 인용(`evidence`)과 값을 만든 주체(`extractedBy`: `API`, `LLM`, `MANUAL` 중 하나)를 포함한다 (B §3.5, B §10.2, A §4.4 `sourceQuote`).
3. THE Contract_Package SHALL Posting_For_Analysis에 공고 내용 버전 식별자를 포함해 A가 분석에 쓴 공고 버전을 고정할 수 있게 하고 (A §4.1 `jobSnapshotVersion`, A §7.3), `postingId`가 같은 두 Posting_For_Analysis의 요건 항목이나 `jobDescription`이 다르면 두 식별자 값도 다르게 한다. 식별자로 쓸 필드는 Decision_Log D-09 항목으로 남긴다 (제안 기본값 `postingId` + `contentHash`, 상태 PROPOSED).
4. WHEN Posting_For_Analysis를 Job_Requirement_View로 변환하면, THE Contract_Package SHALL `requirements.required`의 각 항목을 `kind`가 `REQUIRED_SKILL`인 항목으로, `requirements.preferred`의 각 항목을 `kind`가 `PREFERRED_SKILL`인 항목으로 옮긴다. 이때 항목 값은 `name`에, 원문 인용(`evidence`)은 `sourceQuote`에 넣고, 각 항목에 Job_Requirement_View 안에서 겹치지 않는 `requirementId`를 붙이며, `sourceType`은 원래 값을 유지한다 (A §4.4, B §10.2). `weight`는 B 명세에 없으므로 그 기본값은 Decision_Log D-10 항목에서 정한 값을 쓴다.
5. FOR ALL 유효한 Posting_For_Analysis 객체 (필수·우대 요건이 0개인 객체 포함), THE Contract_Package SHALL Job_Requirement_View 변환 전후의 필수 요건 개수와 우대 요건 개수가 각각 같도록 하고, 변환된 각 항목의 `sourceQuote`가 원래 항목의 `evidence` 문자열과 한 글자도 다르지 않도록 한다 (불변 속성).
6. WHEN Posting_For_Analysis에서 Interview_Job_Context를 만들면, THE Contract_Package SHALL `job.name`을 바꾸지 않고 C `start_interview`의 `job` 값으로 옮긴다 (B §10.1, C §5.2).
7. IF `job.name`의 글자 수(유니코드 문자 기준)가 0이거나 50을 넘으면, THEN THE Contract_Package SHALL Interview_Job_Context를 만들지 않고, 필드 이름 `job.name`을 담은 `INVALID_INPUT` 검사 오류를 낸다 (C §5.2 `job` 1~50자).
8. FOR ALL 유효한 Posting_For_Analysis 객체 (Fixture_Set의 Posting_For_Analysis 예시 포함), THE Contract_Package SHALL JSON으로 직렬화한 뒤 다시 읽은 결과가 원래 객체와 같도록 한다 (왕복 속성).
9. THE Contract_Package SHALL Posting_For_Analysis의 소유 Part를 B로, A와 C를 읽기 전용 소비자로 표시하고 (B §10 서두, §6.4), Job_Requirement_View 변환 함수와 Interview_Job_Context 변환 함수가 입력 Posting_For_Analysis 객체를 바꾸지 않도록 한다.
10. IF Posting_For_Analysis 데이터에 기준 1의 필수 필드가 없거나, 요건 항목의 `extractedBy`가 `API`·`LLM`·`MANUAL` 밖의 값이거나, 요건 항목의 `evidence`가 없거나 0자이거나, `workRegion.unknown`이 false인데 `workRegion.sido`가 없으면, THEN THE Contract_Package SHALL 문제가 된 필드 경로(예: `requirements.required[0].evidence`)를 담은 `INVALID_INPUT` 검사 오류를 내고, Job_Requirement_View와 Interview_Job_Context를 만들지 않는다 (A §4.4 "`sourceQuote` 원문 검증을 통과해야 조건을 확정").
11. WHEN 마감된 Posting_For_Analysis(B §4.2 B-01 `active=false`, B §5.8 `closed: true`)를 Job_Requirement_View로 변환하면, THE Contract_Package SHALL 이 공고를 오류 없이 변환하고 A §12.3 `isExpired` 값을 true로 둔다. 마감되지 않은 공고를 변환하면 `isExpired`를 false로 둔다 (B §5.8 "마감된 공고는 오류가 아니라 closed: true").
12. IF 공고에 근무지 정보가 없으면, THEN THE Contract_Package SHALL `workRegion.unknown`이 true이고 `workRegion.sido`·`workRegion.sigungu`가 없는 Posting_For_Analysis를 유효한 객체로 받아들인다 (B §3.2 "없으면 unknown", B §3.5 "근무지 확인 필요").

### Requirement 9: 역량 요약 계약 (A → C)

**User Story:** As a C 파트 개발자, I want A의 역량 분석 결과를 정해진 요약 형식으로 받기를, so that A 기능이 끝나기 전에도 예시 요약으로 질문 생성을 시험할 수 있다.

출처: A §4.2·§12.2, C §3 "입력 (선택)"·§5.2 `profile`, C §10

결정 반영 (D-12 CONFIRMED, C 요청): Career_Profile_Summary 필드는 `projects`, `skills`, `needsConfirmation`(각 문자열 목록, 빈 목록 허용)과 선택 `profileId`·`profileVersion`이다. 원천은 `PROFILE#LATEST`가 가리키는 최신 역량 프로필 버전이고, 백엔드(`backend/interview_api.py`)가 읽어 `start_interview(profile=…)`에 넘긴다. 목표 직무는 이 객체가 아니라 `start_interview`의 `job`으로 넘긴다. 아래 기준의 `targetJob`→`job`, `gapsToVerify`→`needsConfirmation`으로 읽고, `strengths`는 두지 않는다.

#### Acceptance Criteria

1. THE Contract_Package SHALL Career_Profile_Summary를 C §5.2 `profile`의 필수 필드 다섯 개와 추적용 선택 필드 두 개로 정의한다 (A §12.2, C §5.2 예시). 필수 필드는 `targetJob`(문자열)과 `projects`, `skills`, `strengths`, `gapsToVerify`(각각 문자열 목록, 빈 목록 허용)이다. 선택 필드는 `profileId`(빈 값이 아닌 문자열)와 `profileVersion`(1 이상의 정수)이다. 이 필드 구성은 Decision_Log D-12의 제안 기본값(`PROPOSED`)이고, 팀이 확인하기 전에 바꿀 때는 Contract_Change_Procedure를 따른다. 목록 필드의 최대 항목 수와 항목별 최대 글자 수는 D-12에 제안 기본값으로 적고, Contract_Package 검사는 그 값을 쓴다.
2. THE Contract_Package SHALL Career_Profile_Summary에 이력서 원문을 담는 필드를 정의하지 않는다 (A §12.2 `allowRawResume: false`). C §5.2의 `resumeText`(50~5,000자)는 Career_Profile_Summary에 넣지 않고 `start_interview`의 별도 입력으로 남긴다.
3. THE Contract_Package SHALL A §12.2 필드 여덟 개(`profileId`, `profileVersion`, `jobPostingId`, `confirmedCompetencies`, `experienceSummaries`, `verificationQuestions`, `fitAnalysisId`, `allowRawResume`)마다 대응하는 Career_Profile_Summary 필드를 적은 대응표를 포함한다. 대응하는 필드가 없으면 "대응 없음"과 그 이유를 적는다. 대응표는 Career_Profile_Summary 필드 일곱 개마다 A 쪽 원천 필드를 적고, 원천이 정해지지 않은 필드에는 "D-12에서 확인 필요"를 적는다.
4. THE Contract_Package SHALL Career_Profile_Summary의 소유 Part를 A로, C를 읽기 전용 소비자로 표시한다. Career_Profile_Summary는 A에서 C로 가는 단방향 계약이며, C의 면접 결과나 평가를 A의 CareerProfile로 되돌리는 필드나 변환 함수를 정의하지 않는다 (A §12.2 "자동 반영하지 않음", C §10).
5. FOR ALL 유효한 Career_Profile_Summary 객체(선택 필드가 없는 객체와 목록 필드가 비어 있는 객체 포함), THE Contract_Package SHALL JSON으로 직렬화한 뒤 다시 읽은 결과가 원래 객체와 같도록 한다. 같다는 것은 모든 필드 값과 목록 항목 순서가 같다는 뜻이다 (왕복 속성).
6. IF Career_Profile_Summary 데이터에 정의되지 않은 필드(`resumeText` 포함)가 있으면, THEN THE Contract_Package SHALL 객체를 거부하고 정의되지 않은 필드 이름을 모두 담은 검사 오류를 낸다.
7. IF Career_Profile_Summary 데이터에 필수 필드가 없거나, 필드 값의 형식이 기준 1과 다르거나, `targetJob`이 비어 있거나 50자를 넘거나, 목록 항목 중 빈 문자열이 있으면, THEN THE Contract_Package SHALL 객체를 거부하고 위반한 필드 이름을 담은 검사 오류를 낸다. `targetJob` 1~50자는 C §5.2 `job` 1~50자를 같은 목표 직무 값에 적용한 제안이며 D-12에 함께 적는다.
8. THE Contract_Package SHALL 대응표에서 `skills`와 `strengths`의 원천으로 A §4.2 `factStatus`가 `VERIFIED`가 아닌 값을 적지 않는다. 대응표는 `gapsToVerify`를 "확인이 필요한 역량"(C §3)으로 설명하고, 부족이 확정된 역량으로 설명하지 않는다 (A §4.2 "`NOT_FOUND` ≠ 실력 없음").
9. THE Fixture_Set SHALL 유효한 Career_Profile_Summary 예시를 두 개 이상 포함한다. 하나는 C §5.2 요청 예시의 `profile` 값을 그대로 쓰고 선택 필드를 비운 예시이다. 다른 하나는 같은 값에 `profileId: "profile-demo"`와 `profileVersion: 1`을 채운 예시이다 (A §12.2).

### Requirement 10: 계약 버전 관리

**User Story:** As a 계약을 쓰는 파트 개발자, I want 계약이 바뀔 때 버전으로 알 수 있기를, so that 다른 파트의 변경 때문에 내 코드가 조용히 깨지지 않는다.

출처: A §4.1 `schemaVersion`, structure.md "Spec·작업 진행 원칙", tech.md "API" 아래 "계약 문서를 먼저 고치고"

#### Acceptance Criteria

1. THE Contract_Package SHALL 계약마다 현재 `schemaVersion` 값을 하나씩 선언하고, 그 값은 `주.부` 형식의 문자열(주·부는 0 이상의 정수, 예: A §4.3의 `"2.0"`)로 적는다.
2. WHEN 계약 변경이 필드 삭제, 필드 이름 변경, 필드 타입 변경, 선택 필드의 필수 전환, 허용 값 축소 중 하나 이상을 포함하면, THE Contract_Change_Procedure SHALL 같은 PR에서 해당 계약의 주 버전을 1 올리고 부 버전을 0으로 되돌리도록 요구한다.
3. IF 계약 데이터에 `schemaVersion`이 없거나, 값이 `주.부` 형식이 아니거나, 주 버전이 Contract_Package가 지원하는 주 버전과 다르면, THEN THE Contract_Package SHALL 계약 이름, 받은 값, 지원 버전을 담은 검사 오류를 내고 검사·변환 결과를 돌려주지 않는다.
4. THE Contract_Package SHALL 계약마다 소유 Part 1개, 소비 Part 1개 이상(Glossary의 Part 값 중에서), 근거 명세 절 1개 이상(예: `A §4.4`, `B §10.2`)을 기록한다.
5. WHEN 계약 변경이 선택 필드 추가나 허용 값 확대만 포함하면, THE Contract_Change_Procedure SHALL 주 버전을 그대로 두고 같은 PR에서 부 버전을 1 올리도록 요구한다.
6. WHEN 계약 데이터의 주 버전이 지원 주 버전과 같고 부 버전만 다르면, THE Contract_Package SHALL 버전 오류를 내지 않고 그 데이터를 검사한다.
7. THE Local_Check SHALL Fixture_Set의 모든 예시 데이터가 가진 `schemaVersion`이 해당 계약의 현재 버전과 같은지, 모든 계약에 4번의 기록이 있는지 확인하고, 하나라도 어긋나면 계약 이름과 어긋난 항목을 출력하고 실패로 끝난다.

### Requirement 11: 공통 예시 데이터

**User Story:** As a A·B·C·프론트엔드 개발자, I want 계약마다 바로 쓸 수 있는 예시 데이터를 받기를, so that 다른 파트의 구현을 기다리지 않고 화면과 함수를 개발하고 시험할 수 있다.

출처: B §9 "가짜 응답(mocks/)", B §7.1 페르소나, B §6.5 설정 `busanSido`·`capitalAreaSido`, C §3 시연 직무, C §7 "samples/", A §10.3 "로컬 개발에서 사용하는 폴백", tech.md "보안·개인정보", structure.md "코딩 규칙" 테스트 항목

#### Acceptance Criteria

1. THE Fixture_Set SHALL Contract_Package의 계약마다 유효한 예시를 하나 이상 포함하고, 각 예시에 대상 계약 이름과 계약 버전을 적는다 (Requirement 10).
2. THE Fixture_Set SHALL B §7.1의 페르소나 3명마다 Common_Profile 예시를 하나씩 포함하고, 각 예시는 B §7.1 표의 프로필 칸에 적힌 값만 Common_Profile 계약 필드로 담는다. 해당 값은 출생연도, 거주 구, 학교 소재지와 재학·졸업 상태, 전공, 희망 직무, 취업 상태, 그리고 표에 적힌 경우 중요 조건이다. B §7.1 표의 기대 결과 칸은 B 소유 데이터로 두고 Fixture_Set에 넣지 않는다.
3. THE Fixture_Set SHALL Posting_For_Analysis 예시로 부산 근무 공고(근무지 시도 코드 `26`)와 수도권 근무 공고(시도 코드 `11`, `41`, `28` 중 하나)를 각각 하나 이상 포함한다 (B §6.5 설정 `busanSido`·`capitalAreaSido`). 수도권 공고 중 하나 이상은 서울 데이터 분석 직무 공고로 두고 (B §7.1 페르소나 ①), 부산 공고 중 하나 이상은 `job.name`이 "데이터 분석"인 공고로 둔다 (통합 데모 직무, D-37). 모든 공고 예시의 `sourceType`은 `DEMO`로, 회사명은 "가상"이라는 말이 들어간 이름으로 둔다 (A §4.4 "시연용 가상 기업", A §10.3, B §5.3 "회사명은 가상").
4. THE Fixture_Set SHALL Error_Code_Catalog의 코드마다 Error_Envelope 예시를 하나씩 포함한다. Async_Task_Status 예시는 `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` 상태마다 하나씩, 선언된 Status_Extension 값마다 하나씩 포함한다. `FAILED` 예시에는 Error_Envelope의 `error` 객체를 넣는다 (Requirement 5).
5. WHEN Local_Check가 실행되면, THE Local_Check SHALL 다음 세 가지를 확인한다. 유효한 예시는 모두 대응 계약의 검사를 통과해야 한다. 잘못된 예시는 모두 기대한 필드 이름을 담은 검사 오류로 거부되어야 한다. Job_Requirement_View·Interview_Job_Context 예시는 대응하는 Posting_For_Analysis 예시를 Contract_Package 변환 함수에 넣은 결과와 같아야 한다.
6. IF Fixture_Set 파일에 AWS 계정 ID 형태(앞뒤가 숫자가 아닌 연속 12자리 숫자), 액세스 키 형태(`AKIA` 또는 `ASIA` 뒤에 영문 대문자나 숫자 16자가 이어지는 20자 문자열), 이메일 주소, 전화번호, 주민등록번호 형태(6자리-7자리 숫자)의 문자열이 있으면, THEN THE Secret_Scanner SHALL 각 문자열의 파일 경로와 줄 번호를 보고하고 Local_Check를 실패로 끝낸다 (tech.md "보안·개인정보": 공개 저장소). 계정 ID·액세스 키 형태의 정의와 `<계정ID>` 같은 꺾쇠 자리표시자 제외 규칙은 Requirement 13 기준 5·6과 같고, 이메일 주소·전화번호·주민등록번호 형태 검사는 Fixture_Set 파일에만 추가로 적용한다.
7. THE Fixture_Set SHALL Python 이외의 소비자(프론트엔드)가 읽을 수 있는 UTF-8 JSON 파일로 제공되고, 위치를 루트 README에 적는다. 파트 내부 가짜 데이터는 각 Part 소유로 두고 Fixture_Set에 넣지 않는다. 여기에는 B `mocks/`, C `samples/`, A `MockLLM` fixture가 들어간다 (B §9, C §7, A §10.3).
8. THE Fixture_Set SHALL Contract_Package의 계약마다 잘못된 예시를 하나 이상 포함하고, 각 잘못된 예시에 검사 오류로 거부될 것으로 기대하는 필드 이름을 적는다. 잘못된 예시에는 Career_Profile_Summary에 정의되지 않은 필드를 넣은 예시가 들어간다. 필수 필드를 뺀 예시도 들어가며, `job.name`이 비었거나 50자를 넘는 예시가 그 하나다 (Requirement 8 기준 7, Requirement 9 기준 6).
9. THE Fixture_Set SHALL 통합 데모 직무(데이터 분석, D-37)의 가상 자소서에 맞춘 Career_Profile_Summary 예시를 하나 이상 포함한다. 이 예시는 `targetJob`을 "데이터 분석"으로 두고, `projects`, `skills`, `strengths`, `gapsToVerify`에 각각 값을 하나 이상 넣으며, 이력서 원문 필드는 넣지 않는다 (C §5.2 `profile`, A §12.2 `allowRawResume: false`).
10. IF 유효한 예시가 대응 계약의 검사를 통과하지 못하거나, 잘못된 예시가 기대한 필드 이름의 검사 오류로 거부되지 않으면, THEN THE Local_Check SHALL 해당 예시의 파일 경로, 계약 이름, 기대한 결과와 실제 결과를 보고하고 실패로 끝난다.
11. THE Fixture_Set SHALL 모든 예시의 숫자 값과 숫자 문자열에서 연속된 숫자를 11자리 이하로 두어, 기준 6과 Requirement 13 기준 5의 AWS 계정 ID 형태 검사에 걸리지 않게 한다.

### Requirement 12: Backend와 Ai 코드의 연결 경계

**User Story:** As a 공통 백엔드 개발자, I want 각 파트 코드를 부르는 입구와 import 규칙을 미리 알기를, so that 파트 내부 구현이 바뀌어도 백엔드 연결 코드를 다시 쓰지 않는다.

출처: structure.md "파트별 코드 구조"·"구조 미확정", B §5.9·§13, C "함수 명세"·"백엔드와의 약속", A §3·§10, tech.md "AI Agent 구조"

#### Acceptance Criteria

1. THE Integration_Seam_Doc SHALL A·B·C Part마다 Backend가 부르는 입구를 하나도 빠짐없이 목록으로 적고, 입구마다 입구 모듈 경로, 공개 함수 또는 핸들러 이름, 호출 경로(REST 핸들러, Agent 도구, 비동기 작업 처리기 중 하나), 입력·출력 계약 이름(Contract_Package의 계약 이름 또는 해당 Part 내부 형식이면 "Part 내부")을 적는다 (C "백엔드가 부르는 함수", B §5.9·§13 `api/rest_handler.py`·`api/agent_handler.py`). C 항목에는 `start_interview`, `synthesize_question`, `start_transcription`, `get_transcription_result`, `process_answer`, `analyze_face`, `compute_baseline`, `generate_report` 8개를 모두 적는다. 문서에 이름이 없는 입구(예: A의 mentoring API와 작업 처리기 입구, A §10)는 해당 후속 스펙 이름과 함께 "미정"으로 적는다.
2. THE Integration_Seam_Doc SHALL A·B·C Part마다 Python import 패키지 이름과 소스 위치를 적고, 각 패키지 이름이 하이픈 없는 Python 식별자이며 세 Part 사이에서 서로 겹치지 않도록 한다 (B `ai/busan-opportunity/src/opportunity/`, C §10 `interview/` 폴더 import, structure.md "하이픈이 든 폴더 이름은 바로 import할 수 없다"). 아직 정해지지 않은 Part의 패키지 이름은 해당 후속 스펙 이름과 함께 "미정"으로 적는다.
3. THE Integration_Seam_Doc SHALL Backend가 Ai 코드를 Lambda에 포함하는 패키징 방식과 Lambda 분리 방식을 직접 정하지 않고 Decision_Log 항목 ID `D-17`과 그 항목의 현재 Decision_Status로만 참조하며, 1번의 입구 목록은 `D-17`의 결정 결과와 관계없이 같은 내용으로 둔다 (structure.md "구조 미확정", Decision_Log D-17 "Integration_Seam_Doc의 입구 목록만 먼저 고정").
4. FOR ALL `ai/mentoring/`, `ai/busan-opportunity/`, `ai/interview/` 아래 Python 파일(테스트 파일 포함), THE Import_Rule_Checker SHALL 각 `import`·`from ... import` 문이 `backend/` 아래 코드를 가리키지 않는지 확인한다 (C "함수는 DB·API를 직접 부르지 않음", A·C 단독 테스트). `frontend/`는 Python 코드가 아니므로 검사 대상에서 뺀다.
5. FOR ALL A·B·C Part 폴더 아래 Python 파일(테스트 파일 포함), THE Import_Rule_Checker SHALL 파일 경로로 소속 Part를 정하고, 각 import 대상이 같은 Part의 패키지, Contract_Package, 표준 라이브러리, 해당 Part 의존성 파일에 적힌 외부 패키지 중 하나인지 확인한다. 다른 Part의 패키지는 2번에 적힌 이름으로 알아내고, Contract_Package의 위치는 Decision_Log `D-18`의 결정을 따른다 (structure.md "다른 파트의 기능을 중복 구현하지 않고 계약으로 연결한다").
6. THE Integration_Seam_Doc SHALL 통합 Agent 프레임워크 선택을 A의 mentoring-agent-quality 스펙 소유이자 Decision_Log `D-23` 항목으로 적고 Foundation에서 정하지 않는다. 또 Agent 도구 입구는 REST 입구와 같은 비즈니스 함수를 부르고, 요청 변환, Identity_Resolver 호출, 응답 변환만 하며 비즈니스 규칙을 따로 구현하지 않는다는 규칙을 적는다 (B §1.1·§5.9의 `rest_handler.py`·`agent_handler.py`가 같은 `find_busan_alternatives`를 부르는 예, tech.md "AI Agent 구조", A F-06). C 항목에는 Agent 도구 입구가 없고 통합 Agent와는 페이지 이동으로만 연결된다고 적는다 (C §10).
7. FOR ALL `backend/` 아래 Python 파일(테스트 파일 포함), THE Import_Rule_Checker SHALL A·B·C Part 코드에 대한 import가 1번에 적힌 입구 모듈이나 Contract_Package만 가리키는지 확인하고, 그 밖의 Part 내부 모듈을 가리키는 import를 위반으로 판정한다.
8. IF Import_Rule_Checker가 4번, 5번, 7번 규칙의 위반을 하나 이상 찾으면, THEN THE Import_Rule_Checker SHALL 위반마다 파일 경로, 줄 번호, import한 파일의 Part, import 대상 모듈 이름을 보고하고 실패로 끝나며, THE Local_Check SHALL 전체 결과를 실패로 판정한다. 위반이 0건이면 THE Import_Rule_Checker SHALL 성공으로 끝난다.
9. THE Integration_Seam_Doc SHALL A·B·C Part마다 입구가 내보내는 오류 형식(C는 `InterviewError(code, message, retryable)`)과, Backend가 그 오류를 Error_Envelope로 바꿀 때 쓰는 Error_Code_Catalog 코드 대응표를 적는다. C 항목에는 `INVALID_INPUT`, `AI_OUTPUT_INVALID`, `AWS_SERVICE_ERROR` 세 코드를 모두 넣고, `retryable` 값은 받은 그대로 넘긴다고 적는다 (C "백엔드와의 약속"). 오류 형식이 정해지지 않은 Part는 해당 후속 스펙 이름과 함께 "미정"으로 적는다.

### Requirement 13: 자원 이름과 설정 규칙

**User Story:** As a 다른 팀과 AWS 계정을 함께 쓰는 개발자, I want 자원 이름·태그·환경변수·비밀정보 규칙을 한곳에서 확인하기를, so that 다른 팀 자원을 건드리거나 비밀정보를 공개 저장소에 올리는 일을 막을 수 있다.

출처: tech.md "이전 뼈대에서 정한 환경"·"저장 자원"·"보안·개인정보", B §2.3 "리전 ap-northeast-2, 모델 ID는 설정 파일", C §2.3·"백엔드와의 약속" `MODEL_ID`, B §6.5, AGENTS.md "환경·보안"

#### Acceptance Criteria

1. THE Resource_Naming_Convention SHALL 리전 `ap-northeast-2`, 자원 이름 접두사 `team07-`, 태그 `team=team07`을 이전 뼈대 기준 값으로 적고, 접두사와 태그 항목마다 Decision_Log 항목 ID `D-21`과 그 항목의 현재 Decision_Status를 함께 표시한다. 접두사와 태그 값은 `D-21`이 `CONFIRMED`가 되기 전까지 확정 값으로 표시하지 않는다.
2. THE Resource_Naming_Convention SHALL Part마다 모델 ID, 테이블 이름, 버킷 이름, 비밀정보 이름을 담는 환경변수 이름과 설정 파일 위치를 표로 적는다 (C `MODEL_ID`, B `opportunity_config.json`). 이 표는 다음 규칙도 적는다. (a) 계정 ID가 들어가는 버킷 이름은 `team07-<이름>-<계정ID>`처럼 자리표시자로 적는다. 실제 계정 ID는 실행 시점에 조회하고 저장소에 적지 않는다. (b) 필수 환경변수나 설정 값이 없으면 설정을 읽는 코드는 그 변수 이름을 담은 오류를 내고 멈춘다. 코드 안의 기본 모델 ID나 기본 자원 이름으로 대체하지 않는다.
3. THE Resource_Naming_Convention SHALL 테이블과 버킷마다 소유 Part 하나와 읽기 권한을 받는 Part 목록(없으면 "없음")을 적는다. 확정되지 않은 구성은 Decision_Log 항목 ID로 참조한다. DynamoDB 테이블 구성은 `D-13`, 업로드 버킷은 `D-14`로 참조한다 (tech.md "저장 자원" 테이블 구성안). 이전 스크립트로 만든 자원에는 "이전 뼈대 생성, 현재 존재 미확인"을 표시한다.
4. THE Resource_Naming_Convention SHALL 비밀정보 규칙을 적는다. 비밀정보는 Secrets Manager나 IAM 역할로만 다룬다. 자격 증명은 `aws login`으로 얻고 액세스 키는 만들지 않는다. 코드, Git, `.env`, 로그, 문서에는 비밀정보의 이름만 적고 값, 계정 ID, API 주소는 적지 않는다 (AGENTS.md "환경·보안", tech.md "보안·개인정보").
5. FOR ALL 커밋 대상 파일(Git이 추적하거나 스테이징된 텍스트 파일, `.gitignore` 대상 제외), THE Secret_Scanner SHALL 다음 형태의 문자열을 찾는다. (a) AWS 계정 ID 형태: 앞뒤가 숫자가 아닌 연속 12자리 숫자. ARN 안의 12자리 숫자와 버킷 이름 끝의 12자리 숫자를 포함한다. (b) AWS 액세스 키 ID 형태: `AKIA` 또는 `ASIA` 뒤에 영문 대문자나 숫자 16자가 이어지는 20자 문자열. 찾은 문자열마다 파일 경로와 줄 번호를 보고하고, 찾은 값 전체는 출력하지 않는다.
6. WHEN Secret_Scanner가 `<계정ID>`처럼 꺾쇠괄호로 감싼 자리표시자를 만나면, THE Secret_Scanner SHALL 그 자리표시자를 보고 대상에서 제외한다.
7. IF Secret_Scanner가 하나 이상을 보고하면, THEN THE Local_Check SHALL 실패 상태로 끝나고 보고 건수를 출력한다. 파일은 수정하거나 지우지 않는다.
8. FOR ALL `ai/`와 `backend/` 아래 소스 파일(테스트 파일 포함, Criterion 2의 표에 적힌 설정 파일 제외), THE Local_Check SHALL Bedrock 모델 ID 형태의 문자열 리터럴을 찾아 파일 경로와 줄 번호를 보고하고, 하나라도 있으면 실패 상태로 끝난다 (AGENTS.md "모델 ID ... 설정 파일이나 환경변수에서 읽는다"). Bedrock 모델 ID 형태는 선택적인 `global.` 접두사 뒤에 Resource_Naming_Convention에 적힌 모델 제공자 접두사가 오는 문자열이다. 제공자 접두사 목록은 최소 `anthropic.`, `cohere.`, `amazon.titan-`을 포함한다 (tech.md 예: `global.anthropic.claude-haiku-5-5`, `global.cohere.embed-v4:0`, `amazon.titan-embed-text-v2:0`).
9. THE Resource_Naming_Convention SHALL 다음 규칙을 적는다. 자원 이름이 `team07-`로 시작하지 않거나 `team=team07` 태그가 없는 AWS 자원은 바꾸거나 지우지 않는다. 자원 생성·삭제·권한 변경은 실행 전에 사용자에게 먼저 확인한다 (AGENTS.md "환경·보안", tech.md "이전 뼈대에서 정한 환경").

### Requirement 14: 결정 기록

**User Story:** As a 팀 리더와 각 파트 담당자, I want 여러 파트에 걸친 미확정 항목을 한 문서에서 관리하기를, so that 누구도 미확정 항목을 혼자 정하지 않고, 확정되면 모두가 같은 내용을 따른다.

출처: AGENTS.md "미확정", tech.md "기술 미확정" 1~14, structure.md "구조 미확정", product.md "범위 관련 미확정"

#### Acceptance Criteria

1. THE Decision_Log SHALL Local_Check가 읽을 수 있는 구조화된 형식(항목 하나가 한 행인 표 또는 구조화 파일)으로 항목마다 다음 필수 칸을 적는다: Decision_Log 안에서 중복되지 않는 ID, 제목, 영향을 받는 Part(Glossary의 Part 값 하나 이상), 선택지(2개 이상)와 각 선택지의 출처(문서와 절 또는 번호), 제안 기본값과 출처, 확정 담당 Part, Decision_Status, 영향을 받는 후속 스펙(Requirement 2의 후속 스펙 10개 이름 중 하나 이상), Seam.
2. THE Decision_Log SHALL tech.md "기술 미확정" 1~14의 번호마다, 그리고 structure.md "구조 미확정"과 product.md "범위 관련 미확정"의 항목(글머리표)마다 출처 칸에 그 번호나 항목을 적은 Decision_Log 항목을 하나 이상 두고, 이 스펙이 새로 찾은 항목에는 이 스펙의 Requirement 번호를 출처로 적는다.
3. WHILE Decision_Log 항목의 Decision_Status가 `CONFIRMED`가 아니면, THE Foundation SHALL 해당 항목에 걸리는 구현을 그 항목의 Seam 칸에 적힌 Seam 뒤에서만 하도록 하고, Seam 칸이 "Seam 없음 — 해당 후속 스펙 착수 전 확정 필요"인 항목은 영향을 받는 후속 스펙의 구현을 확정 전에 시작하지 않도록 하는 규칙을 적는다.
4. WHEN Decision_Log 항목의 Decision_Status가 `CONFIRMED`로 바뀌면, THE Contract_Change_Procedure SHALL 같은 PR 안에서 그 항목에 선택한 선택지, 확정 날짜(`YYYY-MM-DD`), 확정자를 기록하고, 그 항목 ID를 참조하는 API_Convention_Doc, Resource_Naming_Convention, steering 문서(`tech.md`, `structure.md`, `product.md`)를 고치고, Requirement 2의 리뷰 요청 절차를 따르도록 요구한다.
5. WHERE 미확정 항목이 한 Part에만 속하면 (예: tech.md "기술 미확정" 2 통합 Agent 프레임워크는 A, 12 프론트엔드 프레임워크는 FRONTEND), THE Decision_Log SHALL 해당 항목의 확정 담당 칸에 그 Part를 적고, 제안 기본값 칸에 "없음"과 그 Part 소유라는 이유를 적고, 그 Part가 확정할 때까지 Decision_Status를 `OPEN`으로 둔다.
6. WHEN 개발자가 Local_Check를 실행하면, THE Local_Check SHALL Decision_Log의 모든 항목이 1번의 필수 칸을 빈칸 없이 채웠는지, ID가 중복되지 않는지, Decision_Status가 `OPEN`, `PROPOSED`, `CONFIRMED`, `SUPERSEDED` 중 하나인지, 7번의 상태별 규칙을 지키는지 확인한다.
7. THE Decision_Log SHALL Decision_Status마다 다음 규칙을 지킨다: `OPEN` 항목은 제안 기본값 칸에 "없음"과 이유를 적는다. `PROPOSED` 항목은 선택지 중 하나를 제안 기본값으로 적고 그 출처(문서와 절 또는 번호)를 적는다. `CONFIRMED` 항목은 선택한 선택지, 확정 날짜, 확정자를 적는다. `SUPERSEDED` 항목은 대체한 항목의 ID를 적고, 그 ID는 Decision_Log에 있어야 한다.
8. WHEN Decision_Log 항목이 더 이상 유효하지 않게 되면, THE Contract_Change_Procedure SHALL 그 항목을 삭제하지 않고 Decision_Status를 `SUPERSEDED`로 바꾸고 대체한 항목의 ID를 적도록 요구한다.
9. IF Local_Check가 Decision_Log에서 6번의 검사 중 하나라도 통과하지 못한 항목을 찾으면, THEN THE Local_Check SHALL 실패로 끝나고, 실패한 항목의 ID와 문제가 된 칸 이름을 모두 출력하고, Decision_Log 파일은 수정하지 않는다.

## 결정 기록 (Decision_Log)

2026-11-20 BACKEND 담당이 결정을 확정했다. `CONFIRMED`는 고른 값("결정" 칸), 확정 날짜, 확정자를 적는다. `OPEN` 항목은 담당이 정할 때까지 임의로 정하지 않는다 (Requirement 14 기준 5·7).

| ID | 항목 | 선택지 (출처) | 결정 / 제안 기본값 | 확정 담당 | Decision_Status |
|---|---|---|---|---|---|
| D-01 | API 경로 접두사 | `/api/v1/{mentoring\|opportunities\|interview}` (A §6, B §5.1, C §5.1) / `/chat` 등 (이전 api.md) | `/api/v1/{part}` + 공통 `/api/v1/me`, `/api/v1/auth`, `/api/v1/health` (`docs/api.md` §1) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-02 | JSON 키 표기 | 카멜 (A·B·C) / snake_case (이전 api.md) | 카멜, Python 코드는 snake_case | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-03 | 오류 형식 | `error` 안에 `requestId` (B §5.1, C §5.1) / `error` 밖 + `details` (A §6.6) | `error{code, message, requestId, retryable, details?}` (`backend/common.py`) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-04 | 오류 코드 별칭 | A `VALIDATION_ERROR`·`MODEL_UNAVAILABLE`·`SOURCE_UNAVAILABLE` / B·C `INVALID_INPUT`·`AWS_SERVICE_ERROR` | 대표 코드 `INVALID_INPUT`·`AWS_SERVICE_ERROR`, A 코드는 별칭으로 받고 응답 때 대표 코드로 (`docs/api.md` §5) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-05 | 비동기 상태 값 | 공통 4개 (B·C) / A 추가 2개 / C `stage` | 공통 4개 + Part별 Status_Extension | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-06 | 데이터 기준일 필드 | A `checkedAt` / B `dataAsOf` | 파트 이름 유지, 의미만 공통 정의 | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-07 | 사용자 식별 방식 | Cognito JWT `sub` (A §6, B §5.1) / 무로그인 UUID / MVP 무인증 (C) | Cognito JWT `sub`, 아이디·비밀번호 로그인, 데모 계정 `demo1`~`demo3` (`backend/auth_api.py`, `infra/setup-auth.sh`) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-08 | 공통 프로필 필드 | B §10.3 코드 기반 / 이전 api.md 이름 기반 | `PROFILE#BASIC` 필드 (Requirement 7 결정 반영) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-09 | 공고 버전 식별 | A 스냅샷 / B 덮어쓰기 / catalog 스냅샷 | catalog `SNAP#{snapshotId}` + `LATEST`, 바뀔 때만 새 스냅샷 (B 피드백 v0.1) | A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 (B v0.1 동의) |
| D-10 | 요건 구조와 `weight` | A `requirements[{kind, weight, sourceQuote}]` / B `requirements{required, preferred}` | A 형식(`kind` `REQUIRED_SKILL`/`PREFERRED_SKILL`), `weight` 기본 1.0 (B v0.1 팀 필드) | A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 (B v0.1 동의) |
| D-11 | 지원자격 상태 값 | A·B 공고·B 정책 각각 | Part별 이름 유지, 공고 자격 판정은 `backend/eligibility.py` 하나로 (조건별 B 값, 전체 A 값) | A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-12 | 역량 요약 필드 (A → C) | A §12.2 / C §5.2 `profile` | `projects`, `skills`, `needsConfirmation` + 선택 `profileId`·`profileVersion` (C 요청, Requirement 9 결정 반영) | A + C | CONFIRMED · 2026-11-20 · BACKEND 담당 (C 동의) |
| D-13 | DynamoDB 구성 | 통합 4테이블 / Part별 테이블 | `team07-career-mentor`·`catalog`·`reference`·`cache` (`docs/db-schema.md` v1.3, B·C 동의) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-14 | 이력서 업로드 버킷 | `uploads` 7일 삭제 / `career-docs` | 이력서 `career-docs`(보존), 면접 녹음·질문 음성 `uploads`(7일) | BACKEND + A | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-15 | Python 버전 | 3.12 (A·B) / 3.13 (이전 뼈대) | 3.13 (`.python-version`, Lambda `python3.13`). 3.12 이상 요구를 충족 | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-16 | IaC 도구 | CDK (B) / AWS CLI 스크립트 | AWS CLI 스크립트 `infra/` (CloudFormation 권한 없음) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-17 | Backend–Ai 패키징·Lambda 분리 | 단일 `team07-api` / 기능별 Lambda | 단일 `team07-api`. `ai/interview/`를 `interview` 패키지로 묶음 (`infra/package.sh`). 다른 Part도 하이픈 없는 패키지 이름 + 파트별 `requirements.txt` | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-18 | 공통 계약 위치 | 새 최상위 폴더 / `backend/` 아래 | 계약 문서는 `docs/api.md`·`docs/db-schema.md`, 공통 함수는 `backend/common.py`·`eligibility.py`·`workspace.py`. 기계 검사용 Contract_Package는 만들 때 새 최상위 `contracts/` | COMMON | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-19 | 비동기 처리 방식 | SQS + DLQ (A) / `/jobs` 폴링 / 상태 조회 때 진행 (C) | Lambda 비동기 자기 호출 (면접에서 동작). SQS 권한이 생겨 필요하면 전환, 함수 입출력은 그대로 | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-20 | 모의면접 API·저장 | 이전 api.md / C 명세 | C 명세 + 면접 담당 요청 (`docs/db-schema.md` §2.4, `backend/interview_api.py`) | C + BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 (C 동의) |
| D-21 | 자원 접두사·태그 | `team07-`, `team=team07` | `team07-`, `team=team07`, 리전 `ap-northeast-2` | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-22 | 벡터 저장소·임베딩 모델 | S3 Vectors / OpenSearch, Cohere v4 / Titan v2 | S3 Vectors (`team07-opp-vectors`/`postings-v1`, 1024차원, 코사인), 임베딩 `global.cohere.embed-v4:0` (한국어, 1024) | A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-23 | 통합 Agent 프레임워크 | Bedrock Agents + Action Group (A F-06, B §5.9) / Strands | Bedrock Agents 단일 Agent + Action Group (A `CareerMentoring`, B `BusanOpportunity`). Action Group은 `team07-api`가 받는다. C 면접관은 Strands 그대로, 페이지 이동으로 연결 | A | SUPERSEDED · 2026-11-20 · D-38로 바뀜 (#122) |
| D-24 | 프론트엔드 프레임워크 | 문서에 없음 | Next.js 16 App Router + React + TypeScript + Tailwind CSS v4, `output: "export"` 정적 내보내기 (`.kiro/specs/frontend-ui/`) | FRONTEND | CONFIRMED · 2026-11-20 · FRONTEND 담당 |
| D-25 | 이전 뼈대(`4aa11cc`) 재사용 | 재사용 / 미사용 | 정리해 재사용 (PR #9~#14) | 팀 리더 | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-26 | AI·데이터 작업 영역 라벨 | `fe`·`be`·`common`만 | AI·데이터·인프라 작업은 `be` | 팀 리더 | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-27 | MVP 우선순위·담당 없는 기능 | 제안서 9.2 / 파트 명세 | 없음. 이유: 범위 결정은 팀 리더. 워크스페이스·문서 버전은 D-36으로 분리해 확정 | 팀 리더 | OPEN |
| D-28 | B `infra/`·B `AGENTS.md`·`CONTRIBUTING.md` 위치 | structure.md "구조 미확정" | 인프라는 루트 `infra/`, B `AGENTS.md`는 두지 않고 루트 `AGENTS.md`·steering, `CONTRIBUTING.md`는 `docs/` | B / 팀 리더 | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-29 | 시각 표기 오프셋 | `+09:00` / `Z` | `+09:00` | BACKEND + A | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-30 | 금액 표기 | 정수 + 단위 필드 / 원 단위 정수 | 정수 + 단위 필드 (`MANWON_YEAR`, `MANWON_MONTH`, `MANWON`, `WON`) | BACKEND + B | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-31 | 같은 `Idempotency-Key`에 다른 본문 | 409 거부 (A §7.1) / 첫 결과 반환 | 409 `PRECONDITION_NOT_MET` (`IDEM#`의 `requestHash` 비교) | BACKEND + A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-32 | 오류 코드 HTTP 상태·기본 `retryable` | A §6.6 허용 값 / C §5.1 값 | `RESOURCE_NOT_OWNED` 404, A 별칭은 대표 코드의 HTTP·`retryable` (4xx false, 5xx true) | BACKEND + A | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-33 | Common_Profile 열거형 값 | B §10.3 예시 값만 | Requirement 7 기준 9의 목록 | BACKEND + B | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-34 | 공고 마감 여부 필드 이름 | B `active` / `closed` / A `isExpired` | `isExpired` (catalog `LATEST`, B v0.1) | A + B | CONFIRMED · 2026-11-20 · BACKEND 담당 (B v0.1 동의) |
| D-35 | 개발용 사용자 헤더·배포 설정 값 이름 | 이름 미정 | `X-User-Id`, `ALLOW_DEV_USER_HEADER=1`(로컬 테스트만, 배포 Lambda에는 없음) | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-36 | 공고별 워크스페이스·문서 버전 담당 (product.md "범위 관련 미확정") | 담당 미정 | 워크스페이스 BACKEND (`backend/workspace.py`, `/api/v1/me/workspaces`), 지원 상태는 워크스페이스에만. 문서 버전 저장 구조는 `docs/db-schema.md` §2.1 | BACKEND | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-37 | 통합 데모 페르소나·직무 (product.md "범위 관련 미확정") | C 백엔드 개발 / B 페르소나 ① 데이터 분석 / A NCS 11개 직무 | 페르소나 ① 데이터 분석 (NCS 20010105), 데모 계정 `demo1`~`demo3` | 팀 리더 | CONFIRMED · 2026-11-20 · BACKEND 담당 |
| D-38 | 통합 Agent 프레임워크 (D-23 대체) | Bedrock Agents + Action Group (D-23) / Strands | Strands Agents를 `team07-api` 안에서 돌린다. 패키지 `ai/supervisor/` → `supervisor`, 입구 `POST /api/v1/agent/chat` (202 + 조회). 도구는 B `agent_feed`·`agent_policies`·`ask_policies`와 A 문서·프로필을 포트로 부른다. B `BusanOpportunity` Action Group 경로는 그대로 둔다. 새 AWS 자원·권한 없음 (`docs/개발계획서4.md` §3) | 팀 | CONFIRMED · 2026-11-20 · 팀 합의 (#122) |
| D-39 | 서비스 입구 | 기능 화면별 입구 (제안서 4장) / 채팅 하나 | 홈을 채팅 Agent로 바꾼다. 채팅 조건·이력서로 채용공고와 청년정책을 함께 찾고, 모의면접(지금 C 면접 그대로)을 체험으로 제안한다. 자소서가 없으면 채팅에서 받는다. 기능 화면은 상세로 남긴다 (`docs/개발계획서4.md` §1·§2) | 팀 | CONFIRMED · 2026-11-20 · 팀 합의 (#122) |
| D-40 | 채팅 조건 저장 | 저장 안 함 / 자동 저장 / 사용자에게 묻기 | 사용자에게 묻는다. 화면 버튼을 누를 때만 `PUT /api/v1/me/profile`로 쓴다. `PROFILE#BASIC`에 `desiredSalaryMin`(만 원/년), `desiredCareerType`(`NEW`/`EXPERIENCED`/`ANY`) 추가. 직급은 공고에 필드가 없어 `careerType`(신입/경력)으로 대신한다 | 팀 | CONFIRMED · 2026-11-20 · 팀 합의 (#122) |
